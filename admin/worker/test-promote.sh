#!/usr/bin/env bash
# Runs promote.test.mjs against worker.js.
#
# worker.js begins with `import PAGE from './workspace.html'`, which is a Wrangler
# text import that node cannot resolve. Strip it into a temporary module, run the
# tests against that, and clean up.
set -euo pipefail
cd "$(dirname "$0")"

trap 'rm -f .worker.test.mjs' EXIT
sed "s|^import PAGE from .*|const PAGE='';|" worker.js > .worker.test.mjs
printf '\nexport { handlePromote, handleItems, readFailure, commitFiles };\n' >> .worker.test.mjs

node promote.test.mjs
