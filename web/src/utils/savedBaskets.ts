/**
 * SU11A-64 (SU11A-63 L2): the mobile app's synced basket (one saved-basket row
 * with this name, xxl-super-mobile src/lib/basket-context.tsx) is not a saved
 * basket for the user: "הסלים שלי" does not list it. The API also refuses to
 * delete or rename it (409, api/routers/saved_baskets.py); GET /baskets still
 * returns it, because the app finds its row there.
 */
export const APP_BASKET_NAME = '__xxl_mobile_basket__';

export const listedBaskets = <T extends { name: string }>(all: T[]): T[] =>
  all.filter(b => b.name !== APP_BASKET_NAME);
