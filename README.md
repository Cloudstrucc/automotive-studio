# Autoline — Vehicle Ad Portal

A self-updating GitHub Pages site for pre-owned vehicle ads (Velocity design direction).
Drop image files into a folder, push, and the site rebuilds itself — no code changes needed.

It publishes **three environments** from one repository:

| Environment | Folder | Purpose | Live URL (after setup) |
|---|---|---|---|
| 🟢 **Production** | `production/` | Approved, publish-ready ads | `https://cloudstrucc.github.io/<repo-name>/production/` |
| 🟠 **Review (UAT)** | `review/` | Shared with the client for sign-off | `https://cloudstrucc.github.io/<repo-name>/review/` |
| 🔵 **Development** | `development/` | Work in progress | `https://cloudstrucc.github.io/<repo-name>/development/` |

Landing page linking to all three: `https://cloudstrucc.github.io/<repo-name>/`

Each environment has a **lineup page** (an infographic board of every vehicle) and a **page per
vehicle** showing all three ad formats with direct **JPG** and **SVG** download links. Everything is
responsive — phone, tablet and desktop.

---

## How it updates automatically

A GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on **every push**. It runs
`build.py`, which **scans each environment's `ads/jpg/` folder** and generates the pages from
whatever images are present, then deploys the result to GitHub Pages. So:

- **Add a vehicle** → drop its image files into the folder → it appears on the site.
- **Update a vehicle** → replace its image files → the site shows the new version.
- **Delete a vehicle** (e.g. sold) → delete its image files → it disappears from the site.

No pipeline knowledge required — just add/replace/delete files and the site follows.

### File naming (this is the only rule)

Image files are named **`<vehicle>_<format>.jpg`**:

```
production/ads/jpg/buick_social.jpg      ← Toyota ... Buick etc.
production/ads/jpg/buick_phone.jpg
production/ads/jpg/buick_landscape.jpg
production/ads/svg/buick_social.svg      ← matching SVG (optional, same name)
```

- Everything before the **last** underscore is the vehicle id (`buick`, `santafe`, `elantra`…).
- The part after it is the format: `social` (4:5), `phone` (9:19.5), or `landscape` (16:9).
- A matching `.svg` in `ads/svg/` with the same name is offered as an extra download.

### Nice names & ordering (optional)

Each environment has a `cars.json` that maps a vehicle id to a display name, subtitle and sort
order. It's **optional** — if a vehicle isn't listed, the site just title-cases its id. To add a new
car cleanly, drop its images **and** add a line to that environment's `cars.json`:

```json
{
  "buick": { "name": "Buick LaCrosse", "subtitle": "Premium · Leather", "order": 5 }
}
```

> Prices, mileage and the phone number are printed **on the ad images themselves**, so the site
> doesn't need them in `cars.json`.

---

## The promotion flow

Work in **development** → copy the approved files into **review** to share with the client →
copy them into **production** once signed off. Each folder is independent, so the three URLs can
show different versions at the same time.

---

## One-time setup (≈ 3 minutes)

### Option A — GitHub website (no git needed)

1. Go to **https://github.com/cloudstrucc** → **New repository**.
2. Name it (e.g. `autoline-vehicle-ads`), set **Public**, click **Create repository**.
3. On the new repo page → **uploading an existing file** → drag in **everything from this folder**
   (keep the folder structure) → **Commit changes**.
4. Go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
5. Open the **Actions** tab — the "Build and deploy site" workflow runs (~1 min). When it's green,
   your links are live at the URLs in the table above.

### Option B — command line (git + GitHub CLI)

```bash
cd <this-folder>
git init -b main
git add .
git commit -m "Autoline vehicle ad portal"

# create the repo under the cloudstrucc account/org and push
gh repo create cloudstrucc/autoline-vehicle-ads --public --source=. --remote=origin --push

# turn on Pages via GitHub Actions
gh api -X POST repos/cloudstrucc/autoline-vehicle-ads/pages \
  -f build_type=workflow
```

Then open the **Actions** tab to watch the first deploy. (If the `gh api` Pages command reports it
already exists, just set **Settings → Pages → Source: GitHub Actions** in the UI.)

---

## Everyday tasks

| Task | Do this |
|---|---|
| Update a car's ad | Replace its files in `ads/jpg/` (and `ads/svg/`), commit/push |
| Add a new car | Add `<id>_social.jpg` etc. + a line in `cars.json`, commit/push |
| Remove a sold car | Delete its files from `ads/jpg/` (and `ads/svg/`), commit/push |
| Preview before pushing | `python build.py` then open `_site/index.html` |

Every push triggers a rebuild + redeploy automatically; changes are live in about a minute.

---

## Repository layout

```
build.py                     # the generator (Python standard library only)
.github/workflows/deploy.yml # rebuild + deploy on every push
assets/style.css             # shared styling (tweak the look here)
production/   review/   development/
  ├── cars.json              # display names / order (optional)
  └── ads/
      ├── jpg/<id>_<format>.jpg
      └── svg/<id>_<format>.svg
_site/                       # build output (generated; not committed)
```

---

*Velocity design direction · five vehicles · Social 4:5, Phone 9:19.5, Landscape 16:9.*
