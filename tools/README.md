# tools — ad generator

Regenerates the Velocity ad files. Use this when you need to change what is **printed on**
an ad (year, price, mileage, contact, trim) — the website only handles whole image files.

## What's here
- `gen_velocity.py`  — builds the 15 SVG ads (5 cars × 3 formats) into `output/svg/`.
- photos and copy both come from `<env>/manifests/items/<catalogue>/<slug>.json` and
  `<env>/source-photos/…` — the same files the admin writes.
- `render_jpgs.py`   — renders SVGs to JPGs in `output/jpg/`; names an ad to render just that one.
- `sync_ads.py`      — compares the generated SVGs with the ones committed in an environment,
  renders only the ads that differ, copies those across, and deletes ads whose item is gone.
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
Playwright and its Chromium, then for each environment you name renders the ads that
changed and copies them in. Run it with no arguments to render everything into
`tools/output/` without touching any environment.

First run takes about a minute while Chromium downloads. After that it is a second or two
when nothing changed, and a few seconds per vehicle you edited.

> **Don't `pip install playwright` into your system Python.** That is what `regen.sh` avoids:
> the venv keeps the pinned version with the project, so regeneration does not depend on
> what happens to be on your `PATH` that day.

## Reproducibility
**Re-running `regen.sh` without changing anything produces an empty diff.** That is the
guarantee worth having, and it is worth knowing how it is kept, because it is not that the
renderer is reproducible.

SVG generation *is* deterministic: the same manifest always writes the same bytes. JPEG
rendering is not — headless Chromium loads the Google webfonts a little differently each
time, so re-rendering an untouched ad yields a JPG that differs by a fraction of a percent.
Nothing can be done about that from this end, and trying to make the encoder bit-exact is
the wrong end of the problem.

So the SVGs are used as the signal instead. `sync_ads.py` compares each freshly generated
SVG with the one committed at `<env>/ads/svg/`, and an ad whose SVG matches is left
completely alone: not rendered, not copied, byte-for-byte the file already in git. Only the
ads that genuinely changed are re-rendered. Edit one vehicle's price and exactly that
vehicle's three SVGs and three JPGs change.

Two things follow. CI's "Re-render ads" commits now appear only when an ad really changed,
rather than rewriting all 15 on every manifest edit, and two people regenerating at once no
longer collide over binary files they both happened to rewrite. The practical cost is that a
*revert* does not restore a JPG's original bytes — going back changes the SVG back, which
means a fresh render — so `git checkout <env>/ads` is the way to undo an unwanted
regeneration.

If a run reports ads rendered when you changed nothing, the generator's output moved: diff
`tools/output/svg/` against `<env>/ads/svg/` to see what, and check `requirements.txt`
against `tools/.venv/bin/pip freeze`.

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
