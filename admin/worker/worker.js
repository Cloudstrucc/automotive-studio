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
const MAX_FILES = 40;   // a catalogue deletion rewrites every item it held, in one commit
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

    // Reads are GET; everything else must be POST.
    const isRead = request.method === 'GET' && url.pathname.startsWith('/api/');
    if (!isRead && request.method !== 'POST') {
      return json({ error: 'not found' }, 404);
    }

    // Cloudflare Access is the gate: it authenticates before a request reaches us
    // and stamps every one with Cf-Access-Jwt-Assertion. WRITE_KEY is the escape
    // hatch for scripts.
    //
    // Deliberately NOT accepted: "the request is same-origin". Every visitor to a
    // public page is same-origin, so that would leave an open write endpoint for
    // anyone who found the URL. Without Access configured, POSTs fail closed.
    const auth = request.headers.get('authorization') || '';
    const viaAccess = !!request.headers.get('cf-access-jwt-assertion');
    const viaKey = env.WRITE_KEY && timingSafeEqual(auth, `Bearer ${env.WRITE_KEY}`);
    if (!viaAccess && !viaKey) {
      return json({ error: 'unauthorized', hint: 'Cloudflare Access is not configured for this Worker' }, 401);
    }

    if (url.pathname === '/api/me')    return handleMe(request);
    if (url.pathname === '/api/items')  return handleItems(request, env);
    if (url.pathname === '/api/plan')   return handlePlan(request, env);
    if (url.pathname === '/write')      return handleWrite(request, env);
    if (url.pathname === '/api/promote') return handlePromote(request, env);
    if (url.pathname === '/api/build')   return handleBuild(request, env);
    return json({ error: 'not found' }, 404);
  },
};

/* ---------- GET /api/me ----------
   Cloudflare Access has already verified the assertion before it reaches us, so the
   payload can be read without re-verifying. */
function handleMe(request) {
  const jwt = request.headers.get('cf-access-jwt-assertion');
  if (!jwt) return json({ ok: true, email: null, via: 'none' });
  try {
    const [, payload] = jwt.split('.');
    const claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    return json({
      ok: true,
      email: claims.email || claims.common_name || null,
      expires: claims.exp ? new Date(claims.exp * 1000).toISOString() : null,
      via: 'access',
    });
  } catch {
    return json({ ok: true, email: null, via: 'access' });
  }
}

/* ---------- GET /api/items?env=development ----------
   One recursive tree call finds every manifest, then their blobs are fetched
   together. The repository is the source of truth; nothing is cached here, so the
   admin always shows what is actually committed. */
async function handleItems(request, env) {
  const url = new URL(request.url);
  const which = String(url.searchParams.get('env') || 'development');
  if (!/^[a-z][a-z0-9-]*$/.test(which)) return json({ error: 'bad environment' }, 400);

  const branch = env.BRANCH || 'main';
  let tree;
  try {
    tree = await gh(env, `https://api.github.com/repos/${env.REPO}/git/trees/${encodeURIComponent(branch)}?recursive=1`);
  } catch (e) {
    return json(readFailure(env, e), 502);
  }
  // The tree API truncates very large repositories. Saying so is better than
  // quietly listing a subset and letting someone think an item was deleted.
  if (tree.truncated) {
    return json({
      error: 'the repository listing came back truncated, so this would not be the '
           + 'whole catalogue. Nothing has been changed.',
    }, 502);
  }

  const prefix = `${which}/manifests/items/`;
  const catPrefix = `${which}/manifests/catalogues/`;
  const nodes = (tree.tree || []).filter(n => n.type === 'blob' && n.path.endsWith('.json'));
  const blobs = nodes.filter(n => n.path.startsWith(prefix));
  const catBlobs = nodes.filter(n => n.path.startsWith(catPrefix));

  // One pass for both lists: the catalogues are the admin's tiles, the items their rows.
  const [items, cats] = await Promise.all([
    Promise.all(blobs.map(async n => {
      const cat = n.path.slice(prefix.length).split('/')[0];
      try {
        const m = JSON.parse(await blobText(env, n.sha));
        return { ...m, _path: n.path, _catalogue: cat };
      } catch {
        return { _path: n.path, _broken: true, _catalogue: cat };
      }
    })),
    Promise.all(catBlobs.map(async n => {
      try {
        const m = JSON.parse(await blobText(env, n.sha));
        return { ...m, _path: n.path };
      } catch {
        return null;
      }
    })),
  ]);

  items.sort((a, b) => (a.order ?? 999) - (b.order ?? 999) || String(a.slug).localeCompare(String(b.slug)));

  const byCatalogue = {};
  for (const it of items) (byCatalogue[it._catalogue] ||= []).push(it);

  const defs = cats.filter(c => c && c.slug)
    .sort((a, b) => (a.order ?? 999) - (b.order ?? 999) || String(a.slug).localeCompare(String(b.slug)));

  return json({
    ok: true, env: which, catalogues: byCatalogue,
    catalogueDefs: defs, count: items.length,
  });
}

async function blobText(env, sha) {
  const blob = await gh(env, `https://api.github.com/repos/${env.REPO}/git/blobs/${sha}`);
  return b64decode(blob.content.replace(/\n/g, ''));
}

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
    const raw = await res.text().catch(() => '');
    let detail = raw;
    try { detail = JSON.parse(raw)?.error?.message || raw; } catch {}
    if (res.status === 429) return json({ error: 'the assistant is rate limited; try again shortly' }, 429);
    if (res.status === 401) {
      return json({ error: `the Anthropic API key was rejected: ${String(detail).slice(0, 200)}` }, 502);
    }
    return json({ error: `assistant error ${res.status}: ${String(detail).slice(0, 200)}` }, 502);
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
/* Turns a GitHub failure into something the admin can act on. The common one by far
   is an expired token, which otherwise reads as a generic 502 and sends people
   looking at their manifests instead of at their credentials. */
function readFailure(env, e) {
  const msg = String(e?.message || e);
  if (/GitHub 40[13]/.test(msg)) {
    return {
      error: 'GitHub refused the request, which almost always means the admin\'s '
           + 'access token has expired or been revoked. The products are safe — '
           + 'this is the admin failing to read them, not the repository losing them.',
      remedy: 'Issue a new fine-grained token with Contents: read and write on '
            + `${env.REPO || 'the repository'}, then run: wrangler secret put GITHUB_TOKEN`,
      detail: msg,
    };
  }
  if (/GitHub 404/.test(msg)) {
    return {
      error: `GitHub cannot find ${env.REPO || 'the repository'}, or the token has no `
           + 'access to it.',
      remedy: 'Check REPO in wrangler.toml and that the token grants this repository.',
      detail: msg,
    };
  }
  return { error: `Could not read the repository: ${msg}`, detail: msg };
}

const ENV_NAMES = new Set(['production', 'review', 'development']);
const SAFE_SLUG = /^[a-z0-9][a-z0-9-]*$/;

/* ---------- POST /api/promote ----------
   Copies items from one environment to another: their manifests, their source photos
   and, where the target does not have it yet, the catalogue manifest they belong to.

   Nothing is uploaded. Every path copied already exists in the repository, so the new
   tree points at the same blobs — promoting a vehicle with four photos moves no bytes
   and takes one round trip rather than five.

   Rendered ads are deliberately NOT copied. CI re-renders the target from the manifests
   it just received, which is what keeps an environment internally consistent: its ads
   are always built from its own inputs rather than inherited from somewhere else. */
async function handlePromote(request, env) {
  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'body must be JSON' }, 400); }

  const from = String(body.from || '');
  const to = String(body.to || '');
  if (!ENV_NAMES.has(from)) return json({ error: `unknown source environment: ${from}` }, 400);
  if (!ENV_NAMES.has(to))   return json({ error: `unknown target environment: ${to}` }, 400);
  if (from === to)          return json({ error: 'source and target are the same' }, 400);

  const slugs = Array.isArray(body.slugs) ? body.slugs.map(String) : null;
  if (slugs && !slugs.every(s => SAFE_SLUG.test(s))) {
    return json({ error: 'a slug contains characters that are not allowed' }, 400);
  }
  if (slugs && !slugs.length) return json({ error: 'nothing selected to promote' }, 400);

  const branch = env.BRANCH || 'main';
  let tree;
  try {
    tree = await gh(env, `https://api.github.com/repos/${env.REPO}/git/trees/${encodeURIComponent(branch)}?recursive=1`);
  } catch (e) {
    return json(readFailure(env, e), 502);
  }
  if (tree.truncated) return json({ error: 'the repository listing came back truncated' }, 502);

  const blobs = (tree.tree || []).filter(n => n.type === 'blob');
  const at = new Map(blobs.map(n => [n.path, n.sha]));

  // Which items are we moving?
  const itemPrefix = `${from}/manifests/items/`;
  const chosen = blobs.filter(n => {
    if (!n.path.startsWith(itemPrefix) || !n.path.endsWith('.json')) return false;
    const [cat, file] = n.path.slice(itemPrefix.length).split('/');
    if (cat === 'orphan') return false;          // the pen never promotes
    return !slugs || slugs.includes(file.replace(/\.json$/, ''));
  });
  if (!chosen.length) return json({ error: 'found nothing to promote' }, 404);

  const files = [];
  const seen = new Set();
  const add = (path, sha) => { if (!seen.has(path)) { seen.add(path); files.push({ path, sha }); } };

  const summary = [];
  const cats = new Set();

  for (const node of chosen) {
    const rel = node.path.slice(from.length + 1);           // manifests/items/<cat>/<slug>.json
    const [cat, file] = node.path.slice(itemPrefix.length).split('/');
    const slug = file.replace(/\.json$/, '');

    let item;
    try { item = JSON.parse(await blobText(env, node.sha)); }
    catch { return json({ error: `${rel} is not valid JSON; nothing promoted` }, 422); }

    const images = Array.isArray(item.images) ? item.images : [];
    if (item.status === 'published' && !images.length) {
      return json({ error: `${slug} is published with no photo, so it cannot be promoted. Nothing has been changed.` }, 422);
    }

    add(`${to}/${rel}`, node.sha);
    cats.add(cat);

    // its photos, and its backdrop
    for (const img of images) {
      const p = `${from}/${img?.file || ''}`;
      const sha = at.get(p);
      if (!sha) return json({ error: `${slug} refers to a missing photo: ${img?.file}. Nothing has been changed.` }, 422);
      add(`${to}/${img.file}`, sha);
    }
    if (item.background && at.has(`${from}/${item.background}`)) {
      add(`${to}/${item.background}`, at.get(`${from}/${item.background}`));
    }
    summary.push(slug);
  }

  // Carry each category definition across when the target does not already have it,
  // otherwise a promoted item lands in a category the target cannot render.
  for (const cat of cats) {
    const src = `${from}/manifests/catalogues/${cat}.json`;
    const dst = `${to}/manifests/catalogues/${cat}.json`;
    if (at.has(src) && !at.has(dst)) add(dst, at.get(src));
  }

  if (files.length > 200) {
    return json({ error: `that would copy ${files.length} files in one commit; promote fewer items at a time` }, 413);
  }

  const what = slugs ? summary.join(', ') : `everything in ${from}`;
  const message = `Promote ${what} from ${from} to ${to}`.slice(0, 200);

  try {
    const sha = await commitFiles(env, files, message, []);
    return json({ ok: true, commit: sha, promoted: summary, files: files.length, from, to });
  } catch (e) {
    return json({ error: `the promotion was refused: ${e.message || e}` }, 502);
  }
}

/* ---------- GET /api/build ----------
   The state of the most recent deploy, so the admin can say "your change is being
   rendered" and then "it is live" instead of leaving someone refreshing the site. */
async function handleBuild(request, env) {
  try {
    const runs = await gh(env,
      `https://api.github.com/repos/${env.REPO}/actions/runs?per_page=1&branch=${encodeURIComponent(env.BRANCH || 'main')}`);
    const r = (runs.workflow_runs || [])[0];
    if (!r) return json({ ok: true, state: 'none' });
    return json({
      ok: true,
      state: r.status === 'completed' ? (r.conclusion || 'unknown') : r.status,
      title: r.display_title,
      url: r.html_url,
      started: r.run_started_at,
      sha: r.head_sha,
    });
  } catch (e) {
    return json(readFailure(env, e), 502);
  }
}

async function handleWrite(request, env) {
  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'body must be JSON' }, 400); }

  const files = Array.isArray(body.files) ? body.files : [];
  const deletes = Array.isArray(body.deletes) ? body.deletes.map(String) : [];
  const message = String(body.message || 'Update from Autoline admin').slice(0, 200);

  if (!files.length && !deletes.length) return json({ error: 'nothing to write' }, 400);
  if (files.length > MAX_FILES) return json({ error: `at most ${MAX_FILES} files` }, 400);
  if (deletes.length > 40) return json({ error: 'at most 40 deletions' }, 400);

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

  // Deletions obey the same allowlist: they can only remove what they could write.
  // Rendered ads are deliberately NOT deletable here -- CI rebuilds <env>/ads from
  // the manifests on every change, so a removed item's ads disappear on their own.
  for (const path of deletes) {
    if (path.includes('..') || path.startsWith('/')) {
      return json({ error: `bad path: ${path}` }, 400);
    }
    if (allow.length && !allow.some(p => path.startsWith(p))) {
      return json({ error: `path not allowed: ${path}` }, 403);
    }
  }

  // A published item must have at least one image: the ad artwork is built from the
  // photo, so an item without one renders as an empty frame on the live site. Enforced
  // here rather than only in the page, because the page is not the only possible caller.
  try {
    const problem = await checkPublishedItems(env, files);
    if (problem) return json({ error: problem }, 422);
  } catch (e) {
    return json({ error: `could not validate the item: ${e.message || e}` }, 502);
  }

  try {
    const sha = await commitFiles(env, files, message, deletes);
    return json({ ok: true, commit: sha });
  } catch (e) {
    return json({ error: String(e.message || e) }, 502);
  }
}

const ITEM_MANIFEST = /(?:^|\/)manifests\/items\/([^/]+)\/[^/]+\.json$/;
// Items whose catalogue was deleted are parked here. Kept so a deletion can be undone,
// but they belong to nothing, so nothing in orphan may be published. Must stay in step
// with build.py's ORPHAN_CATALOGUE and gen_velocity.py's.
const ORPHAN_CATALOGUE = 'orphan';

/**
 * Returns a message when the payload would publish an item that cannot render, or
 * null when everything checks out. Two things are checked, both because the ad
 * artwork is built from the manifest and an item that fails either would reach the
 * site as an empty frame or an unreachable page:
 *
 *   - a published item has at least one image, in this payload or already committed;
 *   - a published item names a real category, and the one its file is being written
 *     into. Nothing may be published into the orphan pen.
 *
 * Enforced here rather than only in the page, because the page is not the only
 * possible caller.
 */
async function checkPublishedItems(env, files) {
  const incoming = new Set(files.map(f => f.path));

  for (const f of files) {
    const m = ITEM_MANIFEST.exec(f.path);
    if (!m) continue;
    const folder = m[1];

    let item;
    try { item = JSON.parse(b64decode(f.contentsBase64)); }
    catch { return `${f.path} is not valid JSON`; }

    if (item?.status !== 'published') continue;

    const cat = typeof item.catalogue === 'string' ? item.catalogue.trim() : '';
    if (!cat) {
      return `${item.slug || f.path} has no category. Choose one before publishing it.`;
    }
    if (cat === ORPHAN_CATALOGUE || folder === ORPHAN_CATALOGUE) {
      return `${item.slug || f.path} has no category of its own yet. `
           + `Give it one before publishing it.`;
    }
    if (cat !== folder) {
      return `${item.slug || f.path} says it is in "${cat}" but is being written into `
           + `"${folder}". Those have to match.`;
    }

    const images = Array.isArray(item.images) ? item.images : [];
    if (!images.length) {
      return `${item.slug || f.path} has no image. A published item needs at least one.`;
    }

    // images[].file is relative to the environment root, which is everything in the
    // manifest's path before "/manifests/".
    const root = f.path.slice(0, f.path.indexOf('manifests/'));
    for (const img of images) {
      if (!img?.file) return `${item.slug || f.path} has an image entry with no file`;
      const full = root + img.file;
      if (incoming.has(full)) continue;
      if (!(await existsInRepo(env, full))) {
        return `${item.slug || f.path} refers to a missing image: ${img.file}`;
      }
    }
  }
  return null;
}

async function existsInRepo(env, path) {
  const branch = env.BRANCH || 'main';
  const url = `https://api.github.com/repos/${env.REPO}/contents/${encodeURI(path)}?ref=${encodeURIComponent(branch)}`;
  const res = await fetch(url, {
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: 'application/vnd.github+json',
      'user-agent': UA,
    },
  });
  if (res.status === 404) return false;
  if (!res.ok) throw new Error(`GitHub ${res.status} checking ${path}`);
  return true;
}

function b64decode(b64) {
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/**
 * One commit containing every file, via the git data API. The contents API would be
 * shorter but commits one file at a time, leaving the repository half-updated if a
 * photo failed after its manifest landed -- and triggering a rebuild per file.
 */
async function commitFiles(env, files, message, deletes = []) {
  const api = p => `https://api.github.com/repos/${env.REPO}${p}`;
  const branch = env.BRANCH || 'main';

  const ref = await gh(env, api(`/git/ref/heads/${branch}`));
  const base = await gh(env, api(`/git/commits/${ref.object.sha}`));

  const tree = [];
  for (const f of files) {
    // A file that already names a blob is reused as-is. Promotion works this way:
    // the bytes are already in the repository, so copying an environment is a tree
    // that points at the same blobs rather than a re-upload of every photo.
    if (f.sha) {
      tree.push({ path: f.path, mode: '100644', type: 'blob', sha: f.sha });
      continue;
    }
    const blob = await gh(env, api('/git/blobs'), {
      method: 'POST',
      body: JSON.stringify({ content: f.contentsBase64, encoding: 'base64' }),
    });
    tree.push({ path: f.path, mode: '100644', type: 'blob', sha: blob.sha });
  }

  // sha: null removes a path from the tree
  for (const path of deletes) {
    tree.push({ path, mode: '100644', type: 'blob', sha: null });
  }
  if (!tree.length) throw new Error('nothing to commit');

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
