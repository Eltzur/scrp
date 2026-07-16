# Portal — Handoff

Cross-cutting handoff for the portal surface (xxl.co.il) and anything that spans multiple verticals. Individual verticals keep their own handoff files (docs/super/handoff_super.md, docs/flights/handoff_flights.md, xxl-flights repo). This file is for work that touches the shared web/ build, portal-only pages, or policies covering the whole product (legal, privacy, cross-vertical UX).

Session naming: `XXL-x.y.z` (semver), per CLAUDE.md.

## Locked infrastructure facts

- Kamatera VPS 185.229.226.190 (Tel Aviv, Ubuntu 24.04) is PRIMARY for all xxl.co.il surfaces, served by nginx. Portal (xxl.co.il + www.xxl.co.il) and supermarket (super.xxl.co.il) SHARE ONE React build (web/dist) — isPortalHostname() in web/src/utils/hostname.ts switches PortalPage vs AppShell at runtime. Deploying web/ updates both at once.
- Deploy: `.\scripts\deploy_frontend.ps1` from Windows (builds + scp's to Kamatera). Hostinger is cold DR fallback only.
- Auth: Supabase (ES256/JWKS), shared across verticals. Supabase auth is LIVE (not pending) — signup/login routes work today via AuthContext.tsx.
- Payment architecture decision (XXL-1.0.1): third-party PCI-DSS certified gateway, tokenized. XXL infrastructure never stores raw card PAN/CVV. Bit/Paybox via their own app-redirect flows — same rule applies. Do not add a raw card-number field to any schema, ever.
- Flights vertical is a separate repo (github.com/Eltzur/xxl-flights) with its own footer/legal surface. It is NOT updated by this session — needs its own follow-up session to link to the privacy policy/disclaimer pages built here.

## Open decisions

- English version of portal pages (PortalPage, ComingSoonPage, and now /privacy, /disclaimer): deferred. Everything is Hebrew-only for now, consistent with existing portal pages.
- Dedicated privacy@xxl.co.il inbox: not yet created. Privacy policy currently points to info@xxl.co.il — revisit before go-live.
- DPO appointment: not yet made. Amendment 13 compliance assessment (docs/compliance_amendment13.md) flags this as likely required once payment/financial data processing begins — needs attorney confirmation of exact trigger point.

## Session log

### Session XXL-1.0.1 (July 12, 2026) — Legal/privacy foundation

**Goal:** liability disclaimer, privacy policy, cookie consent rework, and an Amendment 13 (Tikun 13) compliance checklist, covering both live verticals (supermarket + flights) and the future data model (full profile + payment).

**Shipped:**
- `docs/handoff_portal.md` (this file) — established.
- Shared `Footer.tsx` component with privacy/disclaimer/contact links, mounted consistently across PortalPage, ComingSoonPage, and AppShell (which previously had no footer at all).
- `/privacy` route — full Hebrew privacy policy, written to cover current data collection (email signups, Supabase auth, favorites, baskets, GA4) and the planned future collection (full name, phone, ID number, address, payment via third-party PCI-DSS gateway) so it's ready before those fields exist in the schema.
- `/disclaimer` route — liability disclaimer covering both verticals: mirrored third-party data (SerpApi/Google Flights; Israeli government price-transparency XML feeds), no ownership/verification/guarantee, final price/availability governed by the airline/retailer at time of transaction.
- Cookie banner reworked from implicit X-dismiss-consent to explicit accept/reject buttons; GA4 only initializes on explicit accept.
- `docs/compliance_amendment13.md` — Amendment 13 applicability checklist, fact-specific items marked NEEDS COUNSEL.

**Not done this session (flagged for follow-up):**
- fly.xxl.co.il (xxl-flights repo) footer does not yet link to /privacy or /disclaimer on xxl.co.il — needs a small follow-up session in the flights repo.
- No real signup/user counts exist yet (DB is empty) — Amendment 13 threshold questions (registration, notification, DPO trigger timing) stay open until there's real volume to assess against.

**Next session:** attorney review of drafted text; once a payment gateway vendor is selected, revisit the DPO/security-tier assessment in docs/compliance_amendment13.md with confirmed specifics.

### Session XXL-1.0.2 (July 16, 2026) — fly.xxl.co.il footer

**Goal:** close the fly.xxl.co.il footer gap flagged as follow-up in XXL-1.0.1. Separate repo (xxl-flights, github.com/Eltzur/xxl-flights) — not the shared scrp web/ build — so it needed its own session and commit.

**Shipped (in the xxl-flights repo):**
- `frontend/src/components/Footer.tsx` — Hebrew footer mounted in `App.tsx` (after the search-form content, inside the root shell, so it renders on the single-page flights app). Matches the repo's emerald/gray/border-t visual language; plain `<a>` anchors (no router in this app).
- Footer links OUT to the canonical legal pages — `https://xxl.co.il/privacy` and `https://xxl.co.il/disclaimer` (built in XXL-1.0.1), opening in a new tab (`target="_blank" rel="noopener noreferrer"`) to preserve flight-search state. Deliberately did NOT duplicate the policy/disclaimer text into the flights repo — those xxl.co.il pages are the single source of truth and already cover fly.xxl.co.il explicitly, so linking out avoids two copies drifting apart. Contact: `mailto:info@xxl.co.il`.
- **No cookie banner added.** Confirmed live that the flights bundle loads zero analytics/tracking cookies (no gtag/GA4 — only Google Fonts). A consent banner is only mandatory once a non-essential cookie is introduced; not before. If GA4 or similar is ever added to flights, a banner becomes required at that point.

**Deploy:** xxl-flights uses its own path (NOT scrp's deploy_frontend.ps1). Frontend build scp'd `dist/*` to the `~/fly_deploy` staging dir, then `sudo cp` into the www-data-owned `/var/www/fly.xxl.co.il` web root (per FL10A-3 deploy notes in docs/flights/handoff_flights.md).

**Next:** English footer labels still deferred (destination legal pages are Hebrew-only). Revisit if/when the portal legal pages get an English version.
