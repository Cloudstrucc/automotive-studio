# Autoline admin — Cloudflare Worker

One Worker serves the whole admin: the workspace page, the assistant, and the commit
endpoint. Runs on the Workers free plan (100,000 requests/day).

```
GET  /            the workspace page
POST /api/plan    description -> validated plan JSON  (Anthropic, server-side)
POST /write       files -> one commit on an allowlisted path
```

---

## Why it is a Worker and not an Artifact

The first version of this was a published Artifact. It cannot work. An Artifact runs
under:

```
Content-Security-Policy: connect-src 'self' https://<id>.frame.claudeusercontent.com
```

so the page may talk to itself and nothing else — no external endpoint, whatever
CORS headers that endpoint returns. Serving the page from the same origin as the API
removes CSP and CORS from the picture, and keeps both secrets server-side.

---

## Deploy

```bash
cd admin/worker
npx wrangler deploy
```

Secrets:

```bash
npx wrangler secret put GITHUB_TOKEN        # fine-grained PAT, one repo, Contents: RW
npx wrangler secret put ANTHROPIC_API_KEY   # for POST /api/plan
```

`WRITE_KEY` is now **optional**. The page calls `/write` same-origin and Cloudflare
Access is the gate; the key only exists so scripts and `test-endpoint.sh` can call in
from outside. Set one if you want that, and make it long:

```bash
openssl rand -base64 32 | tr -d '\n' | pbcopy && echo "copied"
npx wrangler secret put WRITE_KEY
```

> Secrets are write-only — Cloudflare never shows them again. Losing one means setting
> a new one, not recovering the old.

---

## Put Cloudflare Access in front of it — do this before sharing the URL

**There is no login on `GET /`.** Without Access, anyone with the URL can use the
admin and publish to your site.

1. Cloudflare dashboard → **Zero Trust** → **Access** → **Applications** → *Add an
   application* → **Self-hosted**
2. Domain: `autoline-write.<subdomain>.workers.dev`
3. Policy: *Allow*, with **Emails** listing you and your client
4. Identity provider: **One-time PIN** needs no setup — they get a code by email

Free for up to 50 users. Access authenticates before a request reaches the Worker, so
it protects `/`, `/api/plan` and `/write` together.

Once Access is on, requests arrive with a `Cf-Access-Jwt-Assertion` header, which the
Worker accepts in place of `WRITE_KEY`.

---

## The GitHub token

<https://github.com/settings/personal-access-tokens/new>

| Setting | Value |
|---|---|
| Repository access | **Only select repositories** → `automotive-studio` |
| Permissions → Contents | **Read and write** |
| Everything else | No access |
| Expiration | 90 days, diarised |

---

## The path allowlist

`ALLOW_PREFIXES` in `wrangler.toml` is the real safety boundary. Nothing outside
`manifests/`, `source-photos/` and `development/` can be written, so even a leaked
credential cannot reach `.github/workflows/`, `build.py` or `tools/` — it cannot make
the site build something you did not write.

Limits: 12 files and ~8 MB per request. Every file lands in **one commit** via the git
data API, so the repository is never half-updated and the site rebuilds once.

---

## Local development

```bash
npx wrangler dev --local
```

`GET /` works immediately. `/api/plan` returns 503 until `ANTHROPIC_API_KEY` is set,
and `/write` needs `GITHUB_TOKEN`; put them in `.dev.vars` (gitignored) to exercise
them locally.

## Testing a deployed endpoint

```bash
bash test-endpoint.sh https://autoline-write.<subdomain>.workers.dev
```

Prompts for `WRITE_KEY` and checks the rejections, the allowlist, path traversal and
one real write. Note this bypasses Access only if you have not yet enabled it; once
Access is on, external calls need a service token instead.
