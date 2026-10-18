#!/usr/bin/env python3
"""
Static site generator for the Autoline vehicle-ad portal.

It scans each environment folder (production / review / development) for the
images actually present and builds the pages from them — so adding, updating or
deleting an image file is all it takes. No code changes needed for CRUD.

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

def scan_env(env):
    """Return an ordered list of cars discovered from the env's ad images."""
    jpg_dir = os.path.join(ROOT, env, "ads", "jpg")
    svg_dir = os.path.join(ROOT, env, "ads", "svg")
    if not os.path.isdir(jpg_dir):
        return []
    # metadata (optional)
    meta = {}
    mpath = os.path.join(ROOT, env, "cars.json")
    if os.path.isfile(mpath):
        try:
            meta = json.load(open(mpath, encoding="utf-8"))
        except Exception as e:
            print(f"  ! {env}/cars.json could not be parsed ({e}); using filenames only")
    cars = {}
    for fn in sorted(os.listdir(jpg_dir)):
        if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        stem = os.path.splitext(fn)[0]
        if "_" not in stem:
            continue
        slug, fmt = stem.rsplit("_", 1)
        c = cars.setdefault(slug, {"slug": slug, "jpg": {}, "svg": {}})
        c["jpg"][fmt] = f"ads/jpg/{fn}"
        svg_name = f"{stem}.svg"
        if os.path.isfile(os.path.join(svg_dir, svg_name)):
            c["svg"][fmt] = f"ads/svg/{svg_name}"
    # attach metadata + ordering
    out = []
    for slug, c in cars.items():
        m = meta.get(slug, {})
        c["name"] = m.get("name") or titleize(slug)
        c["subtitle"] = m.get("subtitle", "")
        c["order"] = m.get("order", 999)
        # cars.json wins if it states them; otherwise read them off the ad
        hero = c["svg"].get("social") or next(iter(c["svg"].values()), None)
        y, pr = ad_facts(os.path.join(ROOT, env, hero)) if hero else (None, None)
        c["year"] = str(m.get("year") or y or "")
        c["price"] = str(m.get("price") or pr or "")
        out.append(c)
    out.sort(key=lambda c: (c["order"], c["name"].lower()))
    return out

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

LEDE = ("Every card is a complete ad — price, mileage and contact are printed on the image. "
        "Open a vehicle to preview each format and download the files.")
APP_LEDE = ("Every card is a complete ad — price, mileage and contact are printed on the image. "
            "Open a vehicle to see it sized for the screen you are on, and download the files.")

def contact(small=False):
    """Phone + email, shown on the lineup, each vehicle page and each format view."""
    cls = "contact sm" if small else "contact"
    return f"""<div class="{cls}">
      <span class="ct-label">Call or email</span>
      <a class="ct-phone" href="{PHONE_HREF}">{esc(PHONE)}</a>
      <a class="ct-mail" href="mailto:{EMAIL}">{esc(EMAIL)}</a>
    </div>"""

# ---------- HTML fragments ----------
def page(title, body, css_prefix, home):
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
  <a class="brand" href="{home}"><i></i>Autoline Ads</a>
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
def build_board(cars, css, app=False):
    """The lineup. Lives at the site root and at each environment folder."""
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
            links = f'<a class="open" href="cars/{esc(c["slug"])}.html">{"View" if app else "Open"}</a>'
            if not app:   # app mode has no per-format pages to link to
                for f in fmt_list(c):
                    lbl = FORMAT_LABELS.get(f, (f.title(),))[0]
                    links += f'<a href="cars/{esc(c["slug"])}-{esc(f)}.html">{esc(lbl)}</a>'
            items += f"""
        <article class="card">
          <a class="thumb" href="cars/{esc(c["slug"])}.html"><img loading="lazy" src="{esc(hero_src(c))}" alt="{esc(c["name"])} ad"></a>
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
      <h1>The Lineup</h1>
      <p class="lede">{APP_LEDE if app else LEDE}</p>
      {contact()}
    </header>
    {board}
    <footer><span class="brand" style="font-size:14px"><i></i>Autoline</span>
      <span>{len(cars)} vehicle{'s' if len(cars)!=1 else ''} · updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</span></footer>
  </div>"""
    return page("Autoline — The Lineup", body, css, "index.html")

def build_car_page(car, css):
    """One vehicle: every format, each opening its own page rather than a bare JPG."""
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
    {crumbs(("The Lineup", "../index.html"), (f"{car['year']} {car['name']}".strip(), None))}
    <div class="car-title">
      <div><h1>{title}</h1>
        <p class="lede" style="margin-top:6px">{sub}</p>
        {contact(small=True)}</div>
    </div>
    <div class="formats">{blocks}
    </div>
    <footer><a class="brand" style="font-size:14px" href="../index.html"><i></i>Back to the lineup</a>
      <span>Velocity direction</span></footer>
  </div>"""
    return page(f"{car['year']} {car['name']} — Autoline".strip(), body, css, "../index.html")

def build_format_page(car, f, css):
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
    {crumbs(("The Lineup", "../index.html"), (f"{car['year']} {car['name']}".strip(), f"{car['slug']}.html"), (lbl, None))}
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
    return page(f"{car['year']} {car['name']} {lbl} — Autoline".strip(), body, css, "../index.html")

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

def build_app_car_page(car, css):
    """Promo view: the ad at the viewer's own device size, plus one zip of every file."""
    title = esc(f'{car["year"]} {car["name"]}'.strip())
    sub = esc(" · ".join(x for x in (car["subtitle"], car["price"]) if x))
    n = sum(len(car[k]) for k in ("jpg", "svg"))
    body = f"""
  <div class="wrap">
    {crumbs(("The Lineup", "../index.html"), (f"{car['year']} {car['name']}".strip(), None))}
    <div class="view-head">
      <div><h1>{title}</h1>
        <p class="lede" style="margin-top:6px">{sub}</p></div>
      <div class="view-dl"><a class="dl-zip" href="{esc(car['slug'])}-ads.zip" download>Download images ({n} files)</a></div>
    </div>
    <div class="stage">{ad_picture(car, "../")}</div>
    {contact()}
    <footer><a class="brand" style="font-size:14px" href="../index.html"><i></i>Back to the lineup</a>
      <span>Velocity direction</span></footer>
  </div>"""
    return page(f"{car['year']} {car['name']} — Autoline".strip(), body, css, "../index.html")

def write_zip(car, env_root, dest):
    """Bundle every file for one vehicle so the promo page can hand over all of them at once."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for kind in ("jpg", "svg"):
            for f, rel in sorted(car[kind].items()):
                src = os.path.join(env_root, rel)
                if os.path.isfile(src):
                    z.write(src, os.path.join(car["slug"], os.path.basename(rel)))

# ---------- emit ----------
def emit(cars, out_dir, css_board, css_car, app=False, env_root=None):
    """Write a complete, self-contained lineup into out_dir.

    app=True builds the promotional variant: one responsive ad per vehicle and a zip
    of its files, instead of a page per format."""
    cars_dir = os.path.join(out_dir, "cars")
    os.makedirs(cars_dir, exist_ok=True)
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(build_board(cars, css_board, app))
    for c in cars:
        if app:
            open(os.path.join(cars_dir, f"{c['slug']}.html"), "w", encoding="utf-8").write(build_app_car_page(c, css_car))
            write_zip(c, env_root, os.path.join(cars_dir, f"{c['slug']}-ads.zip"))
        else:
            open(os.path.join(cars_dir, f"{c['slug']}.html"), "w", encoding="utf-8").write(build_car_page(c, css_car))
            for f in fmt_list(c):
                open(os.path.join(cars_dir, f"{c['slug']}-{f}.html"), "w", encoding="utf-8").write(build_format_page(c, f, css_car))

def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    found = {key: scan_env(key) for key, _ in ENVS}

    # Site root: a complete copy of PUBLIC_ENV, so a client opening the bare URL
    # never sees an environment name in the page text or in any path.
    root_cars = found.get(PUBLIC_ENV, [])
    src_ads = os.path.join(ROOT, PUBLIC_ENV, "ads")
    if os.path.isdir(src_ads):
        shutil.copytree(src_ads, os.path.join(OUT, "ads"))
    emit(root_cars, OUT, "", "../",
         app=PUBLIC_ENV in APP_ENVS, env_root=os.path.join(ROOT, PUBLIC_ENV))
    print(f"  root: {len(root_cars)} vehicles (from {PUBLIC_ENV})"
          f"{' (responsive app)' if PUBLIC_ENV in APP_ENVS else ''}")

    # Each environment keeps its own URL so direct links stay valid.
    for key, _ in ENVS:
        cars = found[key]
        env_out = os.path.join(OUT, key)
        os.makedirs(env_out, exist_ok=True)
        src = os.path.join(ROOT, key, "ads")
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(env_out, "ads"))
        emit(cars, env_out, "../", "../../", app=key in APP_ENVS, env_root=os.path.join(ROOT, key))
        print(f"  {key}: {len(cars)} vehicles{' (responsive app)' if key in APP_ENVS else ''}")

    print(f"Built -> {OUT}")

if __name__ == "__main__":
    main()
