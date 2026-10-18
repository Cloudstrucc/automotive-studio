# SKILLS.md — repeatable playbooks

Step-by-step workflows for this repo. Each can be turned into a Claude Code skill later
(drop a `SKILL.md` under `.claude/skills/<name>/`). Commands assume the repo root unless noted.

---

## 1. Preview the site locally
```bash
python build.py          # generates ./_site
open _site/index.html    # macOS; or just open the file in a browser
```
Check the landing page, each environment, a vehicle page, and resize to phone width.

---

## 2. Deploy (publish changes)
No manual step — **pushing to `main` deploys automatically** via GitHub Actions.
```bash
git add -A && git commit -m "Describe the change" && git push
```
Watch the **Actions** tab; the site is live ~1 minute after the run goes green.

---

## 3. Add a new vehicle
1. Prepare its ad images named `<id>_social.jpg`, `<id>_phone.jpg`, `<id>_landscape.jpg`
   (+ optional matching `.svg`s). Use a short lowercase id (e.g. `civic`).
2. Copy them into the target environment:
   ```
   development/ads/jpg/   and   development/ads/svg/
   ```
3. Add a line to `development/cars.json`:
   ```json
   "civic": { "name": "Honda Civic", "subtitle": "LX · Sedan", "order": 6 }
   ```
4. Commit & push (see #2). It appears on the Development site.

> No ad images yet? Generate them with `tools/` — see #6.

---

## 4. Update an existing vehicle
Replace its files in the env's `ads/jpg/` (and `ads/svg/`) with new versions (same filenames),
then commit & push. The site shows the new version automatically.

---

## 5. Remove a sold vehicle
Delete its `<id>_*.jpg` (and `.svg`) from the env's `ads/` folder, optionally remove its line from
`cars.json`, then commit & push. It disappears from that environment.

---

## 6. Change what's printed on an ad (price, mileage, phone, trim)
The text baked into an ad is regenerated with the tools, not edited by hand.
```bash
cd tools
# edit CARS (km / price / trim) or the contact/footer text in gen_velocity.py
python gen_velocity.py
pip install playwright && playwright install chromium   # first run only
python render_jpgs.py
# copy what you need into an environment, e.g.:
cp output/svg/buick_*.svg ../production/ads/svg/
cp output/jpg/buick_*.jpg ../production/ads/jpg/
cd .. && git add -A && git commit -m "Reprice Buick" && git push
```

---

## 7. Promote development → review → production
Copy a vehicle's files up one environment when it's ready:
```bash
cp development/ads/jpg/buick_*.jpg review/ads/jpg/
cp development/ads/svg/buick_*.svg review/ads/svg/
# …then review → production the same way once signed off
git add -A && git commit -m "Promote Buick to review" && git push
```
Keep `cars.json` in sync in the destination environment if you added/renamed a vehicle.

---

## 8. Change the look (colours, fonts, layout)
Edit `assets/style.css` (shared by every page). Preview with #1, then push. The accent colour is
`--acc: #19e36a`; environment badge colours are `--prod`, `--review`, `--dev`.
