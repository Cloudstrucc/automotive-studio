# Admin platform — implementation plan

> **SUPERSEDED by [`ADMIN_APP_PLAN.md`](ADMIN_APP_PLAN.md).** That plan is the current
> direction: a lean Express/Handlebars/Svelte admin publishing into this repo, rather
> than the Next.js platform proposed here. Kept for the security checklist (§9) and the
> passkey notes (§4), which still apply if passkeys are revisited.

Status: **superseded proposal, nothing built.** Written 18 Oct 2026.

Covers the authenticated admin area (`/admin/*`), passwordless auth (`/auth/*`), the
workspace tiles, and the site-template feature.

---

## 1. The constraint that decides everything

**GitHub Pages serves static files. It runs no code, holds no database, keeps no secrets.**

Every feature requested needs at least one of those:

| Feature | Needs |
|---|---|
| Passkey sign-in | Server to generate/verify WebAuthn challenges; credential storage |
| Invite codes | Database, single-use enforcement, expiry |
| Sessions | Server-set `HttpOnly` cookies |
| Orders | Database, transactions, PII handling |
| AI template generation | Anthropic API key held server-side — it **cannot** go in browser JS |
| Uploads (Figma/PDF/image) | File storage, processing |

So this is not an extension of the current site. It is a new application, and the
question is not *whether* to add a backend but *where the public site ends up*.

---

## 2. Stack recommendation

**Recommendation: build `/admin` and `/auth` as a TypeScript app on Next.js. Do not
build it in Python.**

This is a genuine pivot, so here is the honest reasoning rather than a preference.

### Where Python is fine
`build.py` is 280 lines of stdlib string templating. It is good at what it does and
nothing here is wrong with it. FastAPI + HTMX is a real, lean stack, and
[`py_webauthn`](https://github.com/duo-labs/py_webauthn) handles passkeys correctly. If
the ask were *only* passkeys plus CRUD, I would say stay in Python and skip the churn.

### Where Python costs you
The ask is not only CRUD. Three features pull hard toward the JS ecosystem:

1. **The visual page editor.** Puck, Craft.js, GrapesJS, TipTap, Plate — the entire
   category is React. Python has no equivalent. In a Python stack you would still write
   this part in React, so you would be running two languages regardless.
2. **Passkeys.** [SimpleWebAuthn](https://simplewebauthn.dev/) is the de-facto
   implementation, with the best docs and the most-tested edge cases (conditional UI,
   cross-device, autofill). `py_webauthn` is solid but you will hand-roll more.
3. **Auth plumbing generally.** Better Auth and Auth.js give you sessions, invites,
   multi-credential passkeys, and org/role models as configuration. The Python
   equivalents are thinner; expect to write the session layer yourself.

Add Stripe's TS-first integrations for Orders, and the Anthropic TS SDK with streaming
for the template chat, and the balance is clear.

### The real cost of pivoting
You stop being able to read the whole system in one language, and `build.py` either
stays as a separate Python step or gets ported. That is a genuine loss — weigh it
against writing a React editor from a Python backend anyway.

### Concretely
| Layer | Choice | Why |
|---|---|---|
| Framework | **Next.js (App Router)** | Server Actions keep secrets server-side; one app for API + UI |
| Language | **TypeScript**, `strict` | Catches schema drift between admin and site data |
| Auth | **Better Auth** (or Auth.js) + SimpleWebAuthn | Passkeys, sessions, invites, roles as config |
| DB | **Postgres** (Neon/Supabase) + **Drizzle** or Prisma | Orders need real transactions. Not SQLite. |
| Storage | **S3-compatible** (R2/S3) | Uploads; never in the DB |
| Hosting | Vercel, or Fly.io if you want one box | Both fine; Fly if you dislike serverless cold paths |
| Payments | **Stripe** | Do not hand-roll orders or store card data |

---

## 3. Architecture: keep the public site static

Two options:

**A. Split (recommended).** Public site stays on GitHub Pages exactly as it is. The
admin is a separate Next.js app on its own domain (`admin.yourdomain.com`). Publishing
writes content, then triggers a rebuild via GitHub's `repository_dispatch`.

- Storefront stays free, fast, CDN-backed, and **cannot be taken down by an admin bug**
- Content changes appear after a ~30s rebuild, not instantly
- Two deployments to operate

**B. Merge.** Next.js serves both public and admin.

- One codebase, instant updates, easier previews
- The storefront now depends on a running server and a database
- You give up the thing that currently makes the site excellent

**Take A.** A car storefront must be fast and always up; an admin panel is allowed to be
slow and occasionally down. Keeping them separate means an admin outage is invisible to
buyers. Revisit only if the ~30s publish lag proves genuinely annoying.

> **You need a custom domain before building auth.** Passkeys bind to an "RP ID"
> (the domain). On `cloudstrucc.github.io` the RP ID would be `github.io`, shared with
> every GitHub Pages site in existence — unacceptable for credential scoping. Buy the
> domain first; it is a prerequisite, not a nice-to-have.

---

## 4. Auth design (`/auth/*`)

### Passkeys
Standard WebAuthn, via SimpleWebAuthn:

**Registration** — server issues a challenge (stored, single-use, ~5 min TTL) →
`navigator.credentials.create()` → server verifies and stores credential ID, public key,
signature counter, AAGUID, transports.

**Authentication** — server issues a challenge → `navigator.credentials.get()` → verify
signature against the stored public key; reject non-monotonic sign counts.

Settings that matter:
- `residentKey: "required"`, `userVerification: "preferred"` — enables usernameless sign-in
- Conditional UI (autofill) so the passkey is offered in the sign-in field
- **Allow multiple credentials per user** and prompt to add a second device after first login

### Account recovery — do not skip this
A passkey lost with its only device means a locked-out admin. Mitigations, in order:
1. Encourage a second passkey at registration (phone + laptop)
2. Single-use recovery codes, shown once, stored hashed
3. Another admin can issue a fresh invite to re-enrol
4. A CLI break-glass command with server access

Decide this before launch, not after someone is locked out.

### Sessions
`HttpOnly`, `Secure`, `SameSite=Lax` cookie holding an opaque ID (not a JWT) so
revocation is immediate. Rotate on privilege change. ~30 min idle / 12 h absolute for
admin. A session list in Team with "revoke".

### Invites
```
admin generates  → token = 32 random bytes, base64url
                 → store SHA-256(token) only, with role, inviter, expiry (7d), email (optional)
link             → https://admin.example.com/auth/accept?code=<token>
redeem           → hash, constant-time lookup, check unused + unexpired
                 → immediately run passkey registration
                 → mark consumed in the SAME transaction as user creation
```
- Code field is prefilled from the query string, and manually enterable as a fallback
- `Referrer-Policy: no-referrer` on the accept page — URLs leak via referrer and history
- Rate-limit redemption by IP and by code
- **Bootstrap:** the first admin cannot be invited. Ship a CLI (`pnpm admin:create`)
  gated on server access.

### Authorization
Roles from day one, even with one user: `owner` > `admin` > `editor`. Check server-side
in every Server Action. Never trust a role claim from the client.

---

## 5. Data model (first cut)

```
users            id, email?, name, role, created_at, last_seen_at
credentials      id, user_id, public_key, counter, transports, aaguid, nickname, created_at
invites          id, token_hash, role, email?, invited_by, expires_at, consumed_at, consumed_by
sessions         id, user_id, created_at, last_used_at, expires_at, ip, user_agent
audit_log        id, actor_id, action, entity, entity_id, before, after, created_at, ip

vehicles         id, slug, year, make, model, trim, km, price, status, created_at
                 (today's cars.json + gen_velocity CARS, unified)
vehicle_assets   id, vehicle_id, format, kind(jpg|svg), storage_key, width, height
services         id, name, description, price, active
orders           id, customer_id, vehicle_id?, status, total, stripe_payment_intent, created_at
customers        id, email, phone, name, created_at

templates        id, name, status(draft|ready|active), tokens_json, created_by, created_at
template_pages   id, template_id, page_key, layout_json, thumbnail_key
uploads          id, template_id?, storage_key, mime, original_name, created_at
notifications    id, user_id?, kind, payload, read_at, created_at
```

`audit_log` is not optional — it is what makes Logs & Troubleshoot real rather than a
tile showing stack traces.

---

## 6. The workspace tiles

Dashboard at `/admin`, tiles linking to sections. Honest assessment of each:

| Tile | Scope | Notes |
|---|---|---|
| **Vehicles** | CRUD + publish | Replaces hand-editing `cars.json` + `CARS`. **Build this first** — it is the only tile that pays for itself immediately. Publishing triggers ad regeneration + site rebuild. |
| **Services** | CRUD | Straightforward. Needs you to define what a "service" is here. |
| **Orders** | Stripe-backed | Real money, real PII. Use Stripe Checkout; never store cards. Largest compliance surface. |
| **Team** | Invites, roles, revoke | Covered in §4. Small and well-defined. |
| **Notifications** | In-app feed | Cheap if it reads `audit_log`. Expensive if it means email/SMS fan-out — decide which. |
| **Logs & Troubleshoot** | Audit log + build status | Show `audit_log` and the last GitHub Actions runs. Do **not** surface raw server logs to the browser. |
| **Site Settings** | Auth, kill switch, categories, templates | "Turn site off" on a static host means publishing a maintenance page and halting rebuilds — it cannot be a runtime flag. |

Note that "Products" became **Vehicles**. If you genuinely mean parts/accessories
alongside cars, that is a second catalogue with its own model — worth deciding now.

---

## 7. Site templates + AI generation

This is the most ambitious item by a wide margin, and the one most likely to
disappoint if built as described. Being direct about why:

**"Upload a Figma/PDF/image, get back a theme in our exact CSS framework" is not
reliably achievable.** An LLM given a screenshot will produce something plausible that
is subtly wrong — spacing that drifts, invented class names, layouts that break at
breakpoints you did not test. Shipped to a non-technical user as "describe it and we
build it", that becomes a support burden.

**What does work: constrain the output space.**

1. Define a **design-token schema** (colours, type scale, radii, spacing, density) and a
   **fixed library of section components** (hero, vehicle grid, detail, contact, footer).
2. The model's job is *not* to write CSS. It is to emit **validated JSON** — token values
   plus an ordered list of sections with their props.
3. Validate against a Zod schema. Reject and retry on failure. Never `eval` model output,
   never inject model-authored CSS or HTML into the page.
4. Render the preview from that JSON with your existing components, so output is
   *by construction* on-theme.

Uploads feed **context, not output**: extract a palette from an image, pull real
structure from the Figma REST API (not a screenshot), extract text from a PDF. For
uploaded HTML/CSS, parse computed styles to infer tokens — do not adopt their CSS.

The chat is a constrained tool-calling loop (`set_tokens`, `add_section`,
`reorder_sections`, `set_copy`), not an open-ended coding agent. Narrow surface, every
call schema-validated.

State machine as described: `draft → ready → active`. Editing locks while `active`;
cloning to a new draft is the escape hatch. One default template ships; new ones are
created by cloning.

**This is 2–3 months on its own.** Phase it last, and consider whether a curated set of
three or four hand-built themes with token customisation delivers 80% of the value in
2% of the time. My honest advice: build that first and only attempt generation if users
actually ask for it.

---

## 8. Phasing

| Phase | Scope | Rough effort |
|---|---|---|
| **0** | Custom domain, Next.js skeleton, Postgres, CI | 3–5 days |
| **1** | Passkey auth, sessions, invites, Team tile, audit log, CLI bootstrap | 1.5–2 weeks |
| **2** | Vehicles CRUD + publish pipeline → GitHub dispatch → existing `build.py` | 2 weeks |
| **3** | Site Settings, Logs & Troubleshoot, Notifications | 1.5 weeks |
| **4** | Services, Customers | 1 week |
| **5** | Orders + Stripe | 3–4 weeks (compliance-heavy) |
| **6** | Templates: tokens + fixed sections + preview, no AI | 3 weeks |
| **7** | AI template assistant | 6–10 weeks |

**Ship after Phase 2.** That is the point where you stop hand-editing JSON and running
`regen.sh`, which is the actual day-to-day win. Everything after is additive.

Total to Phase 7 is roughly **5–6 months of focused full-time work**. Worth stating
plainly before committing.

---

## 9. Security checklist

- [ ] Custom domain before any WebAuthn work (RP ID scoping)
- [ ] CSP without `unsafe-inline`; HSTS; `Referrer-Policy: no-referrer` on `/auth/*`
- [ ] Rate-limit sign-in, invite redemption, uploads
- [ ] Invite tokens stored hashed; constant-time comparison; single-use and transactional
- [ ] Uploads: validate magic bytes not extensions, cap size, serve from a separate
      origin, never execute
- [ ] Anthropic key server-side only; cap spend per user; log prompts for abuse review
- [ ] Orders: Stripe-hosted, PCI SAQ-A scope only
- [ ] PII in `customers`/`orders` — decide retention and deletion before collecting any
- [ ] Audit log append-only; admins cannot delete their own entries

---

## 10. What I would cut

If this were mine, v1 would be: **passkey auth, Team, Vehicles CRUD, publish.** That
replaces the manual workflow and is ~4 weeks.

Orders, Services, Notifications and Templates are each a product decision that deserves
evidence of demand first. A site selling five cars does not obviously need an order
system or a template engine — and building them before anyone has asked is the most
reliable way to end up maintaining software nobody uses.
