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

if [ "$#" -eq 0 ]; then
  echo "==> generating svg from production/ (no environment named)"
  "$PY" gen_velocity.py production
  echo "==> rendering jpg"
  "$PY" render_jpgs.py
  echo
  echo "Built into tools/output/. Pass environment names to render and copy, e.g."
  echo "  ./regen.sh production review development"
  exit 0
fi

# Each environment is rendered from its own manifests, since they can differ --
# that is the whole point of publishing to development/ before production/.
# sync_ads.py renders and copies only the ads whose generated SVG differs from the
# one already committed, so an untouched ad keeps its exact JPG and the diff stays
# down to what really changed. It is the same pair of commands CI runs.
for env in "$@"; do
  echo "==> $env: generating svg"
  "$PY" gen_velocity.py "$env"
  echo "==> $env: rendering what changed"
  "$PY" sync_ads.py "$env"
done

echo
echo "Done. Review the diff, then commit and push to redeploy."
