/**
 * Autoline write endpoint.
 *
 * The one piece of server the admin needs. The Artifact page cannot hold a GitHub
 * token, so this holds it instead and exposes a single, deliberately narrow operation:
 * commit a small set of files to an allowlisted path prefix on one branch of one repo.
 *
 * Deploy: see README.md. Runs on the Cloudflare Workers free plan.
 *
 * Secrets (wrangler secret put):
 *   GITHUB_TOKEN   fine-grained PAT, single repo, Contents: read and write
 *   WRITE_KEY      shared key the page sends as `Authorization: Bearer <key>`
 *
 * Vars (wrangler.toml):
 *   REPO           "owner/name"
 *   BRANCH         e.g. "main"
 *   ALLOW_PREFIXES comma-separated path prefixes this endpoint may write
 */

const UA = 'autoline-write-endpoint';
const MAX_FILES = 12;
const MAX_BYTES = 8 * 1024 * 1024; // whole request, after base64

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return cors(new Response(null, { status: 204 }));
    if (request.method !== 'POST') return cors(json({ error: 'POST only' }, 405));

    const auth = request.headers.get('authorization') || '';
    if (!env.WRITE_KEY || !timingSafeEqual(auth, `Bearer ${env.WRITE_KEY}`)) {
      return cors(json({ error: 'unauthorized' }, 401));
    }

    let body;
    try { body = await request.json(); }
    catch { return cors(json({ error: 'body must be JSON' }, 400)); }

    const files = Array.isArray(body.files) ? body.files : [];
    const message = String(body.message || 'Update from Autoline admin').slice(0, 200);

    if (!files.length) return cors(json({ error: 'no files' }, 400));
    if (files.length > MAX_FILES) return cors(json({ error: `at most ${MAX_FILES} files` }, 400));

    const allow = (env.ALLOW_PREFIXES || '').split(',').map(s => s.trim()).filter(Boolean);
    let total = 0;
    for (const f of files) {
      if (typeof f?.path !== 'string' || typeof f?.contentsBase64 !== 'string') {
        return cors(json({ error: 'each file needs path and contentsBase64' }, 400));
      }
      // Reject traversal and anything outside the allowlist. This is what keeps a
      // leaked WRITE_KEY from being able to rewrite the workflow or the build script.
      if (f.path.includes('..') || f.path.startsWith('/')) {
        return cors(json({ error: `bad path: ${f.path}` }, 400));
      }
      if (allow.length && !allow.some(p => f.path.startsWith(p))) {
        return cors(json({ error: `path not allowed: ${f.path}` }, 403));
      }
      total += f.contentsBase64.length * 0.75;
      if (total > MAX_BYTES) return cors(json({ error: 'payload too large' }, 413));
    }

    try {
      const sha = await commitFiles(env, files, message);
      return cors(json({ ok: true, commit: sha }));
    } catch (e) {
      return cors(json({ error: String(e.message || e) }, 502));
    }
  },
};

/**
 * One commit containing every file, via the git data API.
 *
 * The contents API would be shorter but commits one file at a time, which would leave
 * the repository in a half-updated state if a photo failed after its manifest landed --
 * and would trigger a site rebuild per file.
 */
async function commitFiles(env, files, message) {
  const repo = env.REPO;
  const branch = env.BRANCH || 'main';
  const api = p => `https://api.github.com/repos/${repo}${p}`;

  const ref = await gh(env, api(`/git/ref/heads/${branch}`));
  const baseCommit = await gh(env, api(`/git/commits/${ref.object.sha}`));

  const blobs = [];
  for (const f of files) {
    const blob = await gh(env, api('/git/blobs'), {
      method: 'POST',
      body: JSON.stringify({ content: f.contentsBase64, encoding: 'base64' }),
    });
    blobs.push({ path: f.path, mode: '100644', type: 'blob', sha: blob.sha });
  }

  const tree = await gh(env, api('/git/trees'), {
    method: 'POST',
    body: JSON.stringify({ base_tree: baseCommit.tree.sha, tree: blobs }),
  });

  const commit = await gh(env, api('/git/commits'), {
    method: 'POST',
    body: JSON.stringify({ message, tree: tree.sha, parents: [ref.object.sha] }),
  });

  await gh(env, api(`/git/refs/heads/${branch}`), {
    method: 'PATCH',
    body: JSON.stringify({ sha: commit.sha }),
  });

  return commit.sha;
}

async function gh(env, url, init = {}) {
  const res = await fetch(url, {
    ...init,
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: 'application/vnd.github+json',
      'user-agent': UA,
      'content-type': 'application/json',
      ...(init.headers || {}),
    },
  });
  const text = await res.text();
  if (!res.ok) {
    let msg = text;
    try { msg = JSON.parse(text).message || text; } catch {}
    throw new Error(`GitHub ${res.status}: ${msg}`);
  }
  return text ? JSON.parse(text) : null;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** Constant-time compare so the key cannot be guessed a character at a time. */
function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/**
 * The artifact runs on an origin we do not control and which may change, so the
 * endpoint is open to any origin and relies on WRITE_KEY plus the path allowlist
 * rather than on origin checks. A browser will not attach the key on its own, so
 * this is not CSRF-exposed.
 */
function cors(res) {
  const h = new Headers(res.headers);
  h.set('access-control-allow-origin', '*');
  h.set('access-control-allow-methods', 'POST, OPTIONS');
  h.set('access-control-allow-headers', 'authorization, content-type');
  h.set('access-control-max-age', '86400');
  return new Response(res.body, { status: res.status, headers: h });
}
