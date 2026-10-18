# CLAUDE.md — Autoline Vehicle Ad Portal

Project memory for Claude Code. Read this first when working in this repo.

## What this repo is
A self-building GitHub Pages site that publishes pre-owned vehicle ads (the **Velocity** design
direction) across **three environments** from a single repo. A GitHub Actions workflow rebuilds and
redeploys on every push.

- 🟢 `production/` — approved, publish-ready ads → `/<repo>/production/`
- 🟠 `review/` — shared with the client for sign-off (UAT) → `/<repo>/review/`
- 🔵 `development/` — work in progress → `/<repo>/development/`
- `/<repo>/` is a **complete copy of `production/`**, so a client opening the bare URL never sees
  an environment name in the text or in any path. Share the other two by direct link.

**The site never names an environment.** No badges, no labels, no "Production" in a title or
crumb — every board is just "The Lineup". The folder names survive only in URLs and in `ENVS`
in `build.py`; `PUBLIC_ENV` there picks which one the root mirrors. Keep it that way when adding
pages.

Owner: Fred Pearson (CloudStrucc). Market: Ottawa / Ontario. Contact printed on ads: **1 613 447 4520**
and **omarranwar58@gmail.com**.

## How the site is generated
- `build.py` (Python stdlib only) scans each environment's `ads/jpg/` folder, groups files by
  vehicle, and generates, for the root and for each environment: a lineup board, a page per
  vehicle, and a page per vehicle *per format* (`cars/<id>-<format>.html`).
- Clicking an ad opens its format page — breadcrumbed, with JPG **and** SVG download buttons —
  rather than dumping the raw JPG into a bare tab.
- **App mode** (`APP_ENVS` in `build.py` — currently every environment, and the root follows
  `PUBLIC_ENV`) builds a promo webapp instead of a format gallery: one vehicle page showing a single ad chosen by viewport via
  `<picture>` (landscape ≥900px, social ≥560px, phone below — see `APP_SOURCES`), so a phone
  fetches only the phone ad. No per-format pages; the board's cards say *View*, not *Open*.
  Each vehicle also gets `cars/<id>-ads.zip`, built by `write_zip()`, holding its JPGs and SVGs.
- Year and price shown in HTML are **parsed out of the ad SVG** by `ad_facts()`, so the image
  stays the single source of truth. `cars.json` may override either.
- `.github/workflows/deploy.yml` runs `build.py` on every push to `main` and deploys `_site/` to Pages.
- `assets/style.css` is the shared stylesheet (Velocity dark theme). Edit the look here.
- `_site/` is build output — **never commit it** (see `.gitignore`).

## The one hard rule: file naming
Ad images live in `<env>/ads/jpg/` named **`<vehicleId>_<format>.jpg`**, with matching optional
SVGs in `<env>/ads/svg/`:
- Everything before the **last** underscore is the vehicle id (`buick`, `santafe`, `elantra`…).
- Format is `social` (4:5, 1080×1350), `phone` (9:19.5, 1080×2340), or `landscape` (16:9, 1920×1080).
- `<env>/cars.json` maps a vehicle id → `{name, subtitle, order}`, plus optional `year` / `price`
  overrides (ids default to title-case; year and price otherwise come from the SVG).

## Current lineup (display order; set by `order` in each env's cars.json)
| id | Year | Vehicle | KM | Price |
|---|--:|---|--:|--:|
| santafe | 2017 | Hyundai Santa Fe Sport 2.4L | 107,000 | $14,000 |
| buick | 2013 | Buick LaCrosse Premium | 83,000 | $11,500 |
| elantra | 2016 | Hyundai Elantra GT GLS | 96,000 | $12,000 |
| sienna | 2016 | Toyota Sienna LE | 165,000 | $18,000 |
| mercedes | 2014 | Mercedes-Benz E 350 4MATIC | 126,000 | $17,900 |

Model years are set (no placeholders left). Dealer name was removed; contact printed on the ads is the phone
number **and** the email **omarranwar58@gmail.com** — both also appear on the landing page, each lineup board
and each vehicle page. Phone/email live as constants in `build.py` and `tools/gen_velocity.py`.

## Common tasks
- **Preview locally:** `python build.py` → open `_site/index.html`.
- **Add a vehicle:** add `ads/jpg/<id>_social.jpg` (+ phone/landscape, + svgs) to the env, add a line
  to that env's `cars.json`, commit & push.
- **Update a vehicle:** replace its image files, commit & push.
- **Remove a sold vehicle:** delete its files from `ads/jpg/` (and `ads/svg/`), commit & push.
- **Promote:** copy a vehicle's files from `development/` → `review/` → `production/`.
- **Change what's printed on an ad** (price, km, contact): use `tools/` — see `tools/README.md`.
  Edit `tools/gen_velocity.py` `CARS`, run `gen_velocity.py` then `render_jpgs.py`, copy outputs into
  the env folder.

## Design direction (Velocity)
- Dark stage, electric-green accent `#19e36a`; condensed display face **Archivo**, body **Inter**.
- Full vehicle always visible (photos composited on a blurred same-photo background; never cropped).
- Vehicles with multiple photos stack two angles (front+rear vertical, side-by-side on landscape).

## Conventions
- Keep `build.py` dependency-free (stdlib only) so CI stays simple.
- The ad JPGs/SVGs are the source of truth for on-image text; don't duplicate price/km in HTML.
- Don't commit `_site/`, `tools/output/`, or `__pycache__/`.
