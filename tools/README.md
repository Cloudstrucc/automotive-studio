# tools — ad generator

Regenerates the Velocity ad files. Use this when you need to change what is **printed on**
an ad (price, mileage, phone number, trim) — the website CRUD only handles whole image files.

## What's here
- `gen_velocity.py`  — builds the 15 SVG ads (5 cars × 3 formats) into `output/svg/`.
- `velocity_imgs.json` — the embedded car photos (blurred background + sharp shots).
- `render_jpgs.py`   — renders those SVGs to JPGs in `output/jpg/`.

## Change a price / mileage / contact
1. Edit the `CARS` dict in `gen_velocity.py` (km, price, trim) and/or the footer/contact text.
2. From this folder:
   ```bash
   python gen_velocity.py
   pip install playwright && playwright install chromium   # first time only
   python render_jpgs.py
   ```
3. Copy the files you want from `output/svg` and `output/jpg` into the target environment,
   e.g. `../production/ads/svg/` and `../production/ads/jpg/`.
4. Commit & push — the site redeploys automatically.

> Adding brand-new photos means adding entries to `velocity_imgs.json` (base64 data URIs).
> Ask Claude Code to help with that step.
