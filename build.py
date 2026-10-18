#!/usr/bin/env python3
"""
Static site generator for the Autoline vehicle-ad portal.

It scans each environment folder (production / review / development) for the
images actually present and builds the pages from them — so adding, updating or
deleting an image file is all it takes. No code changes needed for CRUD.

Run locally:  python build.py        -> outputs the site into ./_site
In CI:        the GitHub Actions workflow runs this, then deploys ./_site.
"""
import json, os, shutil, html, re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(ROOT, "_site")
ENVS = [
    ("production",  "Production", "Live ads approved for publishing."),
    ("review",      "Review (UAT)", "Awaiting client / stakeholder sign-off."),
    ("development", "Development", "Work in progress — not for sharing yet."),
]
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
        out.append(c)
    out.sort(key=lambda c: (c["order"], c["name"].lower()))
    return out

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

# ---------- HTML fragments ----------
def page(title, body, css_prefix, nav_html):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="Pre-owned vehicle ad concepts — Velocity direction.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="{css_prefix}assets/style.css">
</head>
<body>
<div class="bar"><div class="bar-in">
  <a class="brand" href="{css_prefix}index.html"><i></i>Autoline Ads</a>
  <nav>{nav_html}</nav>
</div></div>
{body}
</body>
</html>"""

def env_nav(current, prefix):
    out = []
    for key, label, _ in ENVS:
        cls = "here" if key == current else ""
        out.append(f'<a class="{cls}" href="{prefix}{key}/index.html">{esc(label)}</a>')
    return "".join(out)

def build_landing(found):
    cards = ""
    for key, label, desc in ENVS:
        cars = found.get(key, [])
        cards += f"""
      <a class="env-card {key}" href="{key}/index.html">
        <span class="badge {key}">{esc(label)}</span>
        <h2>{esc(label)}</h2>
        <p>{esc(desc)}</p>
        <span class="count">{len(cars)} vehicle{'s' if len(cars)!=1 else ''}</span> &nbsp;·&nbsp;
        <span class="go">Open →</span>
      </a>"""
    body = f"""
  <div class="wrap">
    <header class="hero">
      <p class="eyebrow">Autoline · Vehicle Ad Portal</p>
      <h1>Pre-Owned<br>Ad Portal</h1>
      <p class="lede">Velocity-direction ads for the current lineup, across three environments. Pick an environment to browse the vehicles, preview each format, and download the files.</p>
      <div class="note"><b>Environments.</b> <b>Development</b> is the working copy, <b>Review</b> is what you share for sign-off, and <b>Production</b> is the approved, publish-ready set. Each updates automatically whenever its folder changes.</div>
    </header>
    <div class="envs">{cards}
    </div>
    <footer><span class="brand" style="font-size:14px"><i></i>Autoline Studio</span>
      <span>Velocity direction · updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</span></footer>
  </div>"""
    return page("Autoline — Vehicle Ad Portal", body, "", env_nav(None, ""))

def build_env_index(key, label, desc, cars):
    nav = env_nav(key, "../")
    if not cars:
        board = '<div class="empty">No vehicles in this environment yet. Add image files to <code>'+key+'/ads/jpg/</code> and they will appear here automatically.</div>'
    else:
        items = ""
        for c in cars:
            links = f'<a class="open" href="cars/{esc(c["slug"])}.html">Open</a>'
            for f in fmt_list(c):
                lbl = FORMAT_LABELS.get(f, (f.title(),))[0]
                links += f'<a href="{esc(c["jpg"][f])}" download>{esc(lbl)}</a>'
            items += f"""
        <article class="card">
          <a class="thumb" href="cars/{esc(c["slug"])}.html"><img loading="lazy" src="{esc(hero_src(c))}" alt="{esc(c["name"])} ad"></a>
          <div class="meta">
            <h3>{esc(c["name"])}</h3>
            <p>{esc(c["subtitle"])}</p>
            <div class="links">{links}</div>
          </div>
        </article>"""
        board = f'<div class="board">{items}\n      </div>'
    body = f"""
  <div class="wrap">
    <header class="hero">
      <span class="badge {key}">{esc(label)}</span>
      <h1 style="margin-top:14px">The Lineup</h1>
      <p class="lede">{esc(desc)} Tap a vehicle to see all three ad formats and download the files. Every card is a complete ad — price, mileage and contact are on the image.</p>
    </header>
    {board}
    <footer><a class="brand" style="font-size:14px" href="../index.html"><i></i>All environments</a>
      <span>{len(cars)} vehicle{'s' if len(cars)!=1 else ''} · updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</span></footer>
  </div>"""
    return page(f"Autoline — {label}", body, "../", nav)

def build_car_page(key, label, car):
    nav = env_nav(key, "../../")
    blocks = ""
    for f in fmt_list(car):
        lbl, size = FORMAT_LABELS.get(f, (f.title(), ""))
        jpg = car["jpg"][f]
        svg = car["svg"].get(f)
        dl = f'<a href="../{esc(jpg)}" download>JPG</a>'
        if svg:
            dl += f'<a class="svg" href="../{esc(svg)}" download>SVG</a>'
        blocks += f"""
        <div class="fmt f-{esc(f)}"><figure>
          <a class="shot" href="../{esc(jpg)}" target="_blank" rel="noopener"><img loading="lazy" src="../{esc(jpg)}" alt="{esc(car['name'])} — {esc(lbl)}"></a>
          <figcaption><span class="fl">{esc(lbl)}</span><span class="fs">{esc(size)}</span>
            <span class="dl">{dl}</span></figcaption>
        </figure></div>"""
    body = f"""
  <div class="wrap">
    <p class="crumb"><a href="index.html">← {esc(label)}</a></p>
    <div class="car-title">
      <div><span class="badge {key}">{esc(label)}</span>
        <h1 style="margin-top:12px">{esc(car['name'])}</h1>
        <p class="lede" style="margin-top:6px">{esc(car['subtitle'])}</p></div>
    </div>
    <div class="formats">{blocks}
    </div>
    <footer><a class="brand" style="font-size:14px" href="index.html"><i></i>Back to {esc(label)}</a>
      <span>Velocity direction</span></footer>
  </div>"""
    return page(f"{car['name']} — Autoline {label}", body, "../../", nav)

def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    # shared assets + jekyll bypass
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    found = {}
    for key, label, desc in ENVS:
        found[key] = scan_env(key)

    # landing
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(build_landing(found))

    # each environment
    for key, label, desc in ENVS:
        cars = found[key]
        env_out = os.path.join(OUT, key)
        os.makedirs(os.path.join(env_out, "cars"), exist_ok=True)
        # copy this env's ad files
        src_ads = os.path.join(ROOT, key, "ads")
        if os.path.isdir(src_ads):
            shutil.copytree(src_ads, os.path.join(env_out, "ads"))
        open(os.path.join(env_out, "index.html"), "w", encoding="utf-8").write(build_env_index(key, label, desc, cars))
        for c in cars:
            open(os.path.join(env_out, "cars", f"{c['slug']}.html"), "w", encoding="utf-8").write(build_car_page(key, label, c))
        print(f"  {key}: {len(cars)} vehicles")

    print(f"Built -> {OUT}")

if __name__ == "__main__":
    main()
