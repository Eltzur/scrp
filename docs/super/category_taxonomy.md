# XXL product taxonomy — 20 top-level categories

Status: **draft for review.** Categories 1–11 were confirmed by Dude; 12–19 were filled in during SU11A-6 following the same pattern; 20 is Dude's deliberate catch-all. SU11A-7 resolved the overlaps the SU11A-6 pilot exposed (see "Resolved overlaps") and added rules for its recurring errors. Every placement note and overlap decision is a call Dude should confirm or change. This file is the classifier's whole instruction set: what it says is what the model is told.

| # | קטגוריה | תת-קטגוריות |
|---|---|---|
| 1 | פירות וירקות | טריים, קפואים (פירות בלבד — ראו להלן), מיובשים |
| 2 | מוצרי חלב וביצים | חלב, יוגורט, גבינות קשות, גבינות רכות, שמנת, חמאה ומרגרינה, ביצים |
| 3 | בשר, עוף ודגים | בקר, עוף, הודו, דגים, בשר טחון |
| 4 | לחם ומוצרי מאפה | לחם, פיתות, עוגות, מאפים מתוקים |
| 5 | סלטים, ממרחים ונקניקים | חומוס וטחינה, סלטים מוכנים, זיתים וחמוצים, נקניקים ובשר מעובד |
| 6 | מזון קפוא | גלידות וקינוחים קפואים, ירקות קפואים, מוכנים קפואים, בצק קפוא |
| 7 | שימורים ובישול | שימורי ירקות, שימורי דגים, רטבים לבישול |
| 8 | אורז, פסטה וקטניות | אורז, פסטה, קטניות יבשות |
| 9 | חטיפים ומתוקים | שוקולד, חטיפים מלוחים, עוגיות וממתקים |
| 10 | משקאות קלים | מים, מיצים, משקאות מוגזים |
| 11 | משקאות אלכוהוליים | יין, בירה, משקאות חריפים |
| 12 | קפה, תה ומשקאות חמים | קפה טחון ופולים, קפה נמס, קפסולות קפה, תה, חליטות צמחים, אבקות שוקו ומשקאות חמים, מלבינים ותחליפי קפה |
| 13 | תבלינים, רטבים ושמנים | תבלינים ועשבי תיבול יבשים, מלח ופלפל, שמנים, חומץ, קטשופ, מיונז וחרדל, רטבים ותיבול לסלט, קמח, סוכר ומוצרי אפייה |
| 14 | ניקיון | אבקות ונוזלי כביסה, מרככי כביסה, ניקוי כלים, ניקוי משטחים ורצפות, ניקוי אסלה, מטהרי אוויר, אביזרי ניקיון, הדברה |
| 15 | טיפוח אישי | טיפוח שיער, סבון ורחצה, דאודורנטים, טיפוח עור והגנה מהשמש, היגיינת הפה, גילוח והסרת שיער, היגיינה נשית, איפור ובשמים |
| 16 | מוצרי תינוקות | חיתולים, מגבונים לתינוק, תמ"ל, מזון תינוקות, טיפוח תינוקות, אביזרי האכלה |
| 17 | מזון לחיות מחמד | מזון לכלבים, מזון לחתולים, מזון רטוב, חטיפים לחיות, חול לחתולים, אביזרים לחיות |
| 18 | ויטמינים ותוספים | מולטי-ויטמינים, ויטמינים ומינרלים, אומגה 3, אבקות חלבון, צמחי מרפא, תוספי תזונה לספורט |
| 19 | כלי בית וחד פעמי | כלים חד פעמיים, נייר טואלט, מגבות נייר וממחטות, נייר אפייה, ניילון נצמד ואלומיניום, שקיות אשפה ואחסון, כלי מטבח ובישול, כלי הגשה |
| 20 | מיוחדים | מכשירי חשמל, סלולר, מוצרי רכב, עונתי/חגים |

**Category 20 rule:** only for items that genuinely do not fit 1–19 (non-grocery goods actually sold in these stores). It is NOT a bucket for items the classifier is unsure about.

## Resolved overlaps (SU11A-7 decisions — review)

Each was a source of disagreement in the SU11A-6 pilot. The rule is chosen so a shopper looking for the item would look there, and so the classifier can apply it from the product name alone.

| Overlap | Decision | Rule |
|---|---|---|
| Sauces: 7 vs 13 | **Split by use** | Sauces for cooking or marinating → **7**: pasta and pizza sauce, soy, teriyaki, curry, shakshuka base, cooking cream substitutes in jars. Table condiments and salad dressings → **13**: ketchup, mayonnaise, mustard, salad dressing, vinegar. |
| Cleaning accessories (cloths, sponges, mops, cleaning gloves): 14 vs 19 | **14** | 14 already lists "אביזרי ניקיון". 19 is kitchenware, disposables and paper goods — not cleaning tools. |
| Crackers, wafers, rusks, pretzels, grissini: 4 vs 9 | **9** | Dry packaged crackers, crispbreads, wafers, rusks, pretzels and breadsticks → 9. Category 4 keeps bread, pita, rolls, cakes, brownies, muffins and sweet pastries (croissant, rugelach). |
| Frozen pastry (burekas, frozen dough, frozen bread, frozen cakes): 4 vs 6 | **6** | Anything sold frozen in the bakery family → 6. Category 4 is fresh or shelf-stable only. |
| Ice-cream bars (שלגון, ארטיק, קרטיב, גלידה on a stick, frozen yogurt bars): 6 vs 9 | **6** | Any ice cream or ice lolly → 6, even when the name sounds like a snack or chocolate bar ("חטיף קראש" from an ice-cream maker). |
| Baby toiletries (baby shampoo, baby soap, baby lotion, nursing pads): 15 vs 16 | **16** | 16 already lists "טיפוח תינוקות". Any personal-care product labelled for babies → 16. |

## Placement notes

From SU11A-6, plus the SU11A-7 rules for recurring pilot errors (marked ★).

- ★ **Pickles (מלפפונים חמוצים / במלח / כבושים), pickled vegetables → 5,** with olives. Not 7, even when canned or jarred.
- ★ **Toilet-soap blocks and toilet gels (סבון אסלה, סנובון, דאק) → 14.** Not 15 — "סבון" here is a toilet cleaner.
- ★ **Cookies, biscuits, wafers → 9.** See the crackers row above.
- ★ **Frozen fruit → 1;** frozen vegetables → 6. Categories 1 ("קפואים") and 6 ("ירקות קפואים") overlapped as confirmed; this resolves it.
- ★ **Pet treats and chews → 17.** Not 9.
- ★ **Milk drinks (שוקו, משקה חלב, יוגורט לשתייה), puddings and dairy desserts → 2.** Plant-based milks and dairy substitutes → 2. Not 10.
- **Raw meat, poultry and fish, fresh or frozen → 3.** Frozen *prepared* products (schnitzel, nuggets, burgers, burekas, frozen meals) → 6.
- **Sliced deli meat (pastrami, turkey breast), sausages, hot dogs, pâté → 5.**
- **Canned fish (tuna, sardines) and canned fruit → 7.** Ready soups and soup powders, stock → 7.
- **Breakfast cereals and granola → 8.** Cereal bars → 9.
- **Nuts, seeds and פיצוחים → 9.** Dried fruit → 1.
- **Sweet spreads (honey, jam, chocolate spread, silan) → 5.** Halva → 9.
- **Flour, cornflour, sugar, sweeteners (סוכרזית), baking powder, baking mixes → 13.**
- **Margarine and butter → 2.** Cooking oils → 13.
- **Toilet paper, paper towels, tissues, refuse bags → 19.**
- **Pest control (insecticides, traps, repellents) → 14.**
- **Baby wipes → 16;** other wet wipes → 15.
- **Iced / ready-to-drink coffee and tea → 10.**
