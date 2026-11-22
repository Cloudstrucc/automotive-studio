/**
 * Promotion tests — run with:  bash admin/worker/test-promote.sh
 *
 * Promotion is the one admin operation that can write to the live site, so its
 * guardrails are tested against a fake repository rather than trusted by reading.
 * The fake serves a git tree and blobs; the assertions are about which paths end up
 * in the commit, and which requests are refused outright.
 *
 * worker.js imports workspace.html, which only Wrangler can do, so the runner
 * strips that import into a temporary module first.
 */
import { handlePromote } from './.worker.test.mjs';

// A fake repository: development holds two vehicles, production holds nothing.
const TREE = { truncated:false, tree:[
  {type:'blob', path:'development/manifests/catalogues/vehicles.json', sha:'cat1'},
  {type:'blob', path:'development/manifests/items/vehicles/santafe.json', sha:'i1'},
  {type:'blob', path:'development/source-photos/vehicles/santafe/1.jpg', sha:'p1'},
  {type:'blob', path:'development/source-photos/vehicles/santafe/blur.jpg', sha:'b1'},
  {type:'blob', path:'development/manifests/items/vehicles/buick.json', sha:'i2'},
  {type:'blob', path:'development/source-photos/vehicles/buick/1.jpg', sha:'p2'},
  {type:'blob', path:'development/manifests/items/orphan/old.json', sha:'i3'},
  {type:'blob', path:'development/manifests/items/vehicles/nophoto.json', sha:'i4'},
  {type:'blob', path:'development/manifests/items/vehicles/missing.json', sha:'i5'},
]};
const BLOBS = {
  i1:{slug:'santafe',status:'published',images:[{file:'source-photos/vehicles/santafe/1.jpg'}],background:'source-photos/vehicles/santafe/blur.jpg'},
  i2:{slug:'buick',status:'draft',images:[{file:'source-photos/vehicles/buick/1.jpg'}]},
  i3:{slug:'old',status:'draft',images:[]},
  i4:{slug:'nophoto',status:'published',images:[]},
  i5:{slug:'missing',status:'published',images:[{file:'source-photos/vehicles/missing/1.jpg'}]},
  cat1:{slug:'vehicles',status:'public'},
};
let committed = null;
globalThis.fetch = async (url, init) => {
  const u = String(url);
  const ok = b => new Response(JSON.stringify(b), {status:200, headers:{'content-type':'application/json'}});
  if (u.includes('/git/trees/') && u.includes('recursive')) return ok(TREE);
  if (u.includes('/git/blobs/')) {
    const sha = u.split('/git/blobs/')[1];
    return ok({ content: Buffer.from(JSON.stringify(BLOBS[sha])).toString('base64') });
  }
  if (u.endsWith('/git/ref/heads/main')) return ok({object:{sha:'base'}});
  if (u.includes('/git/commits/base')) return ok({tree:{sha:'basetree'}});
  if (u.endsWith('/git/trees')) { committed = JSON.parse(init.body); return ok({sha:'newtree'}); }
  if (u.endsWith('/git/commits')) return ok({sha:'commit123'});
  if (u.includes('/git/refs/heads/main')) return ok({});
  throw new Error('unexpected ' + u);
};
const env = { REPO:'o/r', BRANCH:'main', GITHUB_TOKEN:'t' };
const call = body => handlePromote(new Request('https://x/api/promote',{method:'POST',body:JSON.stringify(body)}), env);
const read = async r => ({ status:r.status, body: await r.json() });

let fails = 0;
const check = (name, cond, extra='') => { console.log((cond?'  ok   ':'  FAIL ')+name+(cond?'':' — '+extra)); if(!cond) fails++; };

console.log('\n1. promote one published item to review');
committed=null;
let r = await read(await call({from:'development',to:'review',slugs:['santafe']}));
const paths = (committed?.tree||[]).map(t=>t.path).sort();
check('succeeds', r.status===200, JSON.stringify(r.body));
check('copies manifest, photo, backdrop and the category', JSON.stringify(paths)===JSON.stringify([
  'review/manifests/catalogues/vehicles.json',
  'review/manifests/items/vehicles/santafe.json',
  'review/source-photos/vehicles/santafe/1.jpg',
  'review/source-photos/vehicles/santafe/blur.jpg']), JSON.stringify(paths));
check('reuses blob shas (uploads nothing)', (committed.tree||[]).every(t=>t.sha && !t.content), JSON.stringify(committed.tree));

console.log('\n2. a draft promotes, and stays a draft');
committed=null;
r = await read(await call({from:'development',to:'review',slugs:['buick']}));
check('succeeds', r.status===200, JSON.stringify(r.body));
check('its manifest blob is copied unchanged', committed.tree.some(t=>t.path==='review/manifests/items/vehicles/buick.json' && t.sha==='i2'));

console.log('\n3. guardrails');
r = await read(await call({from:'development',to:'production',slugs:['nophoto']}));
check('refuses a published item with no photo', r.status===422, JSON.stringify(r.body));
r = await read(await call({from:'development',to:'production',slugs:['missing']}));
check('refuses an item whose photo is missing', r.status===422, JSON.stringify(r.body));
r = await read(await call({from:'development',to:'development',slugs:['santafe']}));
check('refuses same source and target', r.status===400);
r = await read(await call({from:'development',to:'../../etc',slugs:['santafe']}));
check('refuses an unknown target', r.status===400);
r = await read(await call({from:'development',to:'review',slugs:['../../../build.py']}));
check('refuses a slug with traversal', r.status===400, JSON.stringify(r.body));
r = await read(await call({from:'development',to:'review',slugs:['nope']}));
check('404s when nothing matches', r.status===404);

console.log('\n4. the orphan pen never promotes');
committed=null;
r = await read(await call({from:'development',to:'review'}));
check('promoting everything skips orphan', !(committed?.tree||[]).some(t=>t.path.includes('/orphan/')), JSON.stringify((committed?.tree||[]).map(t=>t.path)));

console.log('\n5. the category is not re-copied when the target already has it');
TREE.tree.push({type:'blob', path:'production/manifests/catalogues/vehicles.json', sha:'cat1'});
committed=null;
r = await read(await call({from:'development',to:'production',slugs:['santafe']}));
check('skips the category it already has', !committed.tree.some(t=>t.path.endsWith('catalogues/vehicles.json')), JSON.stringify(committed.tree.map(t=>t.path)));

console.log(fails ? `\n${fails} FAILED\n` : '\nall passed\n');
process.exit(fails?1:0);
