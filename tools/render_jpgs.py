#!/usr/bin/env python3
"""Render every SVG in output/svg/ to a JPG in output/jpg/ (headless Chromium).
Setup:  pip install playwright  &&  playwright install chromium
Run:    python render_jpgs.py        (from the tools/ folder)"""
import glob, os
from playwright.sync_api import sync_playwright
HERE=os.path.dirname(os.path.abspath(__file__))
svgdir=os.path.join(HERE,"output","svg"); jpgdir=os.path.join(HERE,"output","jpg")
os.makedirs(jpgdir,exist_ok=True)
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
