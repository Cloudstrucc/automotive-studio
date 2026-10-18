# tools — ad generator

Regenerates the Velocity ad files. Use this when you need to change what is **printed on**
an ad (year, price, mileage, contact, trim) — the website only handles whole image files.

## What's here
- `gen_velocity.py`  — builds the 15 SVG ads (5 cars × 3 formats) into `output/svg/`.
- photos and copy both come from `<env>/manifests/items/<catalogue>/<slug>.json` and
  `<env>/source-photos/…` — the same files the admin writes.
- `render_jpgs.py`   — renders those SVGs to JPGs in `output/jpg/`.
- `requirements.txt` — pinned dependencies, so a rebuild months from now matches today's.
- `regen.sh`         — does all of the above in one command.

## Change a price / year / mileage
Edit the item's manifest — `<env>/manifests/items/vehicles/<slug>.json` — then regenerate.
The admin does exactly this; editing the file by hand is the same operation.

## Change the contact details
1. Edit `PHONE` / `EMAIL` at the top of `gen_velocity.py`.
2. From the repo root:
   ```bash
   ./tools/regen.sh production review development
   ```
3. Review the diff, commit and push — the site redeploys automatically.

That's the whole setup. `regen.sh` creates `tools/.venv` on first run, installs the pinned
Playwright and its Chromium, renders everything, and copies the results into whichever
environments you name. Run it with no arguments to build into `tools/output/` without
touching the site.

First run takes about a minute while Chromium downloads; after that it is ~20 seconds.

> **Don't `pip install playwright` into your system Python.** That is what `regen.sh` avoids:
> the venv keeps the pinned version with the project, so regeneration does not depend on
> what happens to be on your `PATH` that day.

## Reproducibility
Rendering is deterministic: re-running `regen.sh` without editing `gen_velocity.py` produces
byte-identical SVGs and JPGs. If a run shows unexpected diffs, the Playwright version moved —
check `requirements.txt` against `tools/.venv/bin/pip freeze`.

## Adding a vehicle
Write a manifest at `<env>/manifests/items/vehicles/<slug>.json` and put its photos
where the manifest's `images[].file` paths point — normally
`<env>/source-photos/vehicles/<slug>/1.jpg`. Then regenerate.

Fields the ad draws: `year`, `make`, `model`, `subtitle`, `price`, `eyebrow` (the
corner badge), `kicker` (the small line under it), and the first three `specs`
entries as the three columns. Aspect ratios are read from the JPEGs.

`background` is optional — a small, heavily downscaled copy used as the frame-filling
backdrop. Without one the first shot stands in, since it is blurred and veiled anyway.

An item is only rendered when `"status": "published"` and it has at least one image.
