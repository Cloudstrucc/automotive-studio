# Categories (catalogues) — routes, states and the vocabulary

How categories work across the three pieces: `build.py` (the public site),
`admin/worker/worker.js` (the commit endpoint) and `admin/worker/workspace.html`
(the admin page). Written down because the URL shape and the status words have to
mean the same thing on both sides.

## Routes

A category's slug is its folder. The **default** category, `vehicles`, is the
exception: it *is* the environment, so there is deliberately no `/vehicles/` route
and none of today's URLs moved.

| | board | item page | per-item zip |
|---|---|---|---|
| `vehicles` (default) | `<env>/index.html` | `<env>/cars/<slug>.html` | `<env>/cars/<slug>-ads.zip` |
| any other, e.g. `tyres` | `<env>/tyres/index.html` | `<env>/tyres/<slug>.html` | `<env>/tyres/<slug>-ads.zip` |

Both item folders sit one level under the environment root, so ad images are
`../ads/jpg/…` from every item page and the stylesheet prefixes did not change.

`<env>/` is still a complete copy of `PUBLIC_ENV`, and the site still never names an
environment: the folder names survive only in URLs.

A category may not take a folder the build already writes at an environment root —
`ads`, `assets`, `cars`, or an environment name. `build.py` skips such a category
with a warning and the admin refuses to create one.

## Category status

`<env>/manifests/catalogues/<slug>.json` carries `status` and `in_menu`.

| `status` | renders | in the menu |
|---|---|---|
| `public` | yes, at its own route | yes, if `in_menu` and it has an item |
| `draft` | no | no |
| `retired` | no | no |

`published` is the pre-migration spelling of `public` and is still read as public, so
an un-migrated manifest keeps building.

`in_menu: false` is the sitemap flag: the category renders and is reachable by direct
link, but is left out of the menu.

`draft` and `retired` behave identically in the build — both render nothing. They are
kept apart because they read differently to the owner in the admin list: *not launched
yet* versus *we stopped selling this*. Nothing in the build branches on which one it is.

### The menu

A category is listed only when it is `public`, has `in_menu`, and has at least one
published item with an ad image. One entry is not a menu — it is the page you are
already on — so the markup is emitted only once there are **two** or more. With only
`vehicles` configured the site therefore looks exactly as it did.

## Item status: two states, not three

An item's `status` is **`published`** or **`draft`**. There is no third item state,
and `Deactivate` in the admin keeps writing `draft`.

The spec asked for draft, publish and disable as distinct ideas. For a category three
states are worth keeping because the owner reads that list as a plan. For an item they
are not: `draft` and a hypothetical `retired` would be the same row in `build.py`, the
same row in `gen_velocity.py`, the same affordances in the admin, and the same thing
to the client — *saved here, not on the site*. Adding a third spelling would mean two
words for one behaviour and two code paths that must never diverge.

So the single off-the-site state is reached two ways, and that is the whole model:

- **Save as draft** at creation — written but never on the site.
- **Deactivate** an item that was live — same state, reached later.

*Why* an item is off the site (sold, awaiting photos, seasonal) is a different fact
from *whether* it renders. When that needs recording it belongs in a field of its own,
not in the gate that decides rendering.

What both renderers agree on, and must keep agreeing on:

> an item renders only when `status == "published"`, it has at least one image, and
> its category is `public`.

## The orphan pen

Deleting a category must not destroy its items. In one commit, the category manifest
is deleted and each of its items is rewritten to
`manifests/items/orphan/<slug>.json` with `catalogue: "orphan"`, `status: "draft"`,
and `audit.orphaned_from` recording where it came from.

`orphan` is not a real category: it has no manifest, no route and no menu entry.
`build.py` skips it, `tools/gen_velocity.py` renders no ads for it, and the Worker
refuses to commit a *published* item into it. The admin shows orphaned items in a tile
of their own so they can be given a category again — which is an ordinary edit plus an
explicit publish.

Deleting an empty category just removes its manifest.

## Guardrails in the Worker

`POST /write` refuses, before any commit:

- a published item with no image (as before);
- a published item whose `catalogue` is missing, `orphan`, or does not match the
  folder its manifest is being written into.

`ALLOW_PREFIXES` is unchanged, so none of this can touch `build.py`, `tools/` or
`.github/workflows/`.
