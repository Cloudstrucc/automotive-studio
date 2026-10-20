#!/usr/bin/env python3
"""
Static site generator for the Autoline vehicle-ad portal.

It scans each environment folder (production / review / development) for the
images actually present and builds the pages from them — so adding, updating or
deleting an image file is all it takes. No code changes needed for CRUD.

The manifests under <env>/manifests/ say which category (catalogue) each item
belongs to and whether it and its category are on the site; the images cannot,
since an ad is named <slug>_<format>.jpg with no category in the path. See
docs/CATEGORIES.md for the routes and the status vocabulary.

Run locally:  python build.py        -> outputs the site into ./_site
In CI:        the GitHub Actions workflow runs this, then deploys ./_site.
"""
import json, os, shutil, html, re, zipfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(ROOT, "_site")
# Folder names only. They are never printed on the site: the pages carry no
# environment wording, so a client given a direct link sees just the lineup.
ENVS = [
    ("production",  "Live ads approved for publishing."),
    ("review",      "Awaiting client / stakeholder sign-off."),
    ("development", "Work in progress — not for sharing yet."),
]
# Which environment the site root mirrors.
PUBLIC_ENV = "production"
# Environments built as a responsive promo app (one ad sized to the viewer's device,
# plus a zip of the files) instead of a gallery of every format.
APP_ENVS = {"production", "review", "development"}

# ---------- catalogues (categories) ----------
# The default catalogue is the environment itself: its board is <env>/index.html and
# its items stay under <env>/cars/. That is why there is deliberately no /vehicles/
# route and why none of today's URLs moved. Every other catalogue gets <env>/<slug>/,
# with its board and its item pages together in that one folder.
DEFAULT_CATALOGUE = "vehicles"
# Where items whose catalogue was deleted are parked by the admin. Never rendered,
# whatever their own status says, so a deletion stays undoable.
ORPHAN_CATALOGUE = "orphan"
# A catalogue cannot take a folder the build already writes at an environment root.
RESERVED_ROUTES = {"ads", "assets", "cars"} | {e for e, _ in ENVS}
# Catalogue statuses that put a category on the site. "published" is the spelling
# used before categories had three states, read as "public" so an un-migrated
# manifest still builds.
PUBLIC_STATUS = {"public", "published"}

# Which format each breakpoint shows in app mode, widest first.
APP_SOURCES = [("(min-width:900px)", "landscape"), ("(min-width:560px)", "social")]
APP_FALLBACK = "phone"
FORMAT_LABELS = {          # known formats, in display order, with pixel sizes
    "social":    ("Social",    "1080 × 1350 · 4:5 feed"),
    "phone":     ("Phone",     "1080 × 2340 · 9:19.5 story"),
    "landscape": ("Landscape", "1920 × 1080 · 16:9 web"),
}
FORMAT_ORDER = ["social", "phone", "landscape"]

def esc(s): return html.escape(str(s), quote=True)

def titleize(slug):
    return re.sub(r"[-_]+", " ", slug).strip().title()

def catalogue_route(slug):
    """A catalogue's folder, relative to the environment root ("" meaning the root)."""
    return "" if slug == DEFAULT_CATALOGUE else slug

def singular(label):
    """"Vehicles" -> "vehicle", for the count in a board's footer."""
    s = str(label).strip().lower()
    return s[:-1] if s.endswith("s") and len(s) > 2 else s

def load_catalogues(env):
    """Category definitions from <env>/manifests/catalogues/, in display order.

    An environment with no catalogue manifests is treated as holding the default
    catalogue alone, with the built-in heading and lede, so it still builds."""
    folder = os.path.join(ROOT, env, "manifests", "catalogues")
    out = []
    if os.path.isdir(folder):
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".json"):
                continue
            try:
                m = json.load(open(os.path.join(folder, fn), encoding="utf-8"))
            except Exception as e:
                print(f"  ! {env}/manifests/catalogues/{fn} could not be parsed ({e}); ignored")
                continue
            slug = m.get("slug") or os.path.splitext(fn)[0]
            out.append({
                "slug": slug,
                "label": m.get("label") or titleize(slug),
                "status": str(m.get("status") or "public"),
                # a category can be public but kept out of the menu, reachable only
                # by direct link
                "in_menu": m.get("in_menu", True) is not False,
                "order": m.get("order", 999),
                "heading": m.get("heading") or m.get("label") or titleize(slug),
                "lede": m.get("lede") or "",
            })
    if not out:
        out = [{"slug": DEFAULT_CATALOGUE, "label": "Vehicles", "status": "public",
                "in_menu": True, "order": 1, "heading": "The Lineup", "lede": LEDE}]
    out.sort(key=lambda c: (c["order"], c["slug"]))
    return out

def load_item_meta(env):
    """slug -> facts from <env>/manifests/items/<catalogue>/<slug>.json.

    The manifest is what says which category an item belongs to and whether it is on
    the site. An item with no manifest falls back to the default catalogue, so an
    environment that predates manifests builds exactly as it did."""
    folder = os.path.join(ROOT, env, "manifests", "items")
    meta = {}
    if not os.path.isdir(folder):
        return meta
    for cat in sorted(os.listdir(folder)):
        d = os.path.join(folder, cat)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            try:
                m = json.load(open(os.path.join(d, fn), encoding="utf-8"))
            except Exception as e:
                print(f"  ! {env}/manifests/items/{cat}/{fn} could not be parsed ({e}); ignored")
                continue
            slug = m.get("slug") or os.path.splitext(fn)[0]
            meta[slug] = {
                "catalogue": m.get("catalogue") or cat,
                "status": str(m.get("status") or "published"),
                "name": " ".join(str(x) for x in (m.get("make"), m.get("model")) if x),
                "subtitle": m.get("subtitle") or "",
                "order": m.get("order", 999),
            }
    return meta

def renderable(cats, env):
    """The catalogues that get pages: public, not the orphan pen, route not reserved."""
    out = []
    for c in cats:
        if c["slug"] == ORPHAN_CATALOGUE:
            continue
        if c["status"] not in PUBLIC_STATUS:
            continue
        route = catalogue_route(c["slug"])
        if route and (route in RESERVED_ROUTES or not re.fullmatch(r"[a-z][a-z0-9-]*", route)):
            print(f"  ! {env}: catalogue '{c['slug']}' cannot have a folder of that name; skipped")
            continue
        out.append(c)
    return out

def scan_env(env):
    """Every renderable item in an environment, grouped into its catalogues.

    An item is on the site when its manifest says published, its category is public,
    and an ad image exists for it — the three gates docs/CATEGORIES.md records."""
    jpg_dir = os.path.join(ROOT, env, "ads", "jpg")
    svg_dir = os.path.join(ROOT, env, "ads", "svg")
    cats = load_catalogues(env)
    for c in cats:
        c["cars"] = []
    if not os.path.isdir(jpg_dir):
        return renderable(cats, env)
    by_slug = {c["slug"]: c for c in cats}
    meta = load_item_meta(env)
    # cars.json still wins on the display name, subtitle and order where it states them
    legacy = {}
    mpath = os.path.join(ROOT, env, "cars.json")
    if os.path.isfile(mpath):
        try:
            legacy = json.load(open(mpath, encoding="utf-8"))
        except Exception as e:
            print(f"  ! {env}/cars.json could not be parsed ({e}); using filenames only")
    found = {}
    for fn in sorted(os.listdir(jpg_dir)):
        if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        stem = os.path.splitext(fn)[0]
        if "_" not in stem:
            continue
        slug, fmt = stem.rsplit("_", 1)
        c = found.setdefault(slug, {"slug": slug, "jpg": {}, "svg": {}})
        c["jpg"][fmt] = f"ads/jpg/{fn}"
        svg_name = f"{stem}.svg"
        if os.path.isfile(os.path.join(svg_dir, svg_name)):
            c["svg"][fmt] = f"ads/svg/{svg_name}"
    # attach metadata + ordering, and file each item under its category
    for slug, c in found.items():
        im = meta.get(slug)
        if im and im["status"] != "published":
            continue                      # saved in the admin, deliberately not on the site
        cat_slug = im["catalogue"] if im else DEFAULT_CATALOGUE
        if cat_slug == ORPHAN_CATALOGUE:
            continue                      # its category was deleted; waiting to be reassigned
        cat = by_slug.get(cat_slug)
        if cat is None:
            print(f"  ! {env}: {slug} names catalogue '{cat_slug}', which has no manifest; skipped")
            continue
        m = legacy.get(slug, {})
        c["name"] = m.get("name") or (im["name"] if im else "") or titleize(slug)
        c["subtitle"] = m.get("subtitle", im["subtitle"] if im else "")
        c["order"] = m.get("order", im["order"] if im else 999)
        # cars.json wins if it states them; otherwise read them off the ad
        hero = c["svg"].get("social") or next(iter(c["svg"].values()), None)
        y, pr = ad_facts(os.path.join(ROOT, env, hero)) if hero else (None, None)
        c["year"] = str(m.get("year") or y or "")
        c["price"] = str(m.get("price") or pr or "")
        cat["cars"].append(c)
    for c in cats:
        c["cars"].sort(key=lambda x: (x["order"], x["name"].lower()))
    return renderable(cats, env)

def ad_facts(svg_path):
    """Pull the year and price off a generated ad, so the HTML never restates them by hand.

    The ads print "<year> · <MAKE>" above the model and "$<price>" in the corner flash;
    anything we cannot find just comes back as None and the page omits it."""
    try:
        svg = open(svg_path, encoding="utf-8").read()
    except OSError:
        return None, None
    y = re.search(r">(\d{4})\s*·\s*[^<]+<", svg)
    p = re.search(r">(\$[\d,]+)<", svg)
    return (y.group(1) if y else None), (p.group(1) if p else None)

def fmt_list(car):
    """Known formats first in order, then any extras found."""
    keys = [f for f in FORMAT_ORDER if f in car["jpg"]]
    keys += [f for f in car["jpg"] if f not in keys]
    return keys

def hero_src(car):
    for f in ("social", "landscape", "phone"):
        if f in car["jpg"]:
            return car["jpg"][f]
    return next(iter(car["jpg"].values()), "")

# ---------- contact ----------
PHONE      = "1 613 447 4520"
PHONE_HREF = "tel:+16134474520"
EMAIL      = "omarranwar58@gmail.com"

# Storefront copy. Kept here so the wording lives in one place.
LEDE = ("Pre-owned vehicles for Ottawa drivers, priced to move. Each listing shows the year, "
        "mileage, engine and price up front. Get in touch to ask about a vehicle or to "
        "arrange a viewing.")
APP_LEDE = LEDE

def contact(small=False):
    """Phone + email, shown on the lineup, each vehicle page and each format view."""
    cls = "contact sm" if small else "contact"
    return f"""<div class="{cls}">
      <span class="ct-label">Call or email</span>
      <a class="ct-phone" href="{PHONE_HREF}">{esc(PHONE)}</a>
      <a class="ct-mail" href="mailto:{EMAIL}">{esc(EMAIL)}</a>
    </div>"""

# ---------- HTML fragments ----------
def menu(cats, up, current):
    """Links between the site's categories, for the top bar.

    A category is listed only when it is public, asks to be in the menu, and has at
    least one item with an ad. One entry is not a menu — it is the page you are
    already on — so nothing is emitted until there are two, which is why a site with
    only vehicles configured carries no menu at all.

    up: the path from this page back to its environment root ("" or "../")."""
    shown = [c for c in cats if c["in_menu"] and c["cars"]]
    if len(shown) < 2:
        return ""
    links = ""
    for c in shown:
        route = catalogue_route(c["slug"])
        href = f"{up}{route}/index.html" if route else f"{up}index.html"
        cur = ' aria-current="page"' if c["slug"] == current else ""
        links += f'<a href="{esc(href)}"{cur}>{esc(c["label"])}</a>'
    return f'\n  <nav class="nav" aria-label="Categories">{links}</nav>'

def page(title, body, css_prefix, home, nav=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="Pre-owned vehicle ads — Velocity direction.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="{css_prefix}assets/style.css">
</head>
<body>
<div class="bar"><div class="bar-in">
  <a class="brand" href="{home}"><i></i>Autoline Ads</a>{nav}
</div></div>
{body}
</body>
</html>"""

def crumbs(*parts):
    """parts: (label, href) — href None for the current page."""
    out = []
    for i, (label, href) in enumerate(parts):
        if i:
            out.append('<span class="sep">/</span>')
        if href:
            out.append(f'<a href="{esc(href)}">{esc(label)}</a>')
        else:
            out.append(f'<span aria-current="page">{esc(label)}</span>')
    return f'<nav class="crumbs" aria-label="Breadcrumb">{"".join(out)}</nav>'

def dl_links(car, f, prefix):
    """Download buttons for a format — always both the JPG and, when present, the SVG."""
    out = f'<a class="dl-jpg" href="{prefix}{esc(car["jpg"][f])}" download>Download JPG</a>'
    if f in car["svg"]:
        out += f'<a class="dl-svg" href="{prefix}{esc(car["svg"][f])}" download>Download SVG</a>'
    return out

# ---------- pages ----------
def build_board(cars, css, app=False, heading="The Lineup", lede=None, nav="",
                item_href="cars/", img_prefix="", noun="vehicle", home="index.html"):
    """One category's board. The default category's lives at the site root and at each
    environment folder; any other category's lives in that category's own folder."""
    if not cars:
        board = ('<div class="empty">No vehicles yet. Add image files to <code>ads/jpg/</code> '
                 'and they will appear here automatically.</div>')
    else:
        items = ""
        for c in cars:
            yr = f'<span class="yr">{esc(c["year"])}</span> ' if c["year"] else ""
            sub = esc(c["subtitle"])
            if c["price"]:
                sub = f'{sub} · <span class="price">{esc(c["price"])}</span>' if sub else f'<span class="price">{esc(c["price"])}</span>'
            links = f'<a class="open" href="{item_href}{esc(c["slug"])}.html">{"View" if app else "Open"}</a>'
            if not app:   # app mode has no per-format pages to link to
                for f in fmt_list(c):
                    lbl = FORMAT_LABELS.get(f, (f.title(),))[0]
                    links += f'<a href="{item_href}{esc(c["slug"])}-{esc(f)}.html">{esc(lbl)}</a>'
            items += f"""
        <article class="card">
          <a class="thumb" href="{item_href}{esc(c["slug"])}.html"><img loading="lazy" src="{img_prefix}{esc(hero_src(c))}" alt="{esc(c["name"])} ad"></a>
          <div class="meta">
            <h3>{yr}{esc(c["name"])}</h3>
            <p>{sub}</p>
            <div class="links">{links}</div>
          </div>
        </article>"""
        board = f'<div class="board">{items}\n      </div>'
    body = f"""
  <div class="wrap">
    <header class="hero">
      <p class="eyebrow">Autoline · Pre-Owned</p>
      <h1>{esc(heading)}</h1>
      <p class="lede">{esc(lede) if lede else (APP_LEDE if app else LEDE)}</p>
      {contact()}
    </header>
    {board}
    <footer><span class="brand" style="font-size:14px"><i></i>Autoline</span>
      <span>{len(cars)} {noun}{'s' if len(cars)!=1 else ''} available · updated {datetime.now(timezone.utc).strftime('%d %b %Y')}</span></footer>
  </div>"""
    return page(f"Autoline — {heading}", body, css, home, nav)

def build_car_page(car, css, nav="", board_href="../index.html", board_label="The Lineup"):
    """One item: every format, each opening its own page rather than a bare JPG."""
    title = esc(f'{car["year"]} {car["name"]}'.strip())
    sub = " · ".join(x for x in (car["subtitle"], car["price"]) if x)
    sub = esc(sub)
    blocks = ""
    for f in fmt_list(car):
        lbl, size = FORMAT_LABELS.get(f, (f.title(), ""))
        view = f'{esc(car["slug"])}-{esc(f)}.html'
        blocks += f"""
        <div class="fmt f-{esc(f)}"><figure>
          <a class="shot" href="{view}"><img loading="lazy" src="../{esc(car["jpg"][f])}" alt="{esc(car['name'])} — {esc(lbl)}"></a>
          <figcaption><span class="fl"><a href="{view}">{esc(lbl)}</a></span><span class="fs">{esc(size)}</span>
            <span class="dl">{dl_links(car, f, "../")}</span></figcaption>
        </figure></div>"""
    body = f"""
  <div class="wrap">
    {crumbs((board_label, board_href), (f"{car['year']} {car['name']}".strip(), None))}
    <div class="car-title">
      <div><h1>{title}</h1>
        <p class="lede" style="margin-top:6px">{sub}</p>
        {contact(small=True)}</div>
    </div>
    <div class="formats">{blocks}
    </div>
    <footer><a class="brand" style="font-size:14px" href="{board_href}"><i></i>Back to {esc(board_label.lower())}</a>
      <span>Velocity direction</span></footer>
  </div>"""
    return page(f"{car['year']} {car['name']} — Autoline".strip(), body, css, board_href, nav)

def build_format_page(car, f, css, nav="", board_href="../index.html", board_label="The Lineup"):
    """A single ad format, with breadcrumbs and both downloads."""
    lbl, size = FORMAT_LABELS.get(f, (f.title(), ""))
    others = ""
    for g in fmt_list(car):
        if g == f:
            continue
        glbl = FORMAT_LABELS.get(g, (g.title(),))[0]
        others += f'<a href="{esc(car["slug"])}-{esc(g)}.html">{esc(glbl)}</a>'
    other_block = f'<div class="also"><span>Other formats</span>{others}</div>' if others else ""
    body = f"""
  <div class="wrap">
    {crumbs((board_label, board_href), (f"{car['year']} {car['name']}".strip(), f"{car['slug']}.html"), (lbl, None))}
    <div class="view-head">
      <div><h1>{esc(f"{car['year']} {car['name']}".strip())}</h1>
        <p class="lede" style="margin-top:6px">{esc(lbl)} · {esc(size)}</p></div>
      <div class="view-dl">{dl_links(car, f, "../")}</div>
    </div>
    <div class="viewer f-{esc(f)}">
      <img src="../{esc(car["jpg"][f])}" alt="{esc(car['name'])} — {esc(lbl)}">
    </div>
    {other_block}
    {contact()}
    <footer><a class="brand" style="font-size:14px" href="{esc(car['slug'])}.html"><i></i>Back to {esc(car['name'])}</a>
      <span>{esc(lbl)} · {esc(size)}</span></footer>
  </div>"""
    return page(f"{car['year']} {car['name']} {lbl} — Autoline".strip(), body, css, board_href, nav)

def ad_picture(car, prefix, cls=""):
    """One <picture> that lets the browser fetch only the format its viewport needs."""
    srcs = ""
    for media, f in APP_SOURCES:
        if f in car["jpg"]:
            srcs += f'<source media="{media}" srcset="{prefix}{esc(car["jpg"][f])}">'
    fb = car["jpg"].get(APP_FALLBACK) or hero_src(car)
    alt = esc(f'{car["year"]} {car["name"]}'.strip())
    return (f'<picture class="{cls}">{srcs}'
            f'<img src="{prefix}{esc(fb)}" alt="{alt} ad" loading="eager"></picture>')

def build_app_car_page(car, css, nav="", board_href="../index.html", board_label="The Lineup"):
    """Promo view: the ad at the viewer's own device size, plus one zip of every file."""
    title = esc(f'{car["year"]} {car["name"]}'.strip())
    sub = esc(" · ".join(x for x in (car["subtitle"], car["price"]) if x))
    body = f"""
  <div class="wrap">
    {crumbs((board_label, board_href), (f"{car['year']} {car['name']}".strip(), None))}
    <div class="view-head">
      <div><h1>{title}</h1>
        <p class="lede" style="margin-top:6px">{sub}</p></div>
      <div class="view-dl"><a class="dl-zip" href="{esc(car['slug'])}-ads.zip" download>Download photos &amp; artwork</a></div>
    </div>
    <div class="stage">{ad_picture(car, "../")}</div>
    {contact()}
    <footer><a class="brand" style="font-size:14px" href="{board_href}"><i></i>Back to {esc(board_label.lower())}</a>
      <span>Velocity direction</span></footer>
  </div>"""
    return page(f"{car['year']} {car['name']} — Autoline".strip(), body, css, board_href, nav)

def write_zip(car, env_root, dest):
    """Bundle every file for one vehicle so the promo page can hand over all of them at once."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for kind in ("jpg", "svg"):
            for f, rel in sorted(car[kind].items()):
                src = os.path.join(env_root, rel)
                if os.path.isfile(src):
                    z.write(src, os.path.join(car["slug"], os.path.basename(rel)))

# ---------- emit ----------
def emit(cat, out_dir, css_env, cats, app=False, env_root=None):
    """Write one category's board and item pages into an environment's output folder.

    The default category is the environment: its board is out_dir/index.html and its
    items live in out_dir/cars/. Any other category gets out_dir/<slug>/, holding both
    its board and its item pages — one level under the environment root either way, so
    the ads are always ../ads/ from an item page.

    app=True builds the promotional variant: one responsive ad per item and a zip of
    its files, instead of a page per format."""
    route = catalogue_route(cat["slug"])
    default = not route
    board_dir = out_dir if default else os.path.join(out_dir, route)
    items_dir = os.path.join(out_dir, "cars") if default else board_dir
    os.makedirs(items_dir, exist_ok=True)

    up = "" if default else "../"          # from the board back to the environment root
    label = cat["heading"]
    board_href = "../index.html" if default else "index.html"
    item_href = "cars/" if default else ""
    cars = cat["cars"]

    open(os.path.join(board_dir, "index.html"), "w", encoding="utf-8").write(
        build_board(cars, css_env + up, app,
                    heading=label, lede=cat["lede"] or None,
                    nav=menu(cats, up, cat["slug"]), item_href=item_href,
                    img_prefix=up, noun=singular(cat["label"]), home=up + "index.html"))

    css_item = css_env + "../"
    nav_item = menu(cats, "../", cat["slug"])
    for c in cars:
        if app:
            open(os.path.join(items_dir, f"{c['slug']}.html"), "w", encoding="utf-8").write(
                build_app_car_page(c, css_item, nav_item, board_href, label))
            write_zip(c, env_root, os.path.join(items_dir, f"{c['slug']}-ads.zip"))
        else:
            open(os.path.join(items_dir, f"{c['slug']}.html"), "w", encoding="utf-8").write(
                build_car_page(c, css_item, nav_item, board_href, label))
            for f in fmt_list(c):
                open(os.path.join(items_dir, f"{c['slug']}-{f}.html"), "w", encoding="utf-8").write(
                    build_format_page(c, f, css_item, nav_item, board_href, label))

def emit_env(cats, out_dir, css_env, app=False, env_root=None):
    """Every category of one environment, plus the guarantee that its root has a board."""
    for cat in cats:
        emit(cat, out_dir, css_env, cats, app=app, env_root=env_root)
    # The environment root is the URL a client is given, so it always has a board —
    # even in the odd case where the default category has been taken off the site.
    if not any(catalogue_route(c["slug"]) == "" for c in cats):
        open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(
            build_board([], css_env, app, nav=menu(cats, "", None)))

def tally(cats):
    """"vehicles 5, tyres 1" — what got built, for the console."""
    return ", ".join(f"{c['slug']} {len(c['cars'])}" for c in cats) or "nothing"

def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    found = {key: scan_env(key) for key, _ in ENVS}

    # Site root: a complete copy of PUBLIC_ENV, so a client opening the bare URL
    # never sees an environment name in the page text or in any path.
    root_cats = found.get(PUBLIC_ENV, [])
    src_ads = os.path.join(ROOT, PUBLIC_ENV, "ads")
    if os.path.isdir(src_ads):
        shutil.copytree(src_ads, os.path.join(OUT, "ads"))
    emit_env(root_cats, OUT, "", app=PUBLIC_ENV in APP_ENVS,
             env_root=os.path.join(ROOT, PUBLIC_ENV))
    print(f"  root: {tally(root_cats)} (from {PUBLIC_ENV})"
          f"{' (responsive app)' if PUBLIC_ENV in APP_ENVS else ''}")

    # Each environment keeps its own URL so direct links stay valid.
    for key, _ in ENVS:
        cats = found[key]
        env_out = os.path.join(OUT, key)
        os.makedirs(env_out, exist_ok=True)
        src = os.path.join(ROOT, key, "ads")
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(env_out, "ads"))
        emit_env(cats, env_out, "../", app=key in APP_ENVS,
                 env_root=os.path.join(ROOT, key))
        print(f"  {key}: {tally(cats)}{' (responsive app)' if key in APP_ENVS else ''}")

    print(f"Built -> {OUT}")

if __name__ == "__main__":
    main()
