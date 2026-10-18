/**
 * Autoline admin — one Worker serving the whole thing.
 *
 *   GET  /            the workspace page
 *   POST /api/plan    turns a description into a validated plan (Anthropic, server-side)
 *   POST /write       commits files to allowlisted paths in one commit
 *
 * Why it all lives here: a published Artifact runs under
 * `connect-src 'self' <its own frame>`, so it can never call an external endpoint.
 * Serving the page from the same origin as the API removes CSP and CORS from the
 * picture, and keeps both the GitHub token and the Anthropic key server-side.
 *
 * Access control is Cloudflare Access (see README). Put it in front of this Worker
 * before sharing the URL -- there is no other gate on GET /.
 */

import PAGE from './workspace.html';

const UA = 'autoline-admin';
const MAX_FILES = 12;
const MAX_BYTES = 8 * 1024 * 1024;
const MODEL = 'claude-sonnet-5-5';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      return new Response(PAGE, {
        headers: {
          'content-type': 'text/html; charset=utf-8',
          'cache-control': 'no-store',
          'x-content-type-options': 'nosniff',
          'referrer-policy': 'no-referrer',
        },
      });
    }

    if (request.method !== 'POST') {
      return json({ error: 'not found' }, 404);
    }

    // Same-origin calls from our own page carry no bearer token: Cloudflare Access
    // is the gate. WRITE_KEY stays supported so scripts and tests can call in.
    if (env.WRITE_KEY) {
      const auth = request.headers.get('authorization') || '';
      const sameOrigin = (request.headers.get('origin') || '') === url.origin;
      const viaAccess = !!request.headers.get('cf-access-jwt-assertion');
      if (!sameOrigin && !viaAccess && !timingSafeEqual(auth, `Bearer ${env.WRITE_KEY}`)) {
        return json({ error: 'unauthorized' }, 401);
      }
    }

    if (url.pathname === '/api/plan') return handlePlan(request, env);
    if (url.pathname === '/write')    return handleWrite(request, env);
    return json({ error: 'not found' }, 404);
  },
};

/* ---------- POST /api/plan ----------
   The model never writes anything. It returns a plan object that the page renders
   as an editable form; only a later /write turns any of it into a commit. */
async function handlePlan(request, env) {
  if (!env.ANTHROPIC_API_KEY) return json({ error: 'assistant is not configured' }, 503);

  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'body must be JSON' }, 400); }

  const description = String(body.description || '').slice(0, 4000).trim();
  const catalogue = String(body.catalogue || 'Items').slice(0, 80);
  const slots = Array.isArray(body.slots) ? body.slots.slice(0, 3).map(s => String(s).slice(0, 40)) : [];
  if (!description) return json({ error: 'describe the item first' }, 400);

  const prompt =
    `You turn a short description into one catalogue item for a vehicle sales site.\n` +
    `Catalogue: ${catalogue}. Its three spec slots are: ${slots.join(', ')}.\n\n` +
    `Return ONLY JSON of this shape, with no prose and no code fence:\n` +
    `{"summary":"one sentence describing the change","fields":{"title":"string or null",` +
    `"subtitle":"string or null","year":"string or null","price":"string or null, digits and commas only",` +
    `"eyebrow":"string or null, a short badge like Certified",` +
    `"specs":[{"label":"string","value":"string or null"}]}}\n\n` +
    `Rules:\n` +
    `- Use null for anything the description does not state. Never invent a value.\n` +
    `- Keep the three spec slots in the order given, with those labels.\n` +
    `- "title" is make and model without the year. "year" is four digits.\n\n` +
    `Description:\n${description}`;

  let res;
  try {
    res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 1024,
        messages: [{ role: 'user', content: prompt }],
      }),
    });
  } catch (e) {
    return json({ error: 'could not reach the assistant' }, 502);
  }

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    if (res.status === 429) return json({ error: 'the assistant is rate limited; try again shortly' }, 429);
    return json({ error: `assistant error ${res.status}`, detail: detail.slice(0, 300) }, 502);
  }

  const data = await res.json();
  const text = (data.content || []).filter(c => c.type === 'text').map(c => c.text).join('').trim();

  let plan;
  try { plan = JSON.parse(stripFence(text)); }
  catch { return json({ error: 'the assistant did not return usable JSON' }, 502); }

  try { return json({ ok: true, plan: normalisePlan(plan, slots) }); }
  catch (e) { return json({ error: String(e.message || e) }, 502); }
}

function stripFence(s) {
  const m = s.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/);
  return m ? m[1] : s;
}

/** Validated here as well as in the page: the page is not the only caller. */
function normalisePlan(p, slots) {
  if (!p || typeof p !== 'object') throw new Error('no plan returned');
  if (typeof p.summary !== 'string' || !p.summary.trim()) throw new Error('plan had no summary');
  const f = p.fields;
  if (!f || typeof f !== 'object') throw new Error('plan had no fields');
  const str = v => (v == null || v === '') ? null : String(v).slice(0, 200);
  const given = Array.isArray(f.specs) ? f.specs : [];
  return {
    summary: p.summary.trim().slice(0, 300),
    fields: {
      title: str(f.title), subtitle: str(f.subtitle), year: str(f.year),
      price: str(f.price) ? String(f.price).replace(/[^0-9,]/g, '') : null,
      eyebrow: str(f.eyebrow),
      // slots are fixed by the catalogue; the model may fill values, never add columns
      specs: slots.map((label, i) => ({
        label: str(given[i]?.label) || label,
        value: str(given[i]?.value),
      })),
    },
  };
}

/* ---------- POST /write ---------- */
async function handleWrite(request, env) {
  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'body must be JSON' }, 400); }

  const files = Array.isArray(body.files) ? body.files : [];
  const message = String(body.message || 'Update from Autoline admin').slice(0, 200);

  if (!files.length) return json({ error: 'no files' }, 400);
  if (files.length > MAX_FILES) return json({ error: `at most ${MAX_FILES} files` }, 400);

  const allow = (env.ALLOW_PREFIXES || '').split(',').map(s => s.trim()).filter(Boolean);
  let total = 0;
  for (const f of files) {
    if (typeof f?.path !== 'string' || typeof f?.contentsBase64 !== 'string') {
      return json({ error: 'each file needs path and contentsBase64' }, 400);
    }
    if (f.path.includes('..') || f.path.startsWith('/')) {
      return json({ error: `bad path: ${f.path}` }, 400);
    }
    if (allow.length && !allow.some(p => f.path.startsWith(p))) {
      return json({ error: `path not allowed: ${f.path}` }, 403);
    }
    total += f.contentsBase64.length * 0.75;
    if (total > MAX_BYTES) return json({ error: 'payload too large' }, 413);
  }

  try {
    const sha = await commitFiles(env, files, message);
    return json({ ok: true, commit: sha });
  } catch (e) {
    return json({ error: String(e.message || e) }, 502);
  }
}

/**
 * One commit containing every file, via the git data API. The contents API would be
 * shorter but commits one file at a time, leaving the repository half-updated if a
 * photo failed after its manifest landed -- and triggering a rebuild per file.
 */
async function commitFiles(env, files, message) {
  const api = p => `https://api.github.com/repos/${env.REPO}${p}`;
  const branch = env.BRANCH || 'main';

  const ref = await gh(env, api(`/git/ref/heads/${branch}`));
  const base = await gh(env, api(`/git/commits/${ref.object.sha}`));

  const tree = [];
  for (const f of files) {
    const blob = await gh(env, api('/git/blobs'), {
      method: 'POST',
      body: JSON.stringify({ content: f.contentsBase64, encoding: 'base64' }),
    });
    tree.push({ path: f.path, mode: '100644', type: 'blob', sha: blob.sha });
  }

  const newTree = await gh(env, api('/git/trees'), {
    method: 'POST',
    body: JSON.stringify({ base_tree: base.tree.sha, tree }),
  });
  const commit = await gh(env, api('/git/commits'), {
    method: 'POST',
    body: JSON.stringify({ message, tree: newTree.sha, parents: [ref.object.sha] }),
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
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}

/** Constant-time compare so the key cannot be guessed a character at a time. */
function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
