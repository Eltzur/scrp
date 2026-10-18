# SU11A-42 — UGC, report, block and terms: investigation report (Stage 1, read-only)

Prepared 2026-10-18. Nothing was changed except this file. Nothing was run against the server or the database; all findings come from the code in `C:\scrp` (API + web) and `C:\scrp\xxl-super-mobile` (`m/` below).

Apple guideline 1.2 (apps with user-generated content) needs: (a) terms users agree to, with zero tolerance for objectionable content and abusive users; (b) a way to report content; (c) a way to block abusive users; (d) published contact info. The developer must also act on reports within 24 hours (remove the content, eject the user).

## Summary

- **Only one kind of content is visible to other users: item ratings (1-3) with an optional comment.** It is shown in the mobile app (product screen → reviews tab) and on the web (product modal → reviews tab). Comments are **anonymous**: the public response carries no user id, name or email.
- Nothing else is shared. Saved baskets, favorites, flight alerts and saved searches are private to their owner. `users.display_name` exists but nothing writes or shows it. There are no photos, price reports, shared lists or profiles.
- **Report:** exists on both mobile and web, for every comment. It stores a row and emails info@. It does **not** hide the comment, and **user reports never reach the admin queue** (the queue lists only non-active ratings). There is no endpoint to hide a rating or ban a user, so acting within 24 hours means manual SQL plus the Supabase dashboard today.
- **Block:** does not exist anywhere.
- **Terms:** the mobile "תנאי שימוש" screen is a placeholder sentence. The web page `/disclaimer` ("תנאי שימוש וכתב ויתור אחריות") has no clauses on user content, abuse, reporting, blocking or account termination.
- **Sign-up consent:** none on mobile or web. No checkbox, no consent text, nothing stored.
- **Contact:** info@xxl.co.il is published in the app (Help screen, privacy summary, deletion screen) and on the web (footer, privacy, terms, accessibility).

## 1. User-generated content visible to others

| Content | Created where | Endpoint | DB | Who can see it |
|---|---|---|---|---|
| Rating 1-3 + optional comment (≤ 2000 chars) | Mobile `m/src/app/product-detail.tsx` (reviews tab form, `submitRating` in `m/src/api/client.ts:404`); web `web/src/components/ReviewsPanel.tsx` (form, `web/src/api/client.ts`) | `POST /items/{item_code}/rating` (auth; upsert, one per user per item) — `api/routers/ratings.py:138` | `ratings` (`user_id`, `item_code`, `rating`, `comment`, `status` active / pending_review / hidden) — `db/migrations/su10r1_ratings.sql` | **Everyone, no sign-in needed**: `GET /items/{item_code}/ratings` (`api/routers/ratings.py:248`) returns active rows only, with `id`, `rating`, `comment`, `created_at`, `updated_at`. No author identifier. Shown in mobile `CommentRow` (`m/src/app/product-detail.tsx:73`) and web `ReviewsPanel` (inside `ProductDetailModal`). The aggregate (count, average) is also public. |
| The author's own ratings, any status | — | `GET /me/ratings` (auth) — `api/routers/ratings.py:295` | `ratings` | The author only |
| Report on a rating + optional reason (≤ 1000) | see section 2 | `POST /ratings/{id}/report` | `rating_reports` | Not public (admins, info@ mailbox) |

Checked and **not** visible to other users:
- `saved_baskets` — every endpoint checks the owner (`api/routers/saved_baskets.py:84-94`, `_owned_or_404`); no share links.
- `favorites` — per user (`api/routers/favorites.py`); mobile screen is a placeholder.
- Mobile "רשימות" (`m/src/app/lists.tsx`) — placeholder, no data.
- `flights.alerts`, `flights.saved_searches` (`xxl-flights/backend/db/schema.sql:63, 76`) — per user, private.
- `users.display_name` — column only; no code writes or reads it.
- Scan history, local basket, city, radius, theme — on the device only.

Moderation already in place for ratings (`api/routers/ratings.py:1-18, 91-200`):
- A term from `rating_blacklist` hides the rating immediately (`status = 'hidden'`), files a system report (`source = 'blacklist'`) and emails info@ with the author's email. The author is not told.
- Editing never puts a hidden or pending rating back to active.
- `GET /admin/ratings/pending` (`ADMIN_USER_EMAILS` allowlist, fails closed) lists **non-active** ratings with their reports. It is view-only; there is no endpoint to change status.

## 2. The existing report mechanism

- **Mobile entry point:** a flag icon on every published comment (`CommentRow`, `m/src/app/product-detail.tsx:93-104`). Signed out: an alert asks the user to sign in (`he.ratings.reportSignIn`). iOS: `Alert.prompt` asks for an optional reason. Android: a confirm alert, no reason (Alert.prompt is iOS-only). Result: "reported" or "failed" alert (`m/src/app/product-detail.tsx:224-250`). Client: `reportRating` (`m/src/api/client.ts:434`).
- **Web entry point:** a report button on every comment in `ReviewsPanel` (`web/src/components/ReviewsPanel.tsx:72-80, 130-139`). Signed out: a toast asks the user to sign in. Reason through `window.prompt`. Toast on success or failure.
- **Endpoint:** `POST /ratings/{rating_id}/report` (auth, `api/routers/ratings.py:210-245`). 404 if the rating does not exist. No uniqueness check (repeat reports from different users are the signal).
- **Stored:** a row in `rating_reports` (`rating_id`, `reporter_user_id`, `reason`, `source = 'user'`, `created_at`).
- **After a report:** the rating **stays public** (by design: "a user report only flags"). A background task emails info@xxl.co.il through Hostinger SMTP with the rating id, item, the **reporter's email** and the reason (`_notify_report`, `api/routers/ratings.py:473-491`). It is logged.
- **Gap 1:** `GET /admin/ratings/pending` lists only `status <> 'active'`, so a user-reported rating that is still active **never appears in the queue**. The email is the only signal.
- **Gap 2:** no endpoint hides a rating or bans a user. Removing content means SQL on the server (`UPDATE ratings SET status = 'hidden' ...`); ejecting a user means the Supabase dashboard (ban) — and our API does not check bans.
- **Coverage:** the report mechanism covers every comment shown to other users, on mobile and web. The only gap in coverage is the user's own comment: it shows the flag too (the response cannot tell which comment is the caller's).

## 3. Terms of use today

- **Mobile:** drawer item "תנאי שימוש" (`he.drawer.terms`, `m/src/components/app-drawer.tsx:223-225`) opens `/terms` (`m/src/app/terms.tsx`), which renders `LegalPage` with `he.legal.termsTitle` and `he.legal.termsBody` (`m/src/i18n/he.ts:387-390`). The body is one placeholder sentence: "מסמך תנאי השימוש טרם נוסח. הנוסח המחייב יפורסם כאן לפני השקת האפליקציה." No link to the web terms. The drawer is reachable signed out.
- **Web:** `web/src/pages/DisclaimerPage.tsx`, route `/disclaimer` on both hosts, footer link "תנאי שימוש וכתב ויתור". Text lives in the JSX. Last updated 12 July 2026. Sections: nature of the service, data sources, no accuracy warranty, final price set by the seller, limitation of liability, changes, contact. **No clauses on user content, prohibited content, reporting, blocking, moderation or account termination.**
- **Mismatch to fix:** the privacy policy says "XXL בע"מ", the accessibility page says "XXL אנטרפרייזס", and `legal/` holds a sole-trader (עוסק פטור) certificate. The terms must name the right legal entity (open question 1).

## 4. Sign-up consent today

- **Mobile** `m/src/app/sign-up.tsx`: email, password, submit, link to sign in, privacy link (SU11A-33). No checkbox, no "by signing up you agree" text.
- **Web** `web/src/pages/SignupPage.tsx`: email, password, submit, link to sign in. No checkbox, no consent text, no links to terms or privacy.
- **Server:** sign-up goes straight to Supabase (`supabase.auth.signUp`); our `users` row is created on the first authenticated API call (`_upsert_user`, `api/auth.py:122-127`). Nothing about consent is stored anywhere.

## 5. Proposed block-user design

The content is anonymous, so the design must block **the author of a rating** without ever telling the blocker who that author is. The server resolves the author from the rating id; the client never sees a user id. Auth is API-level (FastAPI + `get_current_user`; the API connects as `scrp_app`; there is no RLS in this database), so the new table follows the same pattern.

### DB (migration below, not applied)
`user_blocks`: `id` (opaque handle for unblocking), `blocker_id`, `blocked_id` (both `users.id`, `ON DELETE CASCADE`), `source_rating_id` (the rating that triggered the block, `ON DELETE SET NULL`, used only to label the row in the management list), `created_at`. Unique pair, and a check that blocker ≠ blocked.

### API
- `POST /ratings/{rating_id}/block-author` (auth). Looks up `ratings.user_id`; 404 if no such rating; **400 `cannot_block_self`** if it is the caller; inserts with `ON CONFLICT DO NOTHING` (idempotent); returns `{ok: true}` and no user id. It also files a report row with `source = 'block'` and emails info@, so a block also reaches the moderator (open question 3).
- `GET /me/blocks` (auth). Returns `[{id, created_at, item_name, comment_excerpt}]`. The label comes from `source_rating_id` (item name + first ~80 chars of that comment, which was public anyway). No user ids, no emails.
- `DELETE /me/blocks/{id}` (auth). Deletes only where `blocker_id` = caller; 404 otherwise. 204.
- `GET /items/{item_code}/ratings` gains **optional** auth (`get_current_user_optional`). Signed in: rows by blocked authors are left out — `AND NOT EXISTS (SELECT 1 FROM user_blocks b WHERE b.blocker_id = :uid AND b.blocked_id = ratings.user_id)` — and each row gets `is_mine: bool` so the client can hide Report/Block on the caller's own comment. Anonymous: unchanged.
- The aggregate (count, average) stays computed over all active ratings (open question 4).

### Each UGC feed
There is exactly one feed: the comments list of `GET /items/{code}/ratings`. It is used by mobile `product-detail.tsx` and web `ReviewsPanel`. `GET /me/ratings` shows only the caller's own rows, so no filter is needed. The admin queue is unaffected.

### Mobile UI
- On each comment that is not the caller's: replace the flag button with a "⋯" button that opens an action sheet: "דיווח על התוכן", "חסימת המשתמש", "ביטול". The action sheet uses `Alert.alert` with buttons, so it works the same on Android, unlike `Alert.prompt`.
- Block → confirm alert "לחסום את המשתמש? הביקורות שלו/ה לא יוצגו לך יותר. אפשר לבטל את החסימה בהגדרות." → `POST` → refetch the ratings with the token → toast or alert "המשתמש נחסם".
- Signed out: the same sign-in prompt as Report.
- `fetchRatings` sends the token when signed in (today it never does).
- **Settings → "משתמשים חסומים"** (signed in only), new screen `m/src/app/blocked-users.tsx`: the list from `GET /me/blocks`, with the date, the item name and the comment excerpt, and a "ביטול חסימה" button on each row. An empty state when there are none.

### Web UI
Same "⋯" / two buttons in `ReviewsPanel` (the axios interceptor already sends the token, so the GET is filtered automatically once the API changes). A web management page is optional: a block made on the web is server-side, so it shows in the app's list (open question 6).

### Smallest compliant alternative
Not needed: there **is** user-visible UGC from other users (comments), so Apple will expect a real block, not just hooks.

## 6. Proposed in-app terms and consent

### Terms screen
- `m/src/app/terms.tsx` renders a local array of sections from `he.legal.terms` (title + paragraphs), scrollable, no network. At the bottom: links to the privacy policy (in-app `/privacy` screen and `https://super.xxl.co.il/privacy`) and to the full web terms (`https://xxl.co.il/disclaimer`), the contact email, the version and the date.
- The web `/disclaimer` page gets the same sections 3-7 so the two never contradict.
- Constant `TERMS_VERSION = '2026-10-1'` in mobile, web and API.

Proposed Hebrew text (to be checked by you and, ideally, a lawyer; the entity name is a placeholder until open question 1 is answered):

> **תנאי שימוש — SUPER XXL**
> עודכן לאחרונה: [תאריך] · גרסה 2026-10-1
>
> **1. כללי**
> השימוש באפליקציית SUPER XXL ובאתרי XXL (״השירות״) כפוף לתנאים אלה ולמדיניות הפרטיות. הרשמה לשירות או שימוש בו מהווים הסכמה לתנאים. אם אינכם מסכימים להם, אל תשתמשו בשירות.
>
> **2. אופי השירות**
> השירות משווה מחירים על סמך מידע שרשתות השיווק מפרסמות לפי חוק. המידע מוצג כפי שהוא, ואיננו יכולים להבטיח שהוא מדויק או עדכני. המחיר הסופי נקבע על ידי הרשת בעת הקנייה.
>
> **3. חשבון משתמש**
> אתם אחראים לשמירת הסיסמה שלכם ולכל פעולה שנעשית בחשבון. אפשר למחוק את החשבון בכל עת בהגדרות › מחיקת חשבון.
>
> **4. תוכן שאתם מפרסמים**
> דירוגים וביקורות שאתם מפרסמים מוצגים לכל משתמשי השירות, בלי שמכם ובלי כתובת האימייל שלכם. אתם אחראים לתוכן שאתם מפרסמים, ובפרסומו אתם מרשים ל-XXL להציג אותו בשירות.
>
> **5. אפס סובלנות לתוכן פוגעני ולמשתמשים פוגעניים**
> אסור לפרסם תוכן פוגעני, מעליב, מאיים, מטריד, גזעני, מיני, אלים, משמיץ, מפר זכויות או בלתי חוקי, וגם לא פרסומות, ספאם או פרטים אישיים של אחרים. אין לנו שום סבלנות לתוכן כזה או למשתמשים שמפרסמים אותו: התוכן יוסר, והחשבון עלול להיחסם או להימחק, גם ללא הודעה מוקדמת.
>
> **6. דיווח וחסימה**
> ליד כל ביקורת אפשר לדווח עליה ולחסום את מי שכתב אותה. ביקורות של משתמש שחסמתם לא יוצגו לכם יותר, ואפשר לבטל את החסימה בהגדרות › משתמשים חסומים. אנחנו בודקים כל דיווח תוך 24 שעות, מסירים תוכן שמפר את התנאים ונוקטים צעדים נגד מי שפרסם אותו.
>
> **7. הפסקת שימוש וסגירת חשבון**
> אנחנו רשאים להסיר תוכן, להגביל חשבון, להשעות אותו או לסגור אותו אם לדעתנו הופרו תנאים אלה.
>
> **8. הגבלת אחריות**
> במידה המרבית המותרת לפי דין, XXL לא תישא באחריות לנזק ישיר או עקיף שנגרם מהסתמכות על המידע בשירות או מתוכן שפרסמו משתמשים אחרים.
>
> **9. שינויים בתנאים**
> אנחנו עשויים לעדכן תנאים אלה מעת לעת. על שינוי מהותי נודיע בשירות, וייתכן שנבקש מכם לאשר את התנאים מחדש.
>
> **10. יצירת קשר**
> לשאלות, לדיווח על תוכן או על משתמש: info@xxl.co.il
> מדיניות הפרטיות: https://super.xxl.co.il/privacy
> התנאים באתר: https://xxl.co.il/disclaimer

### Consent at sign-up (mobile and web)
- A required checkbox above the submit button; the button stays disabled until it is ticked:
  > ☐ קראתי את [תנאי השימוש] ואת [מדיניות הפרטיות] ואני מסכים/ה להם.
  Both phrases are links (mobile: push `/terms` and `/privacy`, the form keeps its state; web: open `/disclaimer` and `/privacy` in a new tab).
- **Storage, with no new endpoint at sign-up:** pass `options.data = { terms_version, terms_accepted_at }` to `supabase.auth.signUp`. Supabase keeps it in the auth user's metadata, which arrives in the access token as `user_metadata`. `_upsert_user` copies it into `users.terms_version` / `users.terms_accepted_at` the first time it sees the user (only when our columns are still NULL). This survives email confirmation, because our `users` row does not exist until the first authenticated call.
- **Existing users** (no consent recorded): `POST /me/terms` (auth, body `{version}`) sets both columns. The app and the web ask for it the first time the user tries to post a rating ("כדי לפרסם ביקורת יש לאשר את תנאי השימוש" + the checkbox), which is the moment the terms matter. Server-side enforcement on `POST /items/{code}/rating` (403 `terms_required`) stays **off** behind an env flag until old app builds are gone (see risks).

## 7. Files to change or create

**API / DB (`C:\scrp`)**
- `db/migrations/su11a42_ugc_blocks_terms.sql` — new (below).
- `api/routers/ratings.py` — optional auth + block filter + `is_mine` in `get_ratings`; `POST /ratings/{id}/block-author`; report `source = 'block'`; `RatingOut.is_mine`. Optionally (open question 5): admin queue includes active ratings with user reports, and `POST /admin/ratings/{id}/status`.
- `api/routers/blocks.py` — new: `GET /me/blocks`, `DELETE /me/blocks/{id}`, `POST /me/terms`.
- `api/main.py` — include the new router.
- `api/auth.py` — `_upsert_user` copies terms metadata when the columns are NULL; optional `banned_at` check for posting (open question 5).
- `api/tests/test_smoke.py` — block / unblock / self-block / filter / cascade on account deletion / anonymous GET unchanged.

**Web (`C:\scrp\web`)**
- `src/components/ReviewsPanel.tsx` — block action, hide actions on `is_mine`, refetch after block.
- `src/api/client.ts` — `blockRatingAuthor`, `getBlocks`, `unblock`, `acceptTerms`; `RatingOut.is_mine`.
- `src/i18n/locales/he.json`, `en.json` — new `ratings.*` keys (ReviewsPanel uses i18n).
- `src/pages/SignupPage.tsx`, `src/components/AuthContext.tsx` — consent checkbox, `options.data`.
- `src/pages/DisclaimerPage.tsx` — UGC / zero-tolerance / report-and-block / termination sections, new date.
- `src/pages/PrivacyPolicyPage.tsx`, `src/pages/DeleteAccountPage.tsx` — mention block lists and the consent record (stored, deleted with the account).
- Optional: `src/pages/BlockedUsersPage.tsx` + route.

**Mobile (`C:\scrp\xxl-super-mobile`)**
- `src/app/product-detail.tsx` — "⋯" actions (report + block), hidden on own comment; token on `fetchRatings`; refetch after block.
- `src/api/client.ts`, `src/types/api.ts` — token-aware `fetchRatings`, block / unblock / list / acceptTerms; `is_mine`.
- `src/app/blocked-users.tsx` — new; `src/app/_layout.tsx` — register the screen; `src/app/(tabs)/settings.tsx` — "משתמשים חסומים" row.
- `src/app/terms.tsx` (+ `src/components/legal-page.tsx` if it needs sections) — real terms.
- `src/app/sign-up.tsx`, `src/components/auth-form.tsx` (checkbox), `src/lib/auth-context.tsx` (`options.data`).
- `src/i18n/he.ts` — terms text, block strings, consent strings; privacy summary line on blocks.

**Docs:** `docs/store_privacy_inventory.md`, `docs/store_submission_checklist.md` (Apple 1.2 review note: where report, block and terms are), handoffs.

### Migration SQL (NOT applied)

```sql
-- SU11A-42 — user blocks + terms consent. NOT APPLIED. ADDITIVE AND IDEMPOTENT.
-- Apply BEFORE the API that reads user_blocks is deployed.
--   cat ~/scrp/db/migrations/su11a42_ugc_blocks_terms.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1
BEGIN;

CREATE TABLE IF NOT EXISTS user_blocks (
    id               SERIAL      PRIMARY KEY,
    blocker_id       TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id       TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_rating_id INTEGER     NULL REFERENCES ratings(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT user_blocks_pair_uniq UNIQUE (blocker_id, blocked_id),
    CONSTRAINT user_blocks_not_self  CHECK (blocker_id <> blocked_id)
);
-- The unique pair index serves "WHERE blocker_id = :uid"; this one serves the
-- CASCADE when a blocked account is deleted.
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked ON user_blocks (blocked_id);

ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version     TEXT        NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ NULL;
-- Only if open question 5 says yes:
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ NULL;

-- A block also files a report (open question 3). The inline CHECK from
-- su10r1_ratings.sql gets Postgres' default name; confirm with
--   \d rating_reports
-- before applying.
ALTER TABLE rating_reports DROP CONSTRAINT IF EXISTS rating_reports_source_check;
ALTER TABLE rating_reports ADD  CONSTRAINT rating_reports_source_check
    CHECK (source IN ('user', 'blacklist', 'block'));

GRANT SELECT, INSERT, UPDATE, DELETE ON user_blocks TO scrp_app;
GRANT USAGE, SELECT ON SEQUENCE user_blocks_id_seq  TO scrp_app;

COMMIT;
```

Account deletion needs no code change: `DELETE FROM users` cascades to both sides of `user_blocks`. The privacy and deletion pages must list it.

## 8. Risks

- **Public reviews endpoint:** adding `get_current_user_optional` to `GET /items/{code}/ratings` means a signed-in caller's token is verified on every product view. That helper "may raise 503" when the signing keys cannot be fetched. Wrap it so any auth failure answers as anonymous; otherwise a Supabase hiccup takes reviews down for signed-in users. It also upserts the `users` row on each call (existing behaviour of the helper; cheap, but one more write per product view).
- **Deploy order:** the migration must be applied before the API that queries `user_blocks`, or every signed-in ratings call fails. Then API → web → app build.
- **Play internal-testing build (1.2.1):** it never sends a token on the ratings GET, so it keeps working and simply sees no filtering. It has no block button. Terms enforcement on rating submit must stay off until that build is replaced, or rating from it breaks with 403.
- **Existing reviews:** unchanged. The filter only removes rows for a signed-in blocker. The aggregate is not changed (open question 4).
- **Sign-in:** untouched. Sign-up only gains a checkbox and `options.data`. Supabase answers sign-up for an already-registered email with a fake success (no metadata write), which is fine.
- **User metadata is user-editable** (`updateUser({ data })`). Good enough as a consent record; the server copies it once and never overwrites.
- **24-hour promise:** the terms text promises review within 24 hours. Today a user report is only an email, the admin queue does not show it, and hiding or banning is manual. Either add the small admin action (open question 5) or make sure the info@ mailbox is watched daily.
- **Privacy answers:** block lists and the consent record are new account-linked data. Data safety / App Privacy categories do not change (both fall under existing "Other user-generated content" / account data), but the policy text, the deletion page and the in-app summary should mention them.
- **Self-block and own comment:** without `is_mine` a user can report or try to block themselves. The server rejects self-blocks either way.

## 9. Open questions for you

1. **Legal entity name** for the terms: privacy says "XXL בע"מ", accessibility says "XXL אנטרפרייזס", and `legal/` has a sole-trader (עוסק פטור) certificate. Which is right?
2. Is the proposed Hebrew terms text acceptable as a base, and will a lawyer review it before submission?
3. Should a block also file a report (`source = 'block'`) and email info@? (Recommended: yes; Apple reviewers like blocks to notify the developer.)
4. Should blocked users' scores also drop out of the blocker's average and count, or only their comments? (Recommended: comments only; the score carries no identifiable content.)
5. Moderation tooling now or later: (a) include actively-reported ratings in `/admin/ratings/pending`; (b) `POST /admin/ratings/{id}/status` to hide; (c) `users.banned_at` checked on rating submit and report. Without (b) and (c), the 24-hour promise depends on manual SQL and the Supabase dashboard.
6. Web: block button only, or also a blocked-users page on the web?
7. Existing users: ask for consent at their first rating attempt (proposed), or on the next app open for everyone?
8. Should the web `/disclaimer` page be renamed to "תנאי שימוש" and also get the version/date, since the app will link to it as the full terms?

## 10. Decisions (18 Oct 2026)

**Approved defaults unless Dude says otherwise** (answers to section 9):

1. **Legal entity name: OPEN, to be decided by Dude.** The privacy page says XXL בע"מ, the accessibility page says another name, and `legal/` holds a sole-trader certificate.
2. Terms text: the section 6 draft is the base. Lawyer review is still Dude's call.
3. **A block also files a report** (`source = 'block'`) and emails info@.
4. **Blocked authors' scores are NOT removed from averages**; only their comments are hidden from the blocker.
5. **Moderation tools are added now:**
   - actively reported ratings appear in `/admin/ratings/pending`;
   - a hide endpoint;
   - a `users.banned_at` column, checked on rating submit and report.
6. **Web gets a block button only**, no blocked-users page. The list and unblock stay in the app.
7. **Existing users are asked for terms consent at their first rating.**
8. **Web `/disclaimer` is renamed "תנאי שימוש"** and gets the version and date.

**Status:**
- The migration SQL in section 7 is **NOT applied**. It must be applied before the API change; then API → web → app build.
- With decision 5, the migration also adds `users.banned_at`. With decision 3, it changes the `rating_reports` source CHECK.
- **Stage 2 (implementation) has not started.**
