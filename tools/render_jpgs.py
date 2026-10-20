#!/usr/bin/env python3
"""Render SVGs from output/svg/ to JPGs in output/jpg/ (headless Chromium).

    python render_jpgs.py                      every SVG in output/svg/
    python render_jpgs.py santafe_phone ...    only the ads named

Rendering is the slow, non-reproducible half of the pipeline -- the webfonts land a
little differently each time -- so sync_ads.py names the handful of ads whose SVG
actually changed rather than letting this rewrite all of them.

Setup:  pip install playwright  &&  playwright install chromium
Run:    from the tools/ folder"""
import glob, os, sys
from playwright.sync_api import sync_playwright
HERE=os.path.dirname(os.path.abspath(__file__))
svgdir=os.path.join(HERE,"output","svg"); jpgdir=os.path.join(HERE,"output","jpg")
os.makedirs(jpgdir,exist_ok=True)
if sys.argv[1:]:
    files=[os.path.join(svgdir,n+".svg") for n in sys.argv[1:]]
    missing=[f for f in files if not os.path.isfile(f)]
    if missing: raise SystemExit("no such svg: "+", ".join(os.path.basename(f) for f in missing))
else:
    files=sorted(glob.glob(os.path.join(svgdir,"*.svg")))
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(device_scale_factor=1)
    for f in files:
        name=os.path.splitext(os.path.basename(f))[0]
        pg.set_content(f'<body style="margin:0;padding:0">{open(f).read()}</body>')
        pg.wait_for_timeout(600)
        pg.query_selector("svg").screenshot(path=os.path.join(jpgdir,name+".jpg"),type="jpeg",quality=92)
    b.close()
print("rendered",len(files),"jpgs ->",jpgdir)
