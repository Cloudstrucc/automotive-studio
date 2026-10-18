#!/usr/bin/env bash
#
# Regenerate the Velocity ads.
#
#   ./regen.sh                                  build into tools/output only
#   ./regen.sh production review development    ...and copy into those environments
#
# Creates tools/.venv on first run and reuses it afterwards, so this is the whole
# setup — there is nothing to install by hand.

set -euo pipefail
cd "$(dirname "$0")"

# Check the destinations before spending a minute rendering into nowhere.
for env in "$@"; do
  if [ ! -d "../$env/ads/jpg" ] || [ ! -d "../$env/ads/svg" ]; then
    echo "!! no such environment: $env (expected ../$env/ads/jpg and ../$env/ads/svg)" >&2
    exit 1
  fi
done

VENV=.venv
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "==> creating $VENV"
  python3 -m venv "$VENV"
fi

echo "==> installing pinned dependencies"
"$VENV/bin/pip" install -q --disable-pip-version-check -r requirements.txt

# Idempotent and quick once the browser is cached.
echo "==> ensuring chromium is present"
"$VENV/bin/playwright" install chromium >/dev/null

echo "==> generating svg"
"$PY" gen_velocity.py

echo "==> rendering jpg"
"$PY" render_jpgs.py

if [ "$#" -eq 0 ]; then
  echo
  echo "Built into tools/output/. Pass environment names to copy them in, e.g."
  echo "  ./regen.sh production review development"
  exit 0
fi

for env in "$@"; do
  dest="../$env/ads"
  cp output/jpg/*.jpg "$dest/jpg/"
  cp output/svg/*.svg "$dest/svg/"
  echo "==> copied into $env/"
done

echo
echo "Done. Review the diff, then commit and push to redeploy."
