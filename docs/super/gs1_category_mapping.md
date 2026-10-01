# GS1 category → XXL taxonomy mapping (SU11A-6)

Status: **draft for review.** Each of the 501 distinct `gs1.products.group_name` values (GS1 GPC "brick" categories) mapped to ONE top-level category of [category_taxonomy.md](category_taxonomy.md), or **EXCLUDED** where the GS1 category is ambiguous or spans buckets. The SU11A-6 pilot used the non-excluded rows as ground truth for blind LLM classification; correcting a row here changes the ground truth, not the model.

- 501 GS1 categories; **120 EXCLUDED** (2,714 items), 381 mapped.
- Items = catalog items (`items.item_code`) matched to that GS1 category via `gtin` (latest GS1 row per GTIN). 19,644 matched in total; 16,930 remain as ground truth.
- 35 values arrive from GS1 already in Hebrew; their English column shows the Hebrew original.
- Main exclusion reasons: *Prepared/Processed* meat and fish (deli vs frozen-prepared vs raw), dips/dressings and condiment variety packs (5 vs 13), pulses that may be canned or dry (7 vs 8), mixed-bakery and mixed-sweets variety packs, shelf-stable processed fruit (canned 7 vs dried 1), and powered personal-care devices (15 vs 20).

| GS1 group_name | עברית | קטגוריה | פריטים | EXCLUDED |
|---|---|---|---:|:---:|
| Chocolate and Chocolate_Sugar Candy Combinations - Confectionery | שוקולד וממתקי שוקולד | 9. חטיפים ומתוקים | 1,125 | N |
| Cleaning Accessories | אביזרי ניקיון | 14. ניקיון | 451 | N |
| Drinks Flavoured - Ready to Drink | משקאות בטעמים, מוכנים לשתייה | 10. משקאות קלים | 444 | N |
| Cleansing_Washing_Soap - Body | סבון ותכשירי רחצה לגוף | 15. טיפוח אישי | 416 | N |
| Biscuits_Cookies (Shelf Stable) | ביסקוויטים ועוגיות (מדף) | 9. חטיפים ומתוקים | 389 | N |
| Hair - Shampoo | שמפו | 15. טיפוח אישי | 377 | N |
| Cheese_Cheese Substitutes (Shelf Stable) | גבינות ותחליפי גבינה (מדף) | 2. מוצרי חלב וביצים | 333 | N |
| Laundry Detergents | אבקות ונוזלי כביסה | 14. ניקיון | 327 | N |
| Dairy By-Products | מוצרי חלב נלווים (משקאות חלב, מעדנים) | 2. מוצרי חלב וביצים | 317 | N |
| Sugar Candy_Sugar Candy Substitutes Confectionery | סוכריות וממתקי סוכר | 9. חטיפים ומתוקים | 302 | N |
| Fish - Prepared_Processed (Shelf Stable) | דגים מעובדים (מדף, בעיקר שימורים) | 7. שימורים ובישול | 295 | N |
| Antiperspirants_Deodorants | דאודורנטים | 15. טיפוח אישי | 279 | N |
| Cereal_Muesli Bars | חטיפי דגנים ומוזלי | 9. חטיפים ומתוקים | 278 | N |
| Pasta_Noodles - Not Ready to Eat (Shelf Stable) | פסטה ואטריות יבשות | 8. אורז, פסטה וקטניות | 278 | N |
| Cheese_Cheese Substitutes (Perishable) | גבינות ותחליפי גבינה (קירור) | 2. מוצרי חלב וביצים | 271 | N |
| Denture_Orthodontic - Cleansing | ניקוי תותבות ויישור שיניים | 15. טיפוח אישי | 261 | N |
| Coffee - Beans_Ground | קפה פולים וטחון | 12. קפה, תה ומשקאות חמים | 259 | N |
| Dressings_Dips (Shelf Stable) | רטבים לסלט ומטבלים (מדף) | — | 245 | Y |
| Fruit Juice - Ready to Drink (Shelf Stable) | מיץ פירות מוכן לשתייה (מדף) | 10. משקאות קלים | 231 | N |
| Hair - Conditioner_Treatment | מרכך ומסכה לשיער | 15. טיפוח אישי | 230 | N |
| Wine - Still | יין | 11. משקאות אלכוהוליים | 230 | N |
| Hair - Colour | צבע לשיער | 15. טיפוח אישי | 229 | N |
| Sauces_Spreads_Dips_Condiments Variety Packs | רטבים, ממרחים ומטבלים — מגוון | — | 228 | Y |
| Cookware (Disposable) | כלי בישול ואפייה חד פעמיים | 19. כלי בית וחד פעמי | 223 | N |
| Skin Care_Moisturising Products | טיפוח עור וקרמי לחות | 15. טיפוח אישי | 219 | N |
| Yogurt_Yogurt Substitutes (Shelf Stable) | יוגורט ותחליפי יוגורט (מדף) | 2. מוצרי חלב וביצים | 218 | N |
| Ice Cream_Ice Novelties (Frozen) | גלידות וארטיקים | 6. מזון קפוא | 213 | N |
| Cereal_Grain_Pulse Products Variety Packs | מוצרי דגנים וקטניות — מגוון | — | 211 | Y |
| Yogurt_Yogurt Substitutes (Perishable) | יוגורט ותחליפי יוגורט (קירור) | 2. מוצרי חלב וביצים | 209 | N |
| Bread (Shelf Stable) | לחם (מדף) | 4. לחם ומוצרי מאפה | 201 | N |
| Chips_Crisps_Snack Mixes - Natural_Extruded (Shelf Stable) | צ'יפס וחטיפים מלוחים | 9. חטיפים ומתוקים | 196 | N |
| Tea - Bags_Loose | תה בשקיות ותפזורת | 12. קפה, תה ומשקאות חמים | 189 | N |
| Dental Cleansing | משחת שיניים | 15. טיפוח אישי | 187 | N |
| Nuts_Seeds - Prepared_Processed (Shelf Stable) | אגוזים וגרעינים קלויים (פיצוחים) | 9. חטיפים ומתוקים | 182 | N |
| Beer | בירה | 11. משקאות אלכוהוליים | 179 | N |
| Beef - Prepared_Processed | בקר מעובד (נקניק, המבורגר, קבב...) | — | 171 | Y |
| Snacks Variety Packs | חטיפים — מארזי מגוון | 9. חטיפים ומתוקים | 170 | N |
| Nuts_Seeds - Unprepared_Unprocessed (Shelf Stable) | אגוזים וזרעים לא קלויים | 9. חטיפים ומתוקים | 152 | N |
| Flour - Cereal_Pulse (Shelf Stable) | קמח | 13. תבלינים, רטבים ושמנים | 140 | N |
| Herbs_Spices (Shelf Stable) | תבלינים ועשבי תיבול יבשים | 13. תבלינים, רטבים ושמנים | 134 | N |
| Chewing Gum | מסטיק | 9. חטיפים ומתוקים | 129 | N |
| Feminine Hygiene - Panty Liners | מגני תחתונים | 15. טיפוח אישי | 124 | N |
| Fruit - Unprepared_Unprocessed (Frozen) | פירות קפואים | 1. פירות וירקות | 122 | N |
| Jams_Marmalades (Shelf Stable) | ריבות | 5. סלטים, ממרחים ונקניקים | 121 | N |
| Beef Sausages - Prepared_Processed | נקניקיות ונקניק בקר | 5. סלטים, ממרחים ונקניקים | 119 | N |
| Oils Edible - Vegetable or Plant (Shelf Stable) | שמנים צמחיים למאכל | 13. תבלינים, רטבים ושמנים | 116 | N |
| Sun Protection Products | תכשירי הגנה מהשמש | 15. טיפוח אישי | 115 | N |
| Toilet Cleaning Products | ניקוי אסלה | 14. ניקיון | 115 | N |
| Baking_Cooking Mixes (Shelf Stable) | תערובות אפייה ובישול (מדף) | 13. תבלינים, רטבים ושמנים | 113 | N |
| Grains_Cereal - Not Ready to Eat - (Shelf Stable) | דגנים לבישול (אורז, בורגול, קוסקוס) | 8. אורז, פסטה וקטניות | 110 | N |
| Pies_Pastries - Sweet (Shelf Stable) | מאפים מתוקים (מדף) | 4. לחם ומוצרי מאפה | 107 | N |
| Turkey - Prepared_Processed | הודו מעובד (פרוס, שניצל...) | — | 104 | Y |
| Chutneys_Relishes (Shelf Stable) | צ'אטני ורטבים חריפים (מדף) | — | 103 | Y |
| Vegetables - Prepared_Processed (Frozen) | ירקות מעובדים קפואים | 6. מזון קפוא | 98 | N |
| Milk_Milk Substitutes (Shelf Stable) | חלב ותחליפי חלב (מדף) | 2. מוצרי חלב וביצים | 95 | N |
| Sugar_Sugar Substitutes (Shelf Stable) | סוכר ותחליפי סוכר | 13. תבלינים, רטבים ושמנים | 95 | N |
| Cheese_Cheese Substitutes (Frozen) | גבינות (מסומן כקפוא) | 2. מוצרי חלב וביצים | 91 | N |
| Packaged Water | מים ארוזים | 10. משקאות קלים | 89 | N |
| Vegetables - Prepared_Processed (Shelf Stable) | ירקות מעובדים (מדף, בעיקר שימורים) | 7. שימורים ובישול | 88 | N |
| Bread (Perishable) | לחם טרי | 4. לחם ומוצרי מאפה | 85 | N |
| Confectionery Products Variety Packs | ממתקים — מארזי מגוון | 9. חטיפים ומתוקים | 85 | N |
| Dough Based Products _ Meals - Not Ready to Eat - Savoury (Frozen) | מאפים מלוחים קפואים (בורקס, בצק) | 6. מזון קפוא | 85 | N |
| Fruit - Prepared_Processed (Shelf Stable) | פירות מעובדים (מדף — שימורים או מיובשים) | — | 85 | Y |
| Dish Care_Protection | טיפול והגנה לכלים | 14. ניקיון | 84 | N |
| Bread_Bakery Products Variety Packs | לחם ומאפים — מגוון | — | 82 | Y |
| Seasonings_Preservatives_Extracts Variety Packs | תיבול ותמציות — מגוון | 13. תבלינים, רטבים ושמנים | 81 | N |
| Vegetable Based Products _ Meals - Ready to Eat (Perishable) | סלטי ירקות מוכנים (קירור) | 5. סלטים, ממרחים ונקניקים | 80 | N |
| Stimulants_Energy Drinks - Ready to Drink | משקאות אנרגיה | 10. משקאות קלים | 77 | N |
| Vegetables - Unprepared_Unprocessed (Frozen) | ירקות קפואים | 6. מזון קפוא | 77 | N |
| Cakes - Sweet (Shelf Stable) | עוגות (מדף) | 4. לחם ומוצרי מאפה | 76 | N |
| Pickles_Relishes_Chutneys_Olives Variety Packs | חמוצים וזיתים — מגוון | 5. סלטים, ממרחים ונקניקים | 75 | N |
| Baby Diapers (Disposable) | חיתולים חד פעמיים | 16. מוצרי תינוקות | 74 | N |
| Salt Sticks _ Mini Pretzels | בייגלה ומקלות מלוחים | 9. חטיפים ומתוקים | 73 | N |
| Sauces - Cooking (Shelf Stable) | רטבים לבישול (מדף) | 7. שימורים ובישול | 71 | N |
| Tomatoes Variety Packs | עגבניות — מגוון | — | 71 | Y |
| Cereals Products - Ready to Eat (Shelf Stable) | דגני בוקר | 8. אורז, פסטה וקטניות | 67 | N |
| Olives (Shelf Stable) | זיתים | 5. סלטים, ממרחים ונקניקים | 66 | N |
| Sweet Spreads Variety Packs | ממרחים מתוקים — מגוון | 5. סלטים, ממרחים ונקניקים | 66 | N |
| Alcoholic Beverages Variety Packs | משקאות אלכוהוליים — מגוון | 11. משקאות אלכוהוליים | 65 | N |
| Hair Care Products Other | מוצרי שיער אחרים | 15. טיפוח אישי | 65 | N |
| Pate (Perishable) | פטה ומעדני כבד (קירור) | 5. סלטים, ממרחים ונקניקים | 65 | N |
| Fruit - Unprepared_Unprocessed (Shelf Stable) | פירות לא מעובדים (מדף, בעיקר מיובשים) | 1. פירות וירקות | 64 | N |
| Coffee - Instant | קפה נמס | 12. קפה, תה ומשקאות חמים | 63 | N |
| Milk_Butter_Cream_Yogurts_Cheese_Eggs_Substitutes Variety Packs | מוצרי חלב וביצים — מגוון | 2. מוצרי חלב וביצים | 63 | N |
| Hair - Styling (Non Powered) | עיצוב שיער | 15. טיפוח אישי | 62 | N |
| Vegetables - Unprepared_Unprocessed (Shelf Stable) | ירקות לא מעובדים (מדף) | — | 62 | Y |
| Meat Substitutes (Frozen) | תחליפי בשר קפואים | 6. מזון קפוא | 60 | N |
| Pasta_Noodles - Ready to Eat (Shelf Stable) | פסטה ואטריות מוכנות (מדף, אטריות אינסטנט) | 8. אורז, פסטה וקטניות | 60 | N |
| Cleaning Aids | עזרי ניקיון | 14. ניקיון | 59 | N |
| Baby Diapers_Accessories Other | אביזרי חיתול אחרים | 16. מוצרי תינוקות | 58 | N |
| Fresheners_Deodorisers Other | מטהרי אוויר וריח אחרים | 14. ניקיון | 57 | N |
| Fats Edible - Vegetable_Plant (Shelf Stable) | שומנים צמחיים (מרגרינה, שומן לאפייה) | — | 56 | Y |
| Sweetcorn | תירס | — | 56 | Y |
| Sweet Bakery Products Variety Packs | מאפים מתוקים — מגוון | — | 55 | Y |
| Shaving - Razors - Non Disposable (Non Powered) | סכיני גילוח רב-פעמיים | 15. טיפוח אישי | 54 | N |
| Wipes - Personal | מגבונים לחים אישיים | — | 52 | Y |
| Electronic Organisers | ארגוניות אלקטרוניות (סיווג לא ברור) | — | 51 | Y |
| Milk_Milk Substitutes (Perishable) | חלב ותחליפי חלב (קירור) | 2. מוצרי חלב וביצים | 51 | N |
| Pasta_Noodles - Not Ready to Eat (Perishable) | פסטה טרייה | 8. אורז, פסטה וקטניות | 51 | N |
| Confectionery Based Spreads (Shelf Stable) | ממרחים מתוקים (שוקולד וכד') | 5. סלטים, ממרחים ונקניקים | 50 | N |
| Insecticides_Pesticides_Rodenticides | חומרי הדברה | 14. ניקיון | 50 | N |
| Wine - Sparkling | יין מבעבע | 11. משקאות אלכוהוליים | 49 | N |
| Fruit_Nuts_Seeds Mixes - Prepared_Processed (Shelf Stable) | תערובות פירות יבשים ואגוזים | 9. חטיפים ומתוקים | 47 | N |
| Pies_Pastries_Pizzas_Quiches - Savoury (Frozen) | פשטידות, פיצות ומאפים מלוחים קפואים | 6. מזון קפוא | 47 | N |
| Honey (Shelf Stable) | דבש | 5. סלטים, ממרחים ונקניקים | 46 | N |
| Shaving - Razors - Disposable (Non Powered) | סכיני גילוח חד פעמיים | 15. טיפוח אישי | 46 | N |
| Body Washing Other | רחצת גוף — אחר | 15. טיפוח אישי | 45 | N |
| Chicken - Prepared_Processed | עוף מעובד (שניצל, נאגטס...) | — | 44 | Y |
| Confectionery_Sugar Sweetening Products Variety Packs | ממתקים וממתיקים — מגוון | — | 44 | Y |
| Dried Breads (Shelf Stable) | לחם יבש, קרקרים ופריכיות | — | 44 | Y |
| Feminine Hygiene - Accessories | אביזרי היגיינה נשית | 15. טיפוח אישי | 44 | N |
| Lentils | עדשים | 8. אורז, פסטה וקטניות | 44 | N |
| Cereal Products - Ready to Eat (Perishable) | מוצרי דגנים מוכנים (קירור) | — | 43 | Y |
| Yogurt_Yogurt Substitutes (Frozen) | יוגורט (מסומן כקפוא) | — | 43 | Y |
| Fruit Juice Drinks - Ready to Drink (Shelf Stable) | משקאות פירות מוכנים (מדף) | 10. משקאות קלים | 42 | N |
| Pet Care_Food Variety Packs | מזון וטיפוח לחיות — מגוון | 17. מזון לחיות מחמד | 42 | N |
| Biscuits_Cookies Variety Packs | ביסקוויטים ועוגיות — מגוון | 9. חטיפים ומתוקים | 41 | N |
| Spirits | משקאות חריפים | 11. משקאות אלכוהוליים | 40 | N |
| Air Fresheners_Deodorisers (Non Powered) | מטהרי אוויר (לא חשמליים) | 14. ניקיון | 37 | N |
| Biscuits_Cookies (Perishable) | ביסקוויטים ועוגיות (טריים) | 9. חטיפים ומתוקים | 37 | N |
| Meat Substitutes (Shelf Stable) | תחליפי בשר (מדף) | — | 37 | Y |
| Butter_Butter Substitutes (Shelf Stable) | חמאה ותחליפי חמאה (מדף) | 2. מוצרי חלב וביצים | 36 | N |
| Dairy_Dairy Substitute Based Drinks - Ready to Drink (Perishable) | משקאות חלב ותחליפי חלב (קירור) | 2. מוצרי חלב וביצים | 36 | N |
| Fish - Prepared_Processed (Frozen) | דגים מעובדים קפואים | — | 36 | Y |
| Feminine Hygiene - Tampons | טמפונים | 15. טיפוח אישי | 35 | N |
| Toilet Paper | נייר טואלט | 19. כלי בית וחד פעמי | 35 | N |
| Beef - Unprepared_Unprocessed | בקר טרי לא מעובד | 3. בשר, עוף ודגים | 34 | N |
| Desserts (Shelf Stable) | קינוחים (מדף) | — | 34 | Y |
| Fruit_Nuts_Seeds Combination Variety Packs | פירות יבשים ואגוזים — מגוון | 9. חטיפים ומתוקים | 34 | N |
| Grain Based Products _ Meals - Not Ready to Eat - Savoury (Shelf Stable) | מנות על בסיס דגנים להכנה (מדף) | — | 34 | Y |
| Dish Cleaning_Care - Hand | נוזל כלים | 14. ניקיון | 33 | N |
| Refuse Bags | שקיות אשפה | 19. כלי בית וחד פעמי | 33 | N |
| Chickpeas | חומוס (גרגרים) | — | 32 | Y |
| Grains_Cereal - Ready to Eat - (Shelf Stable) | דגנים מוכנים לאכילה (מדף) | — | 32 | Y |
| Laundry Other | כביסה — אחר | 14. ניקיון | 32 | N |
| Nuts_Seeds - Unprepared_Unprocessed (Perishable) | אגוזים וזרעים לא קלויים (קירור) | 9. חטיפים ומתוקים | 32 | N |
| Fabric Softeners_Conditioners | מרככי כביסה | 14. ניקיון | 31 | N |
| Fish - Unprepared_Unprocessed (Frozen) | דגים קפואים לא מעובדים | 3. בשר, עוף ודגים | 31 | N |
| Surface Cleaners | ניקוי משטחים | 14. ניקיון | 31 | N |
| Pasta_Noodles - Ready to Eat (Perishable) | פסטה מוכנה (קירור) | — | 30 | Y |
| Disposable Tableware | כלי אוכל חד פעמיים | 19. כלי בית וחד פעמי | 29 | N |
| Mayonnaise_Mayonnaise Substitutes (Shelf Stable) | מיונז | 13. תבלינים, רטבים ושמנים | 29 | N |
| Pickled Vegetables | ירקות כבושים | 5. סלטים, ממרחים ונקניקים | 29 | N |
| Body Washing Variety Packs | רחצת גוף — מגוון | 15. טיפוח אישי | 28 | N |
| Cakes - Sweet (Frozen) | עוגות קפואות | — | 28 | Y |
| Extracts_Salt_Meat Tenderisers (Shelf Stable) | תמציות, מלח ומרככי בשר | 13. תבלינים, רטבים ושמנים | 28 | N |
| Butter_Butter Substitutes (Perishable) | חמאה ותחליפי חמאה (קירור) | 2. מוצרי חלב וביצים | 27 | N |
| Chicken Sausages - Prepared_Processed | נקניקיות ונקניק עוף | 5. סלטים, ממרחים ונקניקים | 27 | N |
| Fruit Herbal Infusions - Bags_Loose | חליטות פירות וצמחים | 12. קפה, תה ומשקאות חמים | 27 | N |
| Gherkins | מלפפונים חמוצים | 5. סלטים, ממרחים ונקניקים | 27 | N |
| Popcorn (Shelf Stable) | פופקורן | 9. חטיפים ומתוקים | 27 | N |
| Chocolate_Cocoa_Malt - Ready to Drink | משקאות שוקו מוכנים | 2. מוצרי חלב וביצים | 26 | N |
| Cleaning Variety Packs | ניקיון — מגוון | 14. ניקיון | 25 | N |
| Fish - Prepared_Processed (Perishable) | דגים מעובדים (קירור — מעושן, כבוש) | — | 25 | Y |
| Pies_Pastries_Pizzas_Quiches - Savoury (Shelf Stable) | מאפים מלוחים (מדף) | — | 25 | Y |
| Chocolate_Cocoa_Malt - Not Ready to Drink | אבקות שוקו | 12. קפה, תה ומשקאות חמים | 24 | N |
| Depilation_Epilation (Non Powered) | הסרת שיער (שעווה, קרם) | 15. טיפוח אישי | 24 | N |
| Dressings_Dips (Perishable) | מטבלים וסלטים (קירור) | 5. סלטים, ממרחים ונקניקים | 24 | N |
| Gloves | כפפות | 14. ניקיון | 24 | N |
| Hair Removal_Shaving - Accessories | אביזרי גילוח והסרת שיער | 15. טיפוח אישי | 24 | N |
| Oyster Mushrooms | פטריות יער (אויסטר) | 1. פירות וירקות | 24 | N |
| Wild Mushrooms (Other) | פטריות בר אחרות | 1. פירות וירקות | 24 | N |
| Dairy_Dairy Substitute Based Drinks - Ready to Drink (Shelf Stable) | משקאות חלב ותחליפי חלב (מדף) | 2. מוצרי חלב וביצים | 23 | N |
| Facial Tissue_Handkerchiefs (Disposable) | ממחטות נייר | 19. כלי בית וחד פעמי | 23 | N |
| Shaving Preparations | תכשירי גילוח | 15. טיפוח אישי | 22 | N |
| Food_Beverage_Tobacco Variety Packs | מזון, משקה וטבק — מגוון | — | 21 | Y |
| Laundry Colour Care | כביסה לצבעוניים | 14. ניקיון | 21 | N |
| Mustard (Shelf Stable) | חרדל | 13. תבלינים, רטבים ושמנים | 21 | N |
| Oral Care - Aids (Non Powered) | עזרי היגיינת פה (לא חשמליים) | 15. טיפוח אישי | 21 | N |
| Oral Care Centre - Brush_Cleanser_Storage (Powered) | מברשות שיניים חשמליות | — | 21 | Y |
| Paper Towels | מגבות נייר | 19. כלי בית וחד פעמי | 21 | N |
| Ready-Made Combination Meals - Ready to Eat Variety Packs | ארוחות מוכנות — מגוון | — | 21 | Y |
| Vegetables - Prepared_Processed (Perishable) | ירקות מעובדים (קירור) | — | 21 | Y |
| Beverages Variety Packs | משקאות — מגוון | — | 20 | Y |
| Cream_Cream Substitutes (Shelf Stable) | שמנת ותחליפי שמנת (מדף) | 2. מוצרי חלב וביצים | 20 | N |
| Turkey Sausages - Prepared_Processed | נקניקיות ונקניק הודו | 5. סלטים, ממרחים ונקניקים | 20 | N |
| Soups - Prepared (Shelf Stable) | מרקים מוכנים ואבקות מרק | 7. שימורים ובישול | 19 | N |
| Vegetable Based Products _ Meals - Not Ready to Eat (Frozen) | מנות ירקות קפואות להכנה | 6. מזון קפוא | 19 | N |
| Cream_Cream Substitutes (Perishable) | שמנת ותחליפי שמנת (קירור) | 2. מוצרי חלב וביצים | 18 | N |
| Disposable Food Bags | שקיות מזון חד פעמיות | 19. כלי בית וחד פעמי | 18 | N |
| Dough Based Products _ Meals Variety Packs | מאפים — מגוון | — | 18 | Y |
| Drinks Flavoured - Not Ready to Drink | תרכיזי משקה בטעמים | 10. משקאות קלים | 18 | N |
| Lima Beans | שעועית לימה | — | 18 | Y |
| Adult Incontinence - Underwear (Disposable) | תחתוני ספיגה למבוגרים | 15. טיפוח אישי | 17 | N |
| Baby_Infant - Foods_Beverages Variety Packs | מזון ומשקאות לתינוקות — מגוון | 16. מוצרי תינוקות | 17 | N |
| Baking_Cooking Mixes (Perishable) | תערובות אפייה (קירור) | — | 17 | Y |
| Cleansing_Washing Accessories - Personal | אביזרי רחצה אישיים | 15. טיפוח אישי | 17 | N |
| Cookware_Bakeware Accessories_Replacement Parts | אביזרי בישול ואפייה | 19. כלי בית וחד פעמי | 17 | N |
| Desserts_Dessert Toppings Variety Packs | קינוחים ותוספות — מגוון | — | 17 | Y |
| Disposable Food Wrap | ניילון נצמד ונייר עטיפה | 19. כלי בית וחד פעמי | 17 | N |
| Grain Based Products _ Meals - Ready to Eat - Savoury (Shelf Stable) | מנות דגנים מוכנות (מדף) | — | 17 | Y |
| Pepper Variety Packs | פלפלים (ירק) — מגוון | — | 17 | Y |
| Ready-Made Combination Meals - Ready to Eat (Shelf Stable) | ארוחות מוכנות (מדף, שימורים) | 7. שימורים ובישול | 17 | N |
| Sweeties | ממתקים | 9. חטיפים ומתוקים | 17 | N |
| Apples | תפוחים | 1. פירות וירקות | 16 | N |
| Bread (Frozen) | לחם קפוא | — | 16 | Y |
| Prepared_Preserved Foods Variety Packs | מזון משומר — מגוון | — | 16 | Y |
| Syrup_Treacle_Molasses (Shelf Stable) | סירופים ודבש תמרים | — | 16 | Y |
| Disposable Food Containers | קופסאות מזון חד פעמיות | 19. כלי בית וחד פעמי | 15 | N |
| Dough Based Products _ Meals - Ready to Eat - Savoury (Shelf Stable) | מאפים מלוחים מוכנים (מדף) | — | 15 | Y |
| Liqueurs | ליקרים | 11. משקאות אלכוהוליים | 15 | N |
| Oils_Fats Edible Variety Packs | שמנים ושומנים — מגוון | — | 15 | Y |
| Beans (Winged) | שעועית (כנפית) | — | 14 | Y |
| Cleaners Other | חומרי ניקוי אחרים | 14. ניקיון | 14 | N |
| Ear_Nasal Care | טיפוח אוזניים ואף | 15. טיפוח אישי | 14 | N |
| Peas | אפונה | — | 14 | Y |
| Ready-Made Combination Meals - Not Ready to Eat (Shelf Stable) | ארוחות להכנה (מדף) | — | 14 | Y |
| Sauces - Cooking (Perishable) | רטבים לבישול (קירור) | 7. שימורים ובישול | 14 | N |
| Vegetable Based Products _ Meals - Not Ready to Eat (Perishable) | מנות ירקות להכנה (קירור) | — | 14 | Y |
| Vinegars | חומץ | 13. תבלינים, רטבים ושמנים | 14 | N |
| Beauty_Personal Care_Hygiene Variety Packs | טיפוח והיגיינה — מגוון | 15. טיפוח אישי | 13 | N |
| Chicken - Unprepared_Unprocessed | עוף טרי לא מעובד | 3. בשר, עוף ודגים | 13 | N |
| Cookware_Bakeware Other | כלי בישול ואפייה אחרים | 19. כלי בית וחד פעמי | 13 | N |
| Soup Additions (Shelf Stable) | תוספות למרק (שקדי מרק, קרוטונים) | 7. שימורים ובישול | 13 | N |
| Stain Removers | מסירי כתמים | 14. ניקיון | 13 | N |
| Tomato Ketchup_Ketchup Substitutes (Shelf Stable) | קטשופ | 13. תבלינים, רטבים ושמנים | 13 | N |
| Vegetable Based Products _ Meals - Ready to Eat (Shelf Stable) | סלטי ירקות מוכנים (מדף) | — | 13 | Y |
| Fish - Unprepared_Unprocessed (Shelf Stable) | דגים לא מעובדים (מדף) | — | 12 | Y |
| Fruit - Prepared_Processed (Frozen) | פירות מעובדים קפואים | 1. פירות וירקות | 12 | N |
| Grains_Flour Variety Packs | דגנים וקמח — מגוון | — | 12 | Y |
| Palm Hearts | לבבות דקל | — | 12 | Y |
| Air Fresheners_Deodorisers (Powered) | מטהרי אוויר חשמליים | 14. ניקיון | 11 | N |
| Baking_Cooking Mixes (Frozen) | תערובות אפייה קפואות | — | 11 | Y |
| Dates | תמרים | 1. פירות וירקות | 11 | N |
| Food Preparation Equipment Other | כלי הכנת מזון אחרים | 19. כלי בית וחד פעמי | 11 | N |
| Fruit - Prepared_Processed (Perishable) | פירות חתוכים טריים | 1. פירות וירקות | 11 | N |
| Salt_Pepper Shakers | מלחיות ופלפליות | 19. כלי בית וחד פעמי | 11 | N |
| After Shave Care | טיפוח אחרי גילוח | 15. טיפוח אישי | 10 | N |
| Alcoholic Cordials_Syrups | סירופים אלכוהוליים | 11. משקאות אלכוהוליים | 10 | N |
| Cake_Pastry Decorations_Accessories (Non Edible) | קישוטי עוגות (לא אכילים) | 19. כלי בית וחד פעמי | 10 | N |
| Eggs Products_Substitutes | מוצרי ביצים ותחליפים | 2. מוצרי חלב וביצים | 10 | N |
| Coffee - Ready to Drink | קפה מוכן לשתייה | 10. משקאות קלים | 9 | N |
| Desserts (Frozen) | קינוחים קפואים | 6. מזון קפוא | 9 | N |
| Dough Based Products _ Meals - Ready to Eat - Savoury (Perishable) | מאפים מלוחים מוכנים (קירור) | — | 9 | Y |
| Grains_Cereal - Not Ready to Eat - (Perishable) | דגנים לבישול (קירור) | — | 9 | Y |
| Milk_Milk Substitutes (Frozen) | חלב (מסומן כקפוא) | 2. מוצרי חלב וביצים | 9 | N |
| Pet Food Shelf Stable | מזון לחיות מחמד (מדף) | 17. מזון לחיות מחמד | 9 | N |
| Fruits_Vegetables_Nuts_Seeds Variety Packs | פירות, ירקות ואגוזים — מגוון | — | 8 | Y |
| Insect_Pest Control - Barriers_Traps | מלכודות מזיקים | 14. ניקיון | 8 | N |
| Other Sauces Dipping_Condiments_Savoury Toppings_Savoury Spreads_Marinades (Perishable) | רטבים, מטבלים ומרינדות (קירור) | — | 8 | Y |
| Seedlings - Ready to Eat | נבטים | 1. פירות וירקות | 8 | N |
| Skin Care Other | טיפוח עור — אחר | 15. טיפוח אישי | 8 | N |
| פסטה/אטריות – לא מוכן לאכילה (אחסון מדף) | פסטה ואטריות יבשות | 8. אורז, פסטה וקטניות | 8 | N |
| תחליפי גבינה/גבינה (מתכלה) | גבינות ותחליפי גבינה (קירור) | 2. מוצרי חלב וביצים | 8 | N |
| Apple_Pear Alcoholic Beverage - Still | סיידר (לא מוגז) | 11. משקאות אלכוהוליים | 7 | N |
| Aubergines | חצילים | 1. פירות וירקות | 7 | N |
| Baby Diapers Accessories | אביזרי חיתולים | 16. מוצרי תינוקות | 7 | N |
| Dough Based Products _ Meals - Not Ready to Eat - Savoury (Shelf Stable) | מוצרי בצק מלוחים להכנה (מדף) | — | 7 | Y |
| Drain Treatments_Pipe Unblockers | פותחי סתימות | 14. ניקיון | 7 | N |
| Grain Based Products _ Meals - Not Ready to Eat - Savoury (Perishable) | מנות דגנים להכנה (קירור) | — | 7 | Y |
| Lamb_Mutton Sausages - Prepared_Processed | נקניקיות ונקניק כבש | 5. סלטים, ממרחים ונקניקים | 7 | N |
| Nuts_Seeds - Prepared_Processed (Perishable) | אגוזים וגרעינים קלויים (קירור) | 9. חטיפים ומתוקים | 7 | N |
| Pomegranates | רימונים | 1. פירות וירקות | 7 | N |
| Ready-Made Combination Meals - Not Ready to Eat (Frozen) | ארוחות קפואות להכנה | 6. מזון קפוא | 7 | N |
| Tablemats – Non Fabric_Non Textile | פליסמטים | 19. כלי בית וחד פעמי | 7 | N |
| Aquatic Invertebrates_Fish_Shellfish_Seafood Mixes - Prepared_Processed (Shelf Stable) | פירות ים מעובדים (מדף, שימורים) | 7. שימורים ובישול | 6 | N |
| Aquatic Plants Prepared_Processed (Shelf Stable) | אצות מעובדות | — | 6 | Y |
| Baby Hygiene Products | היגיינת תינוקות | 16. מוצרי תינוקות | 6 | N |
| Broad Beans | פול | — | 6 | Y |
| Cotton Wool Products | צמר גפן | 15. טיפוח אישי | 6 | N |
| Dish Cleaning_Care - Automatic | ניקוי למדיח כלים | 14. ניקיון | 6 | N |
| Lemons | לימונים | 1. פירות וירקות | 6 | N |
| Mixed Species Sausages - Prepared_Processed | נקניקיות מעורבות | 5. סלטים, ממרחים ונקניקים | 6 | N |
| Olives (Perishable) | זיתים (קירור) | 5. סלטים, ממרחים ונקניקים | 6 | N |
| Pasta_Noodles - Not Ready to Eat (Frozen) | פסטה קפואה | — | 6 | Y |
| Sugars_Sugar Substitute Products Variety Packs | סוכר ותחליפים — מגוון | 13. תבלינים, רטבים ושמנים | 6 | N |
| מוצרים/ארוחות על בסיס בצק – לא מוכן לאכילה – מתובלים (קפוא) | מאפים מלוחים קפואים (בורקס, בצק) | 6. מזון קפוא | 6 | N |
| Aquatic Invertebrates - Unprepared_Unprocessed (Frozen) | פירות ים קפואים | 3. בשר, עוף ודגים | 5 | N |
| Baby_Infant - Specialised Foods (Shelf Stable) | מזון תינוקות ייעודי | 16. מוצרי תינוקות | 5 | N |
| Breath Fresheners_Mouth Rinses | מי פה ומרעננים | 15. טיפוח אישי | 5 | N |
| Butter_Butter Substitutes (Frozen) | חמאה (קפואה) | 2. מוצרי חלב וביצים | 5 | N |
| Cleansers_Cosmetics Removers (Non Powered) | מסירי איפור ותכשירי ניקוי פנים | 15. טיפוח אישי | 5 | N |
| Dispensers for Cleaning_Hygiene Products | מתקנים לחומרי ניקוי והיגיינה | 14. ניקיון | 5 | N |
| Feminine Hygiene - Towels_Pads | תחבושות היגייניות | 15. טיפוח אישי | 5 | N |
| Fruit Juice Drinks - Ready to Drink (Perishable) | משקאות פירות (קירור) | 10. משקאות קלים | 5 | N |
| Hair - Accessories | אביזרי שיער | 15. טיפוח אישי | 5 | N |
| Ice Cream_Ice Novelties (Shelf Stable) | גלידות (מסומן כמדף) | 6. מזון קפוא | 5 | N |
| Laundry Variety Packs | כביסה — מגוון | 14. ניקיון | 5 | N |
| Pasta_Noodles Variety Packs | פסטה — מגוון | 8. אורז, פסטה וקטניות | 5 | N |
| Pies_Pastries - Sweet (Perishable) | מאפים מתוקים טריים | 4. לחם ומוצרי מאפה | 5 | N |
| Sauces - Cooking (Frozen) | רטבים לבישול קפואים | — | 5 | Y |
| Soups - Prepared Variety Packs | מרקים — מגוון | 7. שימורים ובישול | 5 | N |
| Alcoholic Pre-mixed Drinks | קוקטיילים אלכוהוליים מוכנים | 11. משקאות אלכוהוליים | 4 | N |
| Baby_Infant - Specialised Beverages (Shelf Stable) | תמ"ל ומשקאות לתינוקות | 16. מוצרי תינוקות | 4 | N |
| Desserts (Perishable) | קינוחים (קירור) | — | 4 | Y |
| Dried Breads (Frozen) | לחם יבש קפוא | — | 4 | Y |
| Essential Oils | שמנים אתריים | — | 4 | Y |
| Garlic | שום | 1. פירות וירקות | 4 | N |
| Goose - Prepared_Processed | אווז מעובד | — | 4 | Y |
| Grain Based Products _ Meals - Not Ready to Eat - Savoury (Frozen) | מנות דגנים קפואות להכנה | 6. מזון קפוא | 4 | N |
| Hair Care Products - Replacement Parts | חלקי חילוף למוצרי שיער | 15. טיפוח אישי | 4 | N |
| Lychees (Litchi) | ליצ'י | 1. פירות וירקות | 4 | N |
| Pate (Shelf Stable) | פטה (מדף) | 5. סלטים, ממרחים ונקניקים | 4 | N |
| Personal Hygiene Products Variety Packs | היגיינה אישית — מגוון | 15. טיפוח אישי | 4 | N |
| Pet Food_Drinks Variety Packs | מזון ומשקה לחיות — מגוון | 17. מזון לחיות מחמד | 4 | N |
| Shallots | בצל שאלוט | 1. פירות וירקות | 4 | N |
| Tea - Ready to Drink | תה מוכן לשתייה | 10. משקאות קלים | 4 | N |
| After-Sun Moisturisers | לחות אחרי שמש | 15. טיפוח אישי | 3 | N |
| Apple_Pear Alcoholic Beverage - Sparkling | סיידר מוגז | 11. משקאות אלכוהוליים | 3 | N |
| Aquatic Invertebrates - Prepared_Processed (Perishable) | פירות ים מעובדים (קירור) | — | 3 | Y |
| Asparagus | אספרגוס | 1. פירות וירקות | 3 | N |
| Baby Diapers_Accessories Variety Packs | חיתולים ואביזרים — מגוון | 16. מוצרי תינוקות | 3 | N |
| Cranberries | חמוציות | 1. פירות וירקות | 3 | N |
| Dessert Sauces_Toppings_Fillings (Shelf Stable) | רטבים ומילויים לקינוחים | — | 3 | Y |
| Disposable Food Containers Other | כלי אחסון חד פעמיים אחרים | 19. כלי בית וחד פעמי | 3 | N |
| Exfoliants_Masks | פילינג ומסכות | 15. טיפוח אישי | 3 | N |
| Fats Edible - Animal (Shelf Stable) | שומן מן החי | — | 3 | Y |
| Fats Edible Variety Packs | שומנים — מגוון | — | 3 | Y |
| Fruit Juice Drinks - Not Ready to Drink (Shelf Stable) | תרכיזי מיץ פירות | 10. משקאות קלים | 3 | N |
| Fruit Juice - Ready to Drink (Perishable) | מיץ פירות טרי | 10. משקאות קלים | 3 | N |
| Hair Removal_Masking Products Other | מוצרי הסרת שיער אחרים | 15. טיפוח אישי | 3 | N |
| Leaf Vegetables - Unprepared_Unprocessed Variety Packs | ירקות עלים — מגוון | 1. פירות וירקות | 3 | N |
| Non Personal Repellents | דוחי מזיקים (לא לגוף) | 14. ניקיון | 3 | N |
| Oral Care - Accessories | אביזרי היגיינת פה | 15. טיפוח אישי | 3 | N |
| Peaches | אפרסקים | 1. פירות וירקות | 3 | N |
| Pet Accessory Variety Packs | אביזרים לחיות — מגוון | 17. מזון לחיות מחמד | 3 | N |
| Ready-Made Combination Meals - Not Ready to Eat Variety Packs | ארוחות להכנה — מגוון | — | 3 | Y |
| Shaving - Razors (Powered) | מכונות גילוח חשמליות | — | 3 | Y |
| Shoe Cleaners_Polishers | משחות וניקוי נעליים | 14. ניקיון | 3 | N |
| Tea - Instant | תה נמס | 12. קפה, תה ומשקאות חמים | 3 | N |
| Turkey - Unprepared_Unprocessed | הודו טרי לא מעובד | 3. בשר, עוף ודגים | 3 | N |
| Veal Sausages - Prepared_Processed | נקניקיות עגל | 5. סלטים, ממרחים ונקניקים | 3 | N |
| Vegetable Based Products _ Meals Variety Packs | מנות ירקות — מגוון | — | 3 | Y |
| Vegetable Juice - Ready to Drink (Shelf Stable) | מיץ ירקות | 10. משקאות קלים | 3 | N |
| Adult Incontinence - Pads | רפידות ספיגה למבוגרים | 15. טיפוח אישי | 2 | N |
| Aquatic Plants Unprepared_Unprocessed (Shelf Stable) | אצות לא מעובדות | — | 2 | Y |
| Baby Diapers (Non Disposable) | חיתולי בד | 16. מוצרי תינוקות | 2 | N |
| Bakeware_Ovenware_Grillware (Non Disposable) | תבניות וכלי אפייה | 19. כלי בית וחד פעמי | 2 | N |
| Baking_Cooking Supplies (Shelf Stable) | חומרי אפייה ובישול | 13. תבלינים, רטבים ושמנים | 2 | N |
| Broccoli | ברוקולי | 1. פירות וירקות | 2 | N |
| Cakes - Sweet (Perishable) | עוגות טריות | 4. לחם ומוצרי מאפה | 2 | N |
| Cleaning_Hygiene Products Variety Packs | ניקיון והיגיינה — מגוון | — | 2 | Y |
| Coffee Grinders (Powered) | מטחנות קפה חשמליות | 20. מיוחדים | 2 | N |
| Coffee Substitutes - Instant | תחליפי קפה נמסים | 12. קפה, תה ומשקאות חמים | 2 | N |
| Coffee Substitutes - Ready to Drink | תחליפי קפה מוכנים לשתייה | 10. משקאות קלים | 2 | N |
| Common Chicory | עולש | 1. פירות וירקות | 2 | N |
| Common Cultivated Mushroom (Agaricus) | פטריות שמפיניון | 1. פירות וירקות | 2 | N |
| Dairy_Dairy Substitute Based Drinks - Not Ready to Drink (Shelf Stable) | אבקות משקה חלב | — | 2 | Y |
| Dairy_Egg Based Products _ Meals - Ready to Eat (Perishable) | מנות חלב וביצים מוכנות (קירור) | — | 2 | Y |
| Dairy_Egg Based Products _ Meals - Ready to Eat (Shelf Stable) | מנות חלב וביצים מוכנות (מדף) | — | 2 | Y |
| Denture_Orthodontic - Care | טיפוח תותבות | 15. טיפוח אישי | 2 | N |
| Disinfectants | חומרי חיטוי | 14. ניקיון | 2 | N |
| Feminine_Nursing Hygiene Other | היגיינה נשית והנקה — אחר | 15. טיפוח אישי | 2 | N |
| Food Preparation Equipment Variety Packs | כלי הכנת מזון — מגוון | 19. כלי בית וחד פעמי | 2 | N |
| Fragrances | בשמים | 15. טיפוח אישי | 2 | N |
| Fruit Juice - Not Ready to Drink (Shelf Stable) | תרכיז מיץ | 10. משקאות קלים | 2 | N |
| Fruits - Unprepared_Unprocessed (Fresh) Variety Packs | פירות טריים — מגוון | 1. פירות וירקות | 2 | N |
| General Personal Hygiene Other | היגיינה אישית — אחר | 15. טיפוח אישי | 2 | N |
| Ginger | ג'ינג'ר | 1. פירות וירקות | 2 | N |
| Globe Artichokes | ארטישוק | 1. פירות וירקות | 2 | N |
| Grain Based Products _ Meals - Ready to Eat - Savoury (Perishable) | מנות דגנים מוכנות (קירור) | — | 2 | Y |
| Hair Products Variety Packs | מוצרי שיער — מגוון | 15. טיפוח אישי | 2 | N |
| Herbs_Spices (Perishable) | עשבי תיבול טריים | — | 2 | Y |
| Horseradish | חזרת | — | 2 | Y |
| Lamb - Prepared_Processed | כבש מעובד | — | 2 | Y |
| Lamb - Unprepared_Unprocessed | כבש טרי לא מעובד | 3. בשר, עוף ודגים | 2 | N |
| Meat Substitutes (Perishable) | תחליפי בשר (קירור) | — | 2 | Y |
| Mixed Species Meat_Poultry:Alternative Meat - Prepared_Processed | בשר מעורב מעובד | — | 2 | Y |
| Pineapples | אננס | 1. פירות וירקות | 2 | N |
| Rocket | ארוגולה | 1. פירות וירקות | 2 | N |
| Shiitake Mushrooms | פטריות שיטאקי | 1. פירות וירקות | 2 | N |
| Skin Care Variety Packs | טיפוח עור — מגוון | 15. טיפוח אישי | 2 | N |
| Skin Drying Powder | טלק | 15. טיפוח אישי | 2 | N |
| Soup Additions (Perishable) | תוספות למרק (קירור) | — | 2 | Y |
| Sports Drinks - Rehydration (Ready To Drink) | משקאות ספורט | 10. משקאות קלים | 2 | N |
| Sugar Cane | קני סוכר | 1. פירות וירקות | 2 | N |
| Surface Care Other | טיפוח משטחים אחר | 14. ניקיון | 2 | N |
| Vinegars_Cooking Wines Variety Packs | חומץ ויין לבישול — מגוון | 13. תבלינים, רטבים ושמנים | 2 | N |
| חרדל (אחסון מדף) | חרדל | 13. תבלינים, רטבים ושמנים | 2 | N |
| Adult Incontinence Other | ספיגה למבוגרים — אחר | 15. טיפוח אישי | 1 | N |
| Adult Incontinence - Supplies | ציוד ספיגה למבוגרים | 15. טיפוח אישי | 1 | N |
| Adult Incontinence - Underwear (Non Disposable) | תחתוני ספיגה רב-פעמיים | 15. טיפוח אישי | 1 | N |
| Apricots | משמש | 1. פירות וירקות | 1 | N |
| Aquatic Invertebrates_Fish_Shellfish_Seafood Mixes - Prepared_Processed (Frozen) | תערובות פירות ים קפואות | — | 1 | Y |
| Aquatic Invertebrates - Prepared_Processed (Frozen) | פירות ים מעובדים קפואים | — | 1 | Y |
| Baking_Cooking Supplies (Frozen) | חומרי אפייה קפואים | — | 1 | Y |
| Bananas | בננות | 1. פירות וירקות | 1 | N |
| Bath Additives | תוספי אמבט | 15. טיפוח אישי | 1 | N |
| Bleach | אקונומיקה | 14. ניקיון | 1 | N |
| Bleaching_Lightening Products | מוצרי הבהרה (שיער ועור) | 15. טיפוח אישי | 1 | N |
| Brussel Sprouts | כרוב ניצנים | 1. פירות וירקות | 1 | N |
| Carobs | חרובים | 1. פירות וירקות | 1 | N |
| Celeriac | סלרי שורש | 1. פירות וירקות | 1 | N |
| Chilli Peppers | פלפל חריף | 1. פירות וירקות | 1 | N |
| Coffee Substitutes - Regular(Non-Instant) | תחליפי קפה | 12. קפה, תה ומשקאות חמים | 1 | N |
| Cosmetics - Complexion | איפור פנים | 15. טיפוח אישי | 1 | N |
| Cosmetics - Eyes | איפור עיניים | 15. טיפוח אישי | 1 | N |
| Cosmetics - Nails | לק ומוצרי ציפורניים | 15. טיפוח אישי | 1 | N |
| Cream_Cream Substitutes (Frozen) | שמנת קפואה | 2. מוצרי חלב וביצים | 1 | N |
| Detergent Boosters_Laundry Bleaches | מגבירי ניקוי ומלבינים לכביסה | 14. ניקיון | 1 | N |
| Fabric Protectors | מגיני בדים | 14. ניקיון | 1 | N |
| Fish - Unprepared_Unprocessed (Perishable) | דגים טריים | 3. בשר, עוף ודגים | 1 | N |
| Food_Beverage Storage Containers | כלי אחסון למזון | 19. כלי בית וחד פעמי | 1 | N |
| Fresheners_Deodorisers Variety Packs | מטהרי אוויר — מגוון | 14. ניקיון | 1 | N |
| Fruit Herbal Infusions - Instant | חליטות נמסות | 12. קפה, תה ומשקאות חמים | 1 | N |
| Fruit Herbal Infusions - Ready to Drink | חליטות מוכנות לשתייה | 10. משקאות קלים | 1 | N |
| General Personal Hygiene Variety Packs | היגיינה אישית — מגוון | 15. טיפוח אישי | 1 | N |
| Goose - Unprepared_Unprocessed | אווז טרי | 3. בשר, עוף ודגים | 1 | N |
| Grains_Cereal - Ready to Eat - (Perishable) | דגנים מוכנים (קירור) | — | 1 | Y |
| Hair Care Products Variety Packs | טיפוח שיער — מגוון | 15. טיפוח אישי | 1 | N |
| Ice | קרח | — | 1 | Y |
| Lemongrass | למון גראס | 1. פירות וירקות | 1 | N |
| Lip Balms | שפתונים לחות | 15. טיפוח אישי | 1 | N |
| Mangos | מנגו | 1. פירות וירקות | 1 | N |
| Mould_Mildew Removers | מסירי עובש | 14. ניקיון | 1 | N |
| Nursing Hygiene Accessories | אביזרי הנקה | 16. מוצרי תינוקות | 1 | N |
| Okra | במיה | 1. פירות וירקות | 1 | N |
| Onions | בצל | 1. פירות וירקות | 1 | N |
| Oral Care - Aids (Powered) | עזרי היגיינת פה חשמליים | — | 1 | Y |
| Other Sauces Dipping_Condiments_Savoury Toppings_Savoury Spreads_Marinades (Shelf Stable) | רטבים, מטבלים ומרינדות (מדף) | — | 1 | Y |
| Paper Filters | פילטרים מנייר | 19. כלי בית וחד פעמי | 1 | N |
| Pet Accessories Other | אביזרים לחיות — אחר | 17. מזון לחיות מחמד | 1 | N |
| Pet Housing_Bedding Non Disposable | מיטות ובתים לחיות | 17. מזון לחיות מחמד | 1 | N |
| Pies_Pastries_Pizzas_Quiches - Savoury (Perishable) | מאפים מלוחים טריים | — | 1 | Y |
| Plums | שזיפים | 1. פירות וירקות | 1 | N |
| Potatoes | תפוחי אדמה | 1. פירות וירקות | 1 | N |
| Quark Products (Shelf Stable) | גבינת קווארק | 2. מוצרי חלב וביצים | 1 | N |
| Ready-Made Combination Meals - Ready to Eat (Perishable) | ארוחות מוכנות (קירור) | — | 1 | Y |
| Salt_Pepper_Spice Mills (Non Powered) | מטחנות תבלין | 19. כלי בית וחד פעמי | 1 | N |
| Sandwiches_Filled Rolls_Wraps Variety Packs | כריכים — מגוון | — | 1 | Y |
| Serving_Eating_Drinking Tableware Other | כלי הגשה ואוכל אחרים | 19. כלי בית וחד פעמי | 1 | N |
| Shaving - Blades | להבי גילוח | 15. טיפוח אישי | 1 | N |
| Skewers_Sticks | שיפודים | 19. כלי בית וחד פעמי | 1 | N |
| Snow Peas | אפונת שלג | 1. פירות וירקות | 1 | N |
| Soursop | גואנבנה | 1. פירות וירקות | 1 | N |
| Squash (Opo) | דלעת | 1. פירות וירקות | 1 | N |
| Stock Liquid_Bones (Shelf Stable) | ציר נוזלי | 7. שימורים ובישול | 1 | N |
| Strawberries | תותים | 1. פירות וירקות | 1 | N |
| Tomatoes - Round | עגבניות | 1. פירות וירקות | 1 | N |
| Tomato Ketchup_Ketchup Substitutes (Perishable) | קטשופ (קירור) | 13. תבלינים, רטבים ושמנים | 1 | N |
| Veal - Prepared_Processed | עגל מעובד | — | 1 | Y |
| Vegetable Juice Drinks - Not Ready to Drink (Shelf Stable) | תרכיזי משקה ירקות | 10. משקאות קלים | 1 | N |
| Waste Storage Products - Other | מוצרי פסולת אחרים | 19. כלי בית וחד פעמי | 1 | N |
| Water_Beverage Equipment Other | ציוד מים ומשקאות | 19. כלי בית וחד פעמי | 1 | N |
| Wine - Fortified | יין מחוזק | 11. משקאות אלכוהוליים | 1 | N |
| ארוחות משולבות מוכנות מראש – לא מוכן לאכילה (אחסון מדף) | ארוחות להכנה (מדף) | — | 1 | Y |
| ביסקוויטים/עוגיות במארז משולב | ביסקוויטים ועוגיות — מגוון | 9. חטיפים ומתוקים | 1 | N |
| בסקויטים/עוגיות (אחסון מדף) | ביסקוויטים ועוגיות (מדף) | 9. חטיפים ומתוקים | 1 | N |
| דאודורנטים | דאודורנטים | 15. טיפוח אישי | 1 | N |
| דג – לא מוכן/לא מעובד (קפוא) | דגים קפואים לא מעובדים | 3. בשר, עוף ודגים | 1 | N |
| דג – מוכן/מעובד (קפוא) | דגים מעובדים קפואים | — | 1 | Y |
| הודו – מוכן/מעובד | הודו מעובד | — | 1 | Y |
| חטיפים מארז משולב | חטיפים — מגוון | 9. חטיפים ומתוקים | 1 | N |
| חלב/תחליפי חלב (אחסון מדף) | חלב ותחליפי חלב (מדף) | 2. מוצרי חלב וביצים | 1 | N |
| מגשים | מגשים | 19. כלי בית וחד פעמי | 1 | N |
| מוצרי טיפוח עור/לחות | טיפוח עור וקרמי לחות | 15. טיפוח אישי | 1 | N |
| מוצרי מאפייה מתוקים מארז משולב | מאפים מתוקים — מגוון | — | 1 | Y |
| ממריצים/משקאות אנרגיה - מוכנה לשתייה | משקאות אנרגיה | 10. משקאות קלים | 1 | N |
| מתוקים | ממתקים | 9. חטיפים ומתוקים | 1 | N |
| פסטה/אטריות – מוכן לאכילה (מתכלים) | פסטה מוכנה (קירור) | — | 1 | Y |
| פרי – מוכן/מעובד (מתכלה) | פירות חתוכים טריים | 1. פירות וירקות | 1 | N |
| שקיות אשפה | שקיות אשפה | 19. כלי בית וחד פעמי | 1 | N |
| תחליפי בשר (מתכלים) | תחליפי בשר (קירור) | — | 1 | Y |
| תחליפי חמאה/חמאה (אחסון מדף) | חמאה ותחליפי חמאה (מדף) | 2. מוצרי חלב וביצים | 1 | N |
| תחליפי חמאה/חמאה (מתכלה) | חמאה ותחליפי חמאה (קירור) | 2. מוצרי חלב וביצים | 1 | N |
| תמציות/מלח/מרככי בשר (אחסון מדף) | תמציות, מלח ומרככי בשר | 13. תבלינים, רטבים ושמנים | 1 | N |
| Alternative Meat_Poultry Species - Prepared_Processed | בשר ועוף ממינים אחרים, מעובד | — | 0 | Y |
| Baby Cutlery (Non Disposable) | סכו"ם לתינוקות | 16. מוצרי תינוקות | 0 | N |
| Beetroot | סלק | 1. פירות וירקות | 0 | N |
| Cappuccino Creamers (Non Powered) | מלבינים לקפה | 12. קפה, תה ומשקאות חמים | 0 | N |
| Coffee_Tea_Substitutes Variety Packs | קפה, תה ותחליפים — מגוון | 12. קפה, תה ומשקאות חמים | 0 | N |
| Cosmetic Products Other | מוצרי קוסמטיקה אחרים | 15. טיפוח אישי | 0 | N |
| Cosmetics - Lips | איפור שפתיים | 15. טיפוח אישי | 0 | N |
| Damsons | שזיף דמסון | 1. פירות וירקות | 0 | N |
| Depilation_Epilation (Powered) | מכשירי הסרת שיער חשמליים | — | 0 | Y |
| Dressing_Dips (Frozen) | מטבלים קפואים | — | 0 | Y |
| Endive (Curled) | אנדיב | 1. פירות וירקות | 0 | N |
| Flat Sweet Peppers (Tomato Peppers) | פלפל עגבנייה | 1. פירות וירקות | 0 | N |
| Fruit Juice - Not Ready to Drink (Frozen) | תרכיז מיץ קפוא | — | 0 | Y |
| Herbal Chew_Snuff - Non Tobacco | טבק לעיסה ללא טבק | 20. מיוחדים | 0 | N |
| Jerusalem Artichokes | ארטישוק ירושלמי | 1. פירות וירקות | 0 | N |
| Kitchen Cookware_Bakeware Variety Packs | כלי בישול — מגוון | 19. כלי בית וחד פעמי | 0 | N |
| Kitchen Merchandise Variety Packs | מוצרי מטבח — מגוון | 19. כלי בית וחד פעמי | 0 | N |
| Mayonnaise_Mayonnaise Substitutes (Frozen) | מיונז קפוא | — | 0 | Y |
| Mugs_Cups (Non Disposable) | ספלים | 19. כלי בית וחד פעמי | 0 | N |
| Napkin Rings | טבעות למפיות | 19. כלי בית וחד פעמי | 0 | N |
| Non Alcoholic Beverages Variety Packs - Not Ready to Drink | משקאות לא אלכוהוליים להכנה — מגוון | — | 0 | Y |
| Oil Diffusers (Non Powered) | מפיצי ריח | 14. ניקיון | 0 | N |
| Oral Hygiene Variety Packs | היגיינת הפה — מגוון | 15. טיפוח אישי | 0 | N |
| Pet Nutritional Supplements Variety Packs | תוספי תזונה לחיות | 17. מזון לחיות מחמד | 0 | N |
| Pies_Pastries - Sweet (Frozen) | מאפים מתוקים קפואים | — | 0 | Y |
| Sanitizers | חומרי חיטוי ידיים ומשטחים | — | 0 | Y |
| Seafood Variety Packs | פירות ים — מגוון | — | 0 | Y |
| Serving_Drinking Glasses | כוסות שתייה | 19. כלי בית וחד פעמי | 0 | N |
| Serving Trays | מגשי הגשה | 19. כלי בית וחד פעמי | 0 | N |
| Soups - Prepared (Perishable) | מרקים מוכנים (קירור) | — | 0 | Y |
| Sour Cherries | דובדבן חמוץ | 1. פירות וירקות | 0 | N |
| Stonefruit Hybrids | פירות גלעין מוכלאים | 1. פירות וירקות | 0 | N |
| Vegetable Juice - Ready to Drink (Perishable) | מיץ ירקות טרי | 10. משקאות קלים | 0 | N |
| Winged Pea | אפונה כנפית | — | 0 | Y |
| Yardlong Beans | שעועית ארוכה | — | 0 | Y |
| אחסון מזון (חד פעמי) | אחסון מזון חד פעמי | 19. כלי בית וחד פעמי | 0 | N |
| כוסות הגשה / שתייה | כוסות הגשה ושתייה | 19. כלי בית וחד פעמי | 0 | N |
| מזון/משקה/טבק - מארזים משולבים | מזון, משקה וטבק — מגוון | — | 0 | Y |
| נקניקיות עגל – מוכנים/מעובדים | נקניקיות עגל | 5. סלטים, ממרחים ונקניקים | 0 | N |
| נקניקיות עוף – מוכנים/מעובדים | נקניקיות עוף | 5. סלטים, ממרחים ונקניקים | 0 | N |
| סוכריות גומי/סוכריות גומי תחליפי ממתקים | סוכריות גומי | 9. חטיפים ומתוקים | 0 | N |
| עגבניות – מארז משולב | עגבניות — מגוון | — | 0 | Y |
| עוגות/מאפים - מתוק (מתכלה) | עוגות ומאפים מתוקים טריים | 4. לחם ומוצרי מאפה | 0 | N |
| רטבים/מתבלים (אחסון מדף) | רטבים ומתבלים (מדף) | — | 0 | Y |
| שוקולד ושילובי שוקולד/ממתקי סוכר – ממתקים | שוקולד וממתקים | 9. חטיפים ומתוקים | 0 | N |
