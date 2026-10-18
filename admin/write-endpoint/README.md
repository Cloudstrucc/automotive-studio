# Write endpoint

The one server-side piece the Autoline admin needs. An Artifact page cannot hold a
GitHub token, so this holds it and exposes a single narrow operation: commit a few files
to allowlisted paths on one branch of one repo.

Runs on the **Cloudflare Workers free plan** — 100,000 requests/day, 1,000/min burst,
10 ms CPU per invocation. Publishing uses maybe twenty a day.

---

## Deploy

```bash
npm install -g wrangler
wrangler login
cd admin/write-endpoint
wrangler deploy
```

Then set the two secrets:

```bash
wrangler secret put GITHUB_TOKEN   # paste the PAT from below
wrangler secret put WRITE_KEY      # paste a long random string
```

Generate a key:

```bash
openssl rand -base64 32
```

`wrangler deploy` prints the URL. Paste that and the key into the workspace's
**Connection** screen; they are stored in the artifact's database, never in this repo.

---

## The GitHub token

Create a **fine-grained** PAT at
<https://github.com/settings/personal-access-tokens/new>:

| Setting | Value |
|---|---|
| Repository access | **Only select repositories** → `automotive-studio` |
| Permissions → Contents | **Read and write** |
| Everything else | leave as No access |
| Expiration | 90 days, and diarise the renewal |

Nothing else. Not `workflow`, not organization scopes. If this token leaks, the worst
it permits is editing files in one repository — and the allowlist below narrows that
further.

---

## Configuration

`wrangler.toml`:

```toml
name = "autoline-write"
main = "worker.js"
compatibility_date = "2026-01-01"

[vars]
REPO = "Cloudstrucc/automotive-studio"
BRANCH = "main"
ALLOW_PREFIXES = "manifests/,source-photos/,development/"
```

`ALLOW_PREFIXES` is the real safety boundary. The endpoint refuses any path outside it,
so a leaked `WRITE_KEY` cannot touch `.github/workflows/`, `build.py` or `tools/` —
which is to say it cannot make the site build something you did not write.

Narrow `BRANCH` to a non-default branch if you would rather every change arrive as a
pull request.

---

## The API

```
POST /
Authorization: Bearer <WRITE_KEY>
Content-Type: application/json

{
  "message": "Add 2017 Hyundai Santa Fe Sport",
  "files": [
    { "path": "manifests/items/vehicles/santafe.json", "contentsBase64": "eyJ..." },
    { "path": "source-photos/vehicles/santafe/1.jpg",   "contentsBase64": "/9j/..." }
  ]
}
```

```json
{ "ok": true, "commit": "a3f91c2..." }
```

Errors return `{ "error": "..." }` with 400 (bad request), 401 (bad key), 403 (path not
allowed), 413 (too large) or 502 (GitHub refused).

Limits: 12 files and ~8 MB per request. Every file lands in **one commit** via the git
data API, so the repository is never half-updated and the site rebuilds once.

---

## Be clear about what this does and does not protect

**The token is safe.** It lives in Worker secrets. The page never sees it, and nobody
who opens the artifact can extract it.

**The `WRITE_KEY` is not secret from your users.** It is stored in the artifact's
database so the page can send it, which means anyone you share the artifact with can
read it. That is the same set of people you are already trusting to publish, so the
boundary is unchanged — but it is a bearer key in a browser, not a zero-credential
design, and it is worth knowing which is which.

What makes that acceptable is the narrowness: the key only invokes this endpoint, the
endpoint only writes allowlisted paths in one repo on one branch, and rotating it is one
`wrangler secret put` with no GitHub involvement.

**Rotate the key** when you stop sharing the artifact with someone.

---

## Testing it

```bash
curl -X POST "$WORKER_URL" \
  -H "Authorization: Bearer $WRITE_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"message":"test","files":[{"path":"manifests/.keep","contentsBase64":"dGVzdAo="}]}'
```

A path outside the allowlist should come back `403`, and a wrong key `401`. Check both
before pointing the workspace at it.
