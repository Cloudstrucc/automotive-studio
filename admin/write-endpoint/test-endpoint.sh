#!/usr/bin/env bash
#
# Verify a deployed write endpoint. Prompts for the key, so nothing is typed on a
# command line, stored in a variable or left in shell history.
#
#   bash admin/write-endpoint/test-endpoint.sh [url]

set -uo pipefail
URL="${1:-https://autoline-write.cloustrucc.workers.dev}"

printf 'Endpoint: %s\n' "$URL"
printf 'Paste the WRITE_KEY (input hidden), then press Enter: '
IFS= read -rs KEY
printf '\n\n'

if [ -z "$KEY" ]; then
  echo "No key entered. Nothing to test."
  exit 1
fi
printf 'Key received: %d characters\n\n' "${#KEY}"

pass=0; fail=0
check() { # name expected method key payload
  local name="$1" want="$2" key="$3" payload="$4" body code
  body=$(curl -s -w '\n%{http_code}' --max-time 20 -X POST "$URL" \
    ${key:+-H "Authorization: Bearer $key"} \
    -H 'Content-Type: application/json' -d "$payload")
  code="${body##*$'\n'}"; body="${body%$'\n'*}"
  if [ "$code" = "$want" ]; then
    printf '  PASS  %-34s %s\n' "$name" "$code"
    pass=$((pass+1))
  else
    printf '  FAIL  %-34s got %s, wanted %s\n        %s\n' "$name" "$code" "$want" "$body"
    fail=$((fail+1))
  fi
}

echo "Running checks:"
check "no key -> 401"             401 ""      '{"message":"x","files":[{"path":"manifests/.keep","contentsBase64":"eA=="}]}'
check "wrong key -> 401"          401 "nope"  '{"message":"x","files":[{"path":"manifests/.keep","contentsBase64":"eA=="}]}'
check "outside allowlist -> 403"  403 "$KEY"  '{"message":"t","files":[{"path":"build.py","contentsBase64":"eA=="}]}'
check "path traversal -> 400"     400 "$KEY"  '{"message":"t","files":[{"path":"manifests/../.github/workflows/x.yml","contentsBase64":"eA=="}]}'
check "allowed path -> 200"       200 "$KEY"  '{"message":"endpoint test","files":[{"path":"manifests/.keep","contentsBase64":"dGVzdAo="}]}'

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
echo "Endpoint is good. The last check created a real commit on main."
