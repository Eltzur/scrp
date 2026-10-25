# SU11A-55 rule fixes v1 -> v1.1: before / after on the full export

Read-only local export of 24 Oct 2026, 131,225 live non-pseudo items. Fixes are applied one at a time,
in this order, and each diff is against the previous step (rules + GS1 + the existing AI labels, the same
combine rule the import uses). S0 reproduces the published v1 labels exactly (0 differences).
"Changed" = the final category or confidence of an item changed. Samples are 20 changed items drawn
pseudo-randomly (md5 order); when a fix changed 20 items or fewer, all of them are listed.

| Step | high | medium | low | unclassified | changed | category changed |
|---|---:|---:|---:|---:|---:|---:|
| S0 | 108,437 | 7,210 | 13,704 | 1,874 | - | - |
| F1 | 108,621 | 7,120 | 13,322 | 2,162 | 944 | 590 |
| F2 | 108,622 | 7,121 | 13,321 | 2,161 | 3 | 2 |
| F3 | 108,622 | 7,121 | 13,321 | 2,161 | 5 | 5 |
| F4 | 108,620 | 7,134 | 13,310 | 2,161 | 13 | 7 |
| F5 | 108,617 | 7,137 | 13,310 | 2,161 | 15 | 13 |
| F6 | 108,630 | 7,128 | 13,306 | 2,161 | 14 | 11 |
| F7 | 108,636 | 7,126 | 13,302 | 2,161 | 63 | 63 |
| F8 | 108,654 | 7,121 | 13,297 | 2,153 | 24 | 24 |
| F9 | 108,655 | 7,120 | 13,297 | 2,153 | 9 | 9 |
| F10 | 108,653 | 7,127 | 13,292 | 2,153 | 35 | 28 |
| F11 | 108,653 | 7,127 | 13,292 | 2,153 | 3 | 3 |
| F12 | 108,655 | 7,127 | 13,290 | 2,153 | 2 | 2 |
| F13 | 108,657 | 7,128 | 13,287 | 2,153 | 12 | 8 |
| F14 | 108,660 | 7,126 | 13,286 | 2,153 | 9 | 7 |

## F1: fresh fruit needs evidence: fruit words only as the head of the name; bare פירות/פרי only with a fresh-produce word

- `D01.C04` keywords head: `פירות`, `פרי`
- `D01.C04` keywords remove: `פירות`, `פרי`
- `D01.C04` keywords add: `^פירות,^פרי+שקיל*,במשקל,לק"ג,ארוז,ארוזים,ארוזה,טרי,טריים,טריות,תוצרת,יבוא,מובחר*,אורגני*`, `^גרגירי רימון`, `^גרעיני רימון`, `^פלחי פומלה`, `^פלחי אשכולית`, `^פינגר ליים`
- `D08.C09` negative_keywords add: `רימון`, `רימונים`
- `D09.C05` keywords replace: `פטל` -> `^פטל`
- code: `^` head anchor; pack words חצי / רבע / סלסלת / סלסלה / ארגז no longer count as a content position

Changed 944 (category 590); confidence before {'high': 313, 'low': 449, 'medium': 182}, after {'unclassified': 288, 'high': 497, 'low': 67, 'medium': 92}.
Department moves: D01->-: 286; D01->D08: 44; D01->D09: 26; D01->D07: 23; D08->D08: 22; D15->D12: 14; D02->D02: 11; D09->D09: 10; D01->D12: 10; D01->D02: 9; D05->D05: 8; D01->D05: 8

| item_code | name | before | after |
|---|---|---|---|
| 7296155150353 | מפריד רימונים | D01.C04 high rule | unclassified |
| 7297588028530 | שרשרת רימונים | D16.C03 medium rule | D16.C03 high rule |
| 4820042179047 | פלחי מרמלדה רימון אש | D08.C02 low ai | D08.C02 high ai |
| 666522900091 | צ`יברס מרמלדת תפוזים בסגנון אנגלי 340 גר | D07.C18 low ai | D07.C18 high ai |
| 6941881829110 | סיגריה TESLA  אבטיח | D10.C05 medium rule | D10.C05 high rule |
| 111630 | סט סכיני פירות מעץ | D15.C03 low ai | D12.C10 high rule |
| 7290116851785 | סוחט לימונים ידני | D01.C04 high rule | unclassified |
| 7290010549108 | רכז רימונים טהור 100% | D01.C04 high rule | unclassified |
| 4820043250028 | קיסל תות 250 גר | D01.C04 high rule | unclassified |
| 710497379243 | TINYS משפחתי תות 130 גרם | D01.C04 high rule | unclassified |
| 333041 | טבעות אננס יבש במשקל | D16.C03 medium rule | D16.C03 high rule |
| 812859020098 | קונפיטורת פטל 450 גר | D07.C20 low rule | D07.C20 high rule |
| 64331382167 | קרחונים להקפאה פירות וולצס 510 גרם | D15.C06 low rule | D15.C06 high rule |
| 7290000307015 | אפונת גינה גדול 550 ג' פרי הגליל | D06.C01 low ai | D07.C08 high rule |
| 728614224338 | בייטס דובדבן קטן 113 גרם | D01.C04 high rule | unclassified |
| 7290014453555 | חמוציות חצאים ברכז תפוחים 260 ג' | D01.C05 low rule | D01.C05 high rule |
| 7290114311526 | מולר פרופ תפוז ג'ינג'ר | D02.C03 medium rule | D02.C03 high rule |
| 7290001594117 | סליק פאנטה ענבים 330 | D09.C04 low ai | D09.C03.S02 high rule |
| 7290114314602 | פרוטאין אפרסק 1.6% 200 ג | D01.C04 high rule | unclassified |
| 728614224277 | בייטס דובדבן אישי 67 גרם | D01.C04 high rule | unclassified |

## F2: פרוטאין + a percentage -> yogurt

- `D02.C03` keywords add: `פרוטאין+§pct`

Changed 3 (category 2); confidence before {'high': 1, 'low': 1, 'unclassified': 1}, after {'medium': 1, 'high': 2}.
Department moves: D07->D02: 1; -->D02: 1

| item_code | name | before | after |
|---|---|---|---|
| 7290114313476 | פרוטאין קוקוס 0% שומ | D07.C23 low ai | D02.C03 high rule |
| 3800093560415 | טיםס -לחם שטוח 20% פרוטאין 270 גרם | D05.C01 high rule | D05.C01 medium rule |
| 7290114314602 | פרוטאין אפרסק 1.6% 200 ג | unclassified | D02.C03 high rule |

## F3: flavoured water is water, not a carbonated drink

- `D09.C03` negative_keywords add: `מים בטעם`, `מים בטעמים`

Changed 5 (category 5); confidence before {'high': 5}, after {'high': 5}.
Department moves: D09->D09: 5

| item_code | name | before | after |
|---|---|---|---|
| 7290019056263 | שוופס מים בטעמים אפרסק 1.5 ל' | D09.C03.S02 high gs1 | D09.C01 high gs1 |
| 7290019056256 | שוופס מים בטעמים תפוח 1.5 ל' | D09.C03.S02 high gs1 | D09.C01 high gs1 |
| 7290019056249 | שוופס מים בטעמים ענבים 1.5 ל' | D09.C03.S02 high gs1 | D09.C01 high gs1 |
| 7290019056270 | שוופס מים בטעמים פירות יער 1.5 ל' | D09.C03.S02 high gs1 | D09.C01 high gs1 |
| 7290119776894 | שוופס מים בטעמים אננס 1.5 ל' | D09.C03.S02 high gs1 | D09.C01 high gs1 |

## F4: טבעול pins the frozen department (brand hint, pin=yes)

- `brand_category_hints_v1_1.csv`: טבעול -> D06.C08, pin=yes

Changed 13 (category 7); confidence before {'low': 11, 'high': 2}, after {'medium': 13}.
Department moves: D08->D06: 3; D03->D06: 2; D04->D06: 2

| item_code | name | before | after |
|---|---|---|---|
| 7290122782066 | טבעול חטיפי תירס בד"ץ 1 ק"ג | D08.C05.S02 low ai | D06.C08 medium rule |
| 7290111566271 | חטיפי תירס טבעול 657 גר | D08.C05.S02 high rule | D06.C08 medium rule |
| 7290118428855 | טבעול חטיפי כרובית 4 | D06.C08 low rule | D06.C08 medium rule |
| 7290111566547 | טבעול חזה בגריל צמחוני | D06.C08 low rule | D06.C08 medium rule |
| 7290111566318 | טבעול שניצל דק מן הצ | D03.C06 low ai | D06.C08 medium rule |
| 7290118425007 | טבעול מקלוני ירקות כתומים | D06.C08 low rule | D06.C08 medium rule |
| 7290118425021 | טבעול מקלוני ירקות י | D06.C08 low rule | D06.C08 medium rule |
| 7290118428879 | טבעול נאגטס טבעי ללא | D06.C08 low rule | D06.C08 medium rule |
| 7290012522581 | טבעול שניצל תירס ללא | D06.C08 low rule | D06.C08 medium rule |
| 7290115205633 | סנסשיונל נקניקניות 350 גר טבעול | D04.C01.S02 low ai | D06.C08 medium rule |
| 7290111566240 | טבעול שניצל דק בטעם | D03.C06 low ai | D06.C08 medium rule |
| 7290118428893 | חטיפי ברוקולי טבעול | D08.C05 high ai | D06.C08 medium rule |
| 7290111566332 | נקניקיות וינר צמחוניות 680 גרם טבעול | D04.C01.S02 low ai | D06.C08 medium rule |

## F5: dragée is chocolate

- `D08.C01` keywords add: `דרגיה`, `דרג'ה`, `דרז'ה`, `דראג'ה`, `דראגה`

Changed 15 (category 13); confidence before {'high': 7, 'low': 4, 'medium': 4}, after {'low': 4, 'medium': 7, 'high': 4}.
Department moves: D08->D08: 7; D02->D08: 3; D01->D08: 2; D06->D08: 1

| item_code | name | before | after |
|---|---|---|---|
| 8022470213386 | דרגיה פריסקו שקד חלב | D02.C01 low rule | D08.C01 low rule |
| 8022470213492 | דרגיה דובדובן לבן 500 גר PRISCO MAX | D06.C02 low ai | D08.C01 high rule |
| 8022470226379 | דרגיה  קשיו מריר 500 גר PRISCO MAX | D08.C09 high rule | D08.C01 medium rule |
| 8022470213478 | דרג'ה דובדבן חלב 500 | D02.C01 low rule | D08.C01 low rule |
| 7290000004587 | סוכריות דרז'ה | D08.C02 high rule | D08.C02 medium rule |
| 8022470253115 | דרגיה פריסקו אגוז מל | D08.C09 medium rule | D08.C01 medium rule |
| 105650 | פקאן/לוז שיש דרז'ה פרווה | D08.C09 high ai | D08.C09 low ai |
| 8022470213508 | דרגיה צימוקים חלב 500 גר PRISCO MAX | D01.C05 low rule | D08.C01 low rule |
| 8022470213430 | דרגיה לוז לבן 500 גר PRISCO MAX | D08.C02 medium ai | D08.C01 high rule |
| 8022470213546 | דרגיה בוטנים מריר 500 גר PRISCO MAX | D08.C09 high rule | D08.C01 medium rule |
| 8022470213409 | דרגיה פריסקו שקד חלב | D02.C01 medium rule | D08.C01 medium rule |
| 8022470213393 | דרגיה שקד מריר 500 גר PRISCO MAX | D08.C09 high rule | D08.C01 medium rule |
| 8022470213423 | דרגיה לוז מריר 500 גר PRISCO MAX | D08.C01.S03 medium ai | D08.C01 high rule |
| 8022470213485 | דרגיה דובדובן מריר 500 ג PRISCO MAX | D08.C02 high ai | D08.C01 high rule |
| 8022470213515 | דרגיה צימוקים מריר 500 גר PRISCO MAX | D01.C05 high rule | D08.C01 medium rule |

## F6: weighed / loose nut mixes (מעורב טבעי, מובחר, קלוי ...) are nuts, not meat

- `D08.C09` keywords add: `מעורב+טבעי,מובחר*,קלוי*,מלוח*,עשיר,אקסטרא,אקסטרה,עממי,בינוני,מסוכר*,מנצ'ס,מאנצ'ס`
- `D03` negative_keywords add: `מעורב+טבעי,מובחר*,קלוי*,מלוח*,עשיר,אקסטרא,אקסטרה,עממי,בינוני,מסוכר*,מנצ'ס,מאנצ'ס`

Changed 14 (category 11); confidence before {'low': 4, 'high': 1, 'medium': 9}, after {'high': 14}.
Department moves: D03->D08: 11

| item_code | name | before | after |
|---|---|---|---|
| 333028 | מעורב פיצוחים אקסטרא במשקל | D08.C09 low ai | D08.C09 high rule |
| 5627 | מעורב טבעי | D03 medium rule | D08.C09 high rule |
| 333177 | מעורב מובחר טבעי שקיל | D03.C03 high ai | D08.C09 high rule |
| 93543 | מעורב קלוי עם מלח | D08.C09 low ai | D08.C09 high rule |
| 7290006029126 | מעורב אקסטרא 350 ג' אלמנאר | D03 medium rule | D08.C09 high rule |
| 7290000914480 | מעורב טבעי | D03 medium rule | D08.C09 high rule |
| 5390 | מעורב עשיר | D03 medium rule | D08.C09 high rule |
| 7290000954127 | מעורב מסוכרים | D03 medium rule | D08.C09 high rule |
| 7290010562442 | מעורב בינוני 350 ג' | D03 medium rule | D08.C09 high rule |
| 7290003715299 | מעורב מובחר זארובי 3 | D03 medium rule | D08.C09 high rule |
| 7290000977836 | מעורב טבעי תפזורת | D03 low rule | D08.C09 high rule |
| 7290017784311 | הכל קלוי מעורב אקסטר | D08.C09 low ai | D08.C09 high rule |
| 7290006029188 | מעורב עממי אלמנר 400 | D03 medium rule | D08.C09 high rule |
| 7290000924489 | מעורב טבעי | D03 medium rule | D08.C09 high rule |

## F7: רסק by context: with a fruit -> baby food; otherwise tomato paste (canned)

- `D13.C04` keywords add: `רסק+תפו*,תפ"ע,ת'ע,אגס*,בננה,בננות,אפרסק*,פירות,תות*,שזיפים`
- `D13.C04` negative_keywords remove: `רסק`
- `D07.C08` negative_keywords add: `רסק+תפו*,תפ"ע,ת'ע,אגס*,בננה,בננות,אפרסק*,פירות,תות*,שזיפים`
- `D01.C04` negative_keywords replace: `רסק` -> `!רסק`
- code: hard negatives (`!`) also refuse the GS1 group's id (GS1 group Apples -> fresh fruit)

Changed 63 (category 63); confidence before {'high': 52, 'low': 9, 'medium': 2}, after {'high': 58, 'low': 5}.
Department moves: D07->D13: 54; D01->D13: 8; D09->D13: 1

| item_code | name | before | after |
|---|---|---|---|
| 43427189002 | רסק תפוחים בתוספת סו | D07.C08 high rule | D13.C04 high rule |
| 7290017058146 | רסק תפו"ע עם אפרסק 4 יח' 12X | D07.C08 high rule | D13.C04 high rule |
| 43427781015 | רסק תפוחים סוכר 1.36 ק"ג | D07.C08 high rule | D13.C04 low rule |
| 55369903820 | אפלסנקס שישיות רסק תפוע אגס ללתס | D07.C08 low rule | D13.C04 low rule |
| 7290011154103 | דרומה רסק תפו"ע ללא סוכר 560 גרם | D07.C08 high rule | D13.C04 high rule |
| 55369902793 | רסק תפ"ע צנצנת לל"ס 1.36 | D07.C08 high rule | D13.C04 low rule |
| 7290002881209 | רסק תפוחי עץ ממותק 720 גרם | D07.C08 high rule | D13.C04 high rule |
| 55369902342 | רסק תפו"ע ביתי אפל ס | D07.C08 high rule | D13.C04 high rule |
| 55369901499 | אפלסנקס שישיות רסק תפוחי עץ טרופי ללא תוספת סוכר | D07.C08 low rule | D13.C04 low rule |
| 55369903295 | אפלסנק רסק תפו"ע ללת"ס 652 גרם | D07.C08 high rule | D13.C04 high rule |
| 7290013903594 | ליב, רסק תפוחי עץ 100% טבעי, 670 גרם | D09.C04 low ai | D13.C04 high rule |
| 43427200752 | רסק תפוחים ממותק 680 גר | D07.C08 high rule | D13.C04 high rule |
| 7290117266021 | רביעיית רסק תפוחי עץ ללא תוספת סוכר 113 ג' | D07.C08 high rule | D13.C04 high rule |
| 7290013521385 | רסק תפוחים אורגני 70 | D07.C08 high rule | D13.C04 high rule |
| 37323116118 | רסק תפוחים ללא סוכר | D07.C08 high rule | D13.C04 high rule |
| 7290002111139 | רסק תפ"ע ללא סוכר A2 פ"מ | D01.C04 medium gs1 | D13.C04 high rule |
| 43427200776 | רסק תפוחים בטעם דובד | D07.C08 high rule | D13.C04 high rule |
| 710069805019 | רסק תפו"ע גפן 1.36 ק | D07.C08 high rule | D13.C04 high rule |
| 7290012019258 | רסק תפו""ע פלסטיק 4יח'12X | D07.C08 high rule | D13.C04 high rule |
| 7290012019265 | רסק תפו""ע פלסטיק דיאט 4יח'12X | D07.C08 high rule | D13.C04 high rule |

## F8: product lines the AI did not know (cereals, concentrate, press, nut brand)

- `D07.C22` keywords add: `סיני מיניס`, `סיני מיני`, `דליפקאן`
- `D09.C05` keywords add: `ויטמינצ'יק`, `ויטמינציק`
- `D09.C05` negative_keywords add: `קרחון`, `קרחונים`, `ארטיק`
- `D16.C07` keywords add: `שבועון`, `ירחון`, `עיתונים`, `מגזינים`
- `D08.C09` keywords add: `מאנצ'ס`, `מנצ'ס`, `מאנצס`, `מנצס`

Changed 24 (category 24); confidence before {'medium': 6, 'unclassified': 8, 'low': 6, 'high': 4}, after {'high': 22, 'medium': 1, 'low': 1}.
Department moves: -->D08: 5; D09->D09: 4; D08->D08: 3; D07->D08: 3; -->D09: 2; D16->D08: 1; D08->D07: 1; D03->D08: 1; D06->D08: 1; D12->D07: 1; D13->D09: 1; -->D16: 1

| item_code | name | before | after |
|---|---|---|---|
| 7290001183113 | מנצס פלאפל דק | D06.C07 high rule | D08.C09 medium rule |
| 7290009068962 | מנצס במשקל | unclassified | D08.C09 high rule |
| 103950 | מסיבת מנצ'ס | D16.C05 medium ai | D08.C09 high rule |
| 7613287182425 | ויטמינצ`יק תפוח בננה ותות 110 גר` | unclassified | D09.C05 high rule |
| 7290115208061 | ויטמינצ'יק תפוח 1 ליטר | D09.C04 high ai | D09.C05 high rule |
| 68962 | מנצס במשקל | unclassified | D08.C09 high rule |
| 7290115208009 | ויטמינצ'יק ענבים 1 ל | D09.C04 medium ai | D09.C05 high rule |
| 7290000976754 | מאנצ'ס תפזורת | D08.C05.S02 low ai | D08.C09 high rule |
| 7290112495433 | דליפקאן 400 גר | D12.C01 high ai | D07.C22 high rule |
| 7290001751558 | מנצ'ס | unclassified | D08.C09 high rule |
| 7290115207965 | ויטמינציק מנגו אפרסק | unclassified | D09.C05 high rule |
| 92393 | מנצס במשקל | D08.C02 medium ai | D08.C09 high rule |
| 7290017784007 | הכל קלוי מנצס 170 גר | D07.C14 medium ai | D08.C09 low rule |
| 7290118428220 | ויטמינצ'יק שקוף ענבים 12*1ליטר | D09.C04 medium ai | D09.C05 high rule |
| 7290018566763 | מנצ'ס 400גר בשקית | D07.C07 low ai | D08.C09 high rule |
| 7290006029072 | מנצ'ס אלמנאר 300 ג' | D07.C14 medium ai | D08.C09 high rule |
| 7290018566558 | מנצס 150 גר בשקית קל | D08.C02 low ai | D08.C09 high rule |
| 7290115207941 | ויטמינצ'יק אננס 1 ליטר | D09.C04 high ai | D09.C05 high rule |
| 475073 | מנצס | unclassified | D08.C09 high rule |
| 7290122783544 | ויטמינציק טעם סודי ב | D13.C06 low ai | D09.C05 high rule |

## F9: שנק is a pastry, not cinnamon

- `D05.C06` keywords add: `שנק`, `שנקים`
- `D05.C06` negative_keywords add: `פיצה`
- `D07.C14` negative_keywords add: `שנק`, `שנקים`

Changed 9 (category 9); confidence before {'high': 7, 'medium': 2}, after {'high': 8, 'medium': 1}.
Department moves: D07->D05: 7; D06->D05: 1; D08->D05: 1

| item_code | name | before | after |
|---|---|---|---|
| 7290002020196 | שנק קינמון מנה אישית | D07.C14 high rule | D05.C06 high rule |
| 693493095945 | מארז שנק קינמון | D07.C14 high rule | D05.C06 high rule |
| 7290006210289 | בונזור שנק קינמון. | D07.C14 medium rule | D05.C06 high rule |
| 693493095914 | מארז שנק וניל | D06.C03 medium ai | D05.C06 high rule |
| 7290119733002 | שנק וניל 400 גרם | D07.C18 high ai | D05.C06 high rule |
| 7290119733057 | שנק קינמון 400 גרם | D07.C14 high rule | D05.C06 high rule |
| 7290119732999 | שנק שוקולד 400 גרם אנטקו | D08.C01 high rule | D05.C06 medium rule |
| 6210289 | שנק קינמון בונז`ור | D07.C14 high rule | D05.C06 high rule |
| 7290000096018 | שנק קינמון | D07.C14 high rule | D05.C06 high rule |

## F10: cabbage with dressing / fruit is a salad

- `D04.C03` keywords add: `כרוב,גזר+חמוציות,צימוקים,מיונז,במיונז,אסייתי,אסיאתי,קולסלאו`, `במיונז`
- `D01.C01` negative_keywords add: `חמוציות`, `צימוקים`, `במיונז`, `קולסלאו`
- `D01.C05` negative_keywords add: `חמוציות,צימוקים+כרוב,גזר,סלט`
- `D15.C04` negative_keywords add: `במיונז`, `מיונז`

Changed 35 (category 28); confidence before {'high': 27, 'medium': 2, 'low': 6}, after {'high': 25, 'medium': 9, 'low': 1}.
Department moves: D01->D04: 21; D04->D04: 6; D15->D04: 1

| item_code | name | before | after |
|---|---|---|---|
| 7290011462734 | כרוב לבן במיונז - קו | D01.C01 high rule | D04.C03 high rule |
| 7290000018782 | כרוב קולסלאו | D01.C01 high rule | D04.C03 high rule |
| 7290001881873 | כרוב כבוש עם חמוציות | D04.C05 high rule | D04.C03 low rule |
| 7290100890660 | גביע תפו"א במיונז קלאס פוד 250 גרם | D15.C04 medium rule | D04.C03 medium rule |
| 7290018946350 | חמוציות כרוב כבוש 1 קילו  אדמ | D04.C03 low ai | D04.C03 high rule |
| 7290001548691 | כרוב אדום במיונז 250 | D01.C01 high rule | D04.C03 high rule |
| 7290001548424 | כרוב קולסלאו 250 גרם | D01.C01 high rule | D04.C03 high rule |
| 7290011462536 | חצילים אפויים במיונז | D01.C01 high rule | D04.C03 medium rule |
| 7290001199404 | כרוב במלח עם חמוציות 1 ק"ג | D04.C05 high ai | D04.C03 high rule |
| 7290121137850 | כרוב במיונז הכוכב של | D01.C01 high rule | D04.C03 high rule |
| 7290111650840 | כרוב לבן עם גזר במיונז לימונס 250 גרם | D01.C01 high rule | D04.C03 high rule |
| 7290000018980 | חציל אפוי במיונז | D01.C01 high rule | D04.C03 medium rule |
| 7290100890257 | גביע חציל במיונז על האש קלאס פוד 250 גרם | D04.C03 low ai | D04.C03 high rule |
| 7290006346971 | חציל אפוי במיונז 250 | D01.C01 high rule | D04.C03 medium rule |
| 7290001548240 | גזר חמוציות אסיאתי 2 | D01.C01 medium rule | D04.C03 high rule |
| 4770583219194 | כרוב עם חמוציות 880 | D01.C01 high rule | D04.C03 high rule |
| 7290020900593 | כרוב עם חמוציות מאמו | D01.C01 high rule | D04.C03 high rule |
| 7290004944056 | חציל במיונז אסלי 400 גרם | D04.C05 low ai | D04.C03 high rule |
| 8190010296547 | כרוב חמוציות 500 גר | D01.C01 high rule | D04.C03 high rule |
| 7290018704547 | כרוב אדום במיונז בית | D01.C01 high rule | D04.C03 high rule |

## F11: טאפס is never fresh produce; טאפס פלפל = cheese-stuffed peppers

- `D01` negative_keywords add: `טאפס`
- `D02.C02` keywords add: `טאפס+פלפל*`

Changed 3 (category 3); confidence before {'high': 3}, after {'high': 3}.
Department moves: D01->D02: 3

| item_code | name | before | after |
|---|---|---|---|
| 7290002244004 | טאפס פלפל חלפניו | D01.C01 high rule | D02.C02 high rule |
| 7290002244103 | טאפס פלפל כתום | D01.C01 high rule | D02.C02 high rule |
| 7290002244059 | טאפס פלפל אדום | D01.C01 high rule | D02.C02 high rule |

## F12: a wok in a food name is not cookware

- `D15.C01` negative_keywords add: `נודלס`, `אטריות`, `אטריית`, `מוקפץ`, `מוקפצים`, `מנה חמה`

Changed 2 (category 2); confidence before {'low': 2}, after {'high': 2}.
Department moves: D07->D07: 2

| item_code | name | before | after |
|---|---|---|---|
| 7290118427605 | מנה חמה ווק נודלס ברוטב קארי ירוק 70 ג'  אסם | D07.C23 low ai | D07.C02 high rule |
| 7290118427568 | מנה חמה ווק נודלס ברוטב מוקפץ 70 גרם | D07.C23 low ai | D07.C02 high rule |

## F13: bare דובונים is Osem's salty snack; gummy bears say so

- `D08.C02` keywords remove: `דובונים`
- `D08.C02` keywords add: `דובונים+גומי,ג'לי,סוכריות,סוכ,מסוכר*,מוברק*,מרשמלו,הריבו,פירות,בטעמי`
- `D08.C05` keywords add: `דובונים`
- `D08.C05` negative_keywords add: `דובונים+גומי,ג'לי,סוכריות,סוכ,מסוכר*,מוברק*,מרשמלו,הריבו,פירות,בטעמי`

Changed 12 (category 8); confidence before {'low': 6, 'high': 6}, after {'low': 3, 'high': 8, 'medium': 1}.
Department moves: D08->D08: 8

| item_code | name | before | after |
|---|---|---|---|
| 25675060951 | טיני טדי דובונים שוקולד | D08.C02 high rule | D08.C05 low rule |
| 7290104504228 | מארז דובונים 5*20 גר | D08.C02 high rule | D08.C05 high rule |
| 7290113198579 | סוכריותגומי דובונים 150 גרם | D08.C02 high gs1 | D08.C02 medium gs1 |
| 7290106572652 | 40 גר גן חיות דובונים | D08.C02 high rule | D08.C05 low rule |
| 7290000066264 | דובונים 40 ג' אסם | D08.C02 high rule | D08.C05 high rule |
| 7290118424048 | דובונים כוכבים 40 גר | D08.C02 high rule | D08.C05 high rule |
| 7290122781533 | חטיף דובונים בטעם ביסלי ברביקיו, 40 גרם | D08.C05.S01 low ai | D08.C05 high rule |
| 25675013254 | טיני טדי דובונים דבש פשק | D08.C02 low rule | D08.C05 low rule |
| 7290000062242 | חטיף דובונים בטעם שמנת בצל | D08.C05.S02 low ai | D08.C05.S02 high ai |
| 7290118423966 | דובונים לבבות 40 גרם | D08.C05.S03 low ai | D08.C05.S03 high ai |
| 7290106572614 | דובונים 40 גרם פיצה | D08.C02 low rule | D08.C05.S02 high ai |
| 25675845701 | ג'לי דובונים-קופסא כשל"פ | D08.C02 low ai | D08.C02 high rule |

## F14: cultured soy (סויה ביו) is a yogurt; a dessert name is not a drink

- `D02.C03` keywords add: `סויה ביו`, `ביו סויה`, `יוגורט סויה`, `מעדן סויה+ביו*`
- `D02.C04` negative_keywords add: `מעדן סויה+ביו*`
- `D07.C10` negative_keywords add: `מעדן*`, `יוגורט*`
- `D02.C01` negative_keywords replace: `מעדן` -> `!מעדן`

Changed 9 (category 7); confidence before {'low': 2, 'medium': 2, 'high': 5}, after {'high': 8, 'low': 1}.
Department moves: D02->D02: 6; D07->D02: 1

| item_code | name | before | after |
|---|---|---|---|
| 7290110329846 | מעדן סויה ביו טבעי | D02.C01.S03 high ai | D02.C03 high rule |
| 7290110328061 | מעדן גו סויה מועשר ב | D02.C04 medium rule | D02.C04 high rule |
| 7290110328054 | מעדן גו סויה מועשר ב | D02.C04 medium rule | D02.C04 high rule |
| 7290014763401 | יוגורט סויה לשתיה אפ | D02.C01.S03 low ai | D02.C03 high rule |
| 7290110329792 | מעדן סויה ביו אפרסק | D02.C01.S03 high ai | D02.C03 high rule |
| 7290110329815 | מעדן סויה ביו מתיקות מעודנת | D02.C01.S03 high ai | D02.C03 high rule |
| 7290116932101 | מעדן סויה GO בטעם אגוזי לוז 150 גרם, 12 גרם חלבון | D02.C01.S03 high ai | D02.C04 high rule |
| 8019428009139 | מעדן סויה אורגני וני | D02.C01.S03 low ai | D02.C04 high rule |
| 7290110329822 | מעדן סויה ביו פירות יער | D07.C20 high rule | D02.C03 low rule |

## Rejected after measurement (not in v1.1)

- **GS1 obeys every negative keyword:** 551 changes. Many were wrong: butter spreads moved to salads by the
  negative ממרח, and flavoured instant coffee became unclassified. Negatives were written to stop false keyword hits, not to
  overrule GS1. Kept only as explicit hard negatives (`!רסק` on fresh fruit, `!מעדן` on milk drinks).
- **Department-only GS1 rows (Drinks Flavoured -> D09) no longer raise a rule to high:** 899 labels high ->
  medium, nearly all of them correct. The flavoured-water error it targeted is fixed by F3 instead.
  The GS1 group "Drinks Flavoured - Ready to Drink" is not mapped to still drinks: it also holds Pepsi,
  7up, Mirinda and other carbonated drinks (more than 100 of its 280 items).
