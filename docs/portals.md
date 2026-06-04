# Chain Portal Reference

All scraper portals, credentials, and file-type availability.
Last updated: 2026-06-04.

---

## Shufersal — שופרסל

| Field | Value |
|---|---|
| Chain ID | 7290027600007 |
| Portal | https://prices.shufersal.co.il/FileObject/UpdateCategory |
| Portal type | Shufersal (custom HTTP, Azure Blob signed URLs) |
| Auth | None |
| PriceFull | catID=0 + `?storeId={N}` per store |
| Price (delta) | catID=1 + `?storeId={N}` per store |
| Delta available | ✅ Yes |
| Notes | Signed Azure Blob URLs expire ~30 min — fetched lazily per store (not upfront). 320 stores. Sub-formats: דיל, שלי, אקספרס, יש, יוניברס, BE. |

---

## Rami Levy — רמי לוי

| Field | Value |
|---|---|
| Chain ID | 7290058140886 |
| Portal | https://url.retail.publishedprices.co.il |
| Portal type | Cerberus |
| Username | RamiLevi |
| Password | (none) |
| Delta available | ✅ Yes |
| Notes | Canonical sub_chain_id = 001 (legacy sub='1' rows merged in 9k). |

---

## Osher Ad — אושר עד

| Field | Value |
|---|---|
| Chain ID | 7290103152017 |
| Portal | https://url.retail.publishedprices.co.il |
| Portal type | Cerberus |
| Username | osherad |
| Password | (none) |
| Delta available | ✅ Yes |
| Notes | Stores 002, 004 are warehouses — excluded from active_stores.yaml. |

---

## Victory — ויקטורי

| Field | Value |
|---|---|
| Chain ID | 7290696200003 |
| Portal | https://laibcatalog.co.il/webapi/api/ |
| Portal type | REST API (custom) |
| Auth | None |
| Delta available | ⬜ Not implemented |
| Notes | `getbranches` + `getfiles` REST endpoints. Geo-blocked outside Israel. PriceFull filenames served directly from the API. |

---

## Yochananof — יוחננוף

| Field | Value |
|---|---|
| Chain ID | 7290803800003 |
| Portal | https://url.retail.publishedprices.co.il |
| Portal type | Cerberus |
| Username | yohananof |
| Password | (none) |
| Delta available | ✅ Yes |
| Notes | Note spelling: code uses `yohananof` (one n). |

---

## Keshet — קשת

| Field | Value |
|---|---|
| Chain ID | 7290785400000 |
| Portal | https://url.retail.publishedprices.co.il |
| Portal type | Cerberus |
| Username | Keshet |
| Password | (none) |
| Delta available | ✅ Yes |
| Notes | Includes Kulinarik sub-brand (store_ids 102–105). |

---

## Carrefour — קרפור

| Field | Value |
|---|---|
| Chain ID | 7290055700007 |
| Portal | https://prices.carrefour.co.il |
| Portal type | PublishPrice (JS-embedded file listing) |
| Auth | None |
| Delta available | ❌ No (PublishPrice type not yet supported) |
| Notes | Publishes under Global Retail C.I. — includes Mega and Yenot Bitan sub-brands. Portal was down 2026-06-04. Geo-blocked outside Israel. |

---

## Tiv Taam — טיב טעם

| Field | Value |
|---|---|
| Chain ID | 7290873255550 |
| Portal | https://url.retail.publishedprices.co.il |
| Portal type | Cerberus |
| Username | TivTaam |
| Password | (none) |
| Delta available | ❌ Excluded — no daily Price delta files |
| Notes | 46 retail stores (7 ליקוט warehouse stores excluded). |

---

## King Store — קינג סטור

| Field | Value |
|---|---|
| Chain ID | 7290058108879 |
| Portal | https://kingstore.binaprojects.com |
| Portal type | Bina Projects (JSON API, no auth) |
| Auth | None |
| Delta available | ⬜ Not implemented |
| Notes | Arab-sector coverage. Files are ZIP not gzip (magic PK bytes). 3 endpoints: Select_Store, MainIO_Hok (WFileType=4 for PriceFull), Download. |

---

## Shefa Birkat Hashem — שפע ברכת השם

| Field | Value |
|---|---|
| Chain ID | 7290058134977 |
| Portal | https://shefabirkathashem.binaprojects.com |
| Portal type | Bina Projects (JSON API, no auth) |
| Auth | None |
| Delta available | ⬜ Not implemented |
| Notes | Haredi sector. 30 stores configured, 22 publishing PriceFull. |

---

## Shuk Hayir — שוק העיר

| Field | Value |
|---|---|
| Chain ID | 7290058148776 |
| Portal | https://shuk-hayir.binaprojects.com |
| Portal type | Bina Projects (JSON API, no auth) |
| Auth | None |
| Delta available | ⬜ Not implemented |
| Notes | 20 stores configured, 19 publishing. Store 304 = online hub (excluded). |

---

## Fresh Market — פרש מרקט

| Field | Value |
|---|---|
| Chain ID | 7290876100000 |
| Portal | https://url.retail.publishedprices.co.il |
| Portal type | Cerberus |
| Username | freshmarket |
| Password | (none) |
| Delta available | ✅ Yes |
| Notes | Federation of 7 sub-brands under one chain_id: Fresh Market, Machsanei Mazon, Machsanei Lahav, Hyper Dudu, Super Dush, Tip Tov, Chaviv. |

---

## Super Yuda — סופר יודה

| Field | Value |
|---|---|
| Chain ID | 7290058177776 |
| Portal | https://url.retail.publishedprices.co.il |
| Portal type | Cerberus |
| Username | yuda |
| Password | (none) |
| Delta available | ✅ Yes |
| Notes | — |

---

## Summary Table

| Chain | Chain ID | Portal type | Username | Delta |
|---|---|---|---|---|
| שופרסל Shufersal | 7290027600007 | Shufersal | — | ✅ |
| רמי לוי Rami Levy | 7290058140886 | Cerberus | RamiLevi | ✅ |
| אושר עד Osher Ad | 7290103152017 | Cerberus | osherad | ✅ |
| ויקטורי Victory | 7290696200003 | REST API | — | ⬜ |
| יוחננוף Yochananof | 7290803800003 | Cerberus | yohananof | ✅ |
| קשת Keshet | 7290785400000 | Cerberus | Keshet | ✅ |
| קרפור Carrefour | 7290055700007 | PublishPrice | — | ❌ |
| טיב טעם Tiv Taam | 7290873255550 | Cerberus | TivTaam | ❌ |
| קינג סטור King Store | 7290058108879 | Bina Projects | — | ⬜ |
| שפע ברכת השם Shefa | 7290058134977 | Bina Projects | — | ⬜ |
| שוק העיר Shuk Hayir | 7290058148776 | Bina Projects | — | ⬜ |
| פרש מרקט Fresh Market | 7290876100000 | Cerberus | freshmarket | ✅ |
| סופר יודה Super Yuda | 7290058177776 | Cerberus | yuda | ✅ |

Legend: ✅ = implemented and active · ❌ = explicitly excluded · ⬜ = not yet implemented
