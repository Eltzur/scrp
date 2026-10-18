/**
 * Terms of use: version, date and operator (SU11A-44, designed in SU11A-42).
 *
 * TERMS_VERSION must match api/terms.py and the app's src/legal/terms.ts; a new
 * version makes GET /me/terms answer `required` and users are asked again.
 * This file is the ONLY place the web names the legal entity.
 */
export const TERMS_VERSION = '2026-10-1';

export const TERMS_DATE = '18 באוקטובר 2026';

// TODO(SU11A-42-ENTITY): legal entity name — Dude must confirm before the terms go live
export const LEGAL_ENTITY_NAME = '[שם הישות המשפטית]';
