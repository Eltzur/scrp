# SU11A-56 taxonomy v1.2 (Dude's P1-P4) and the Sonnet 5.5 pilot

Read-only local export of 24 Oct 2026 (131,225 live non-pseudo items). Each change is applied in order and
diffed against the previous step (rules + GS1 + the existing AI labels, combined as the import does).
S0 = v1.1 and reproduces the SU11A-55 labels exactly (0 differences).

| Step | high | medium | low | unclassified | changed | category changed |
|---|---:|---:|---:|---:|---:|---:|
| S0 | 108,660 | 7,126 | 13,286 | 2,153 | - | - |
| P1 | 108,546 | 7,239 | 13,287 | 2,153 | 306 | 271 |
| P2 | 108,545 | 7,239 | 13,288 | 2,153 | 56 | 55 |
| P3 | 108,525 | 7,282 | 13,265 | 2,153 | 621 | 621 |
| P4 | 108,525 | 7,282 | 13,265 | 2,153 | 0 | 0 |

## P1: still soft drinks: new D09.C11; flavoured water and still fruit drinks move there

Changed 306 (category 271); confidence before {'high': 280, 'medium': 18, 'low': 8}, after {'high': 166, 'medium': 131, 'low': 9}.
Department moves: D09->D09: 257; D06->D09: 6; D08->D09: 4; D04->D09: 1; D02->D09: 1; D05->D09: 1; D09->D07: 1

| item_code | name | before | after |
|---|---|---|---|
| 8001620015629 | משקה פירות פרוטה בטעם תפוז ותפוז אדום 400 מ"ל 12 יח | D09.C04 high gs1 | D09.C11 high gs1 |
| 9551011820138 | משקה  בטעם תפוח 325 מ"ל וידה | D09.C04 high rule | D09.C11 medium rule |
| 337 | כרטיס כניסה לאיי ג'אמפ | D09.C04 medium rule | D09.C11 medium rule |
| 7290018925072 | פרימור משקה קל לימונ | D09.C04 high rule | D09.C04 medium rule |
| 7290018925102 | פרימור משקה קל ענבים | D09.C04 high rule | D09.C04 medium rule |
| 7290019056249 | שוופס מים בטעמים ענבים 1.5 ל' | D09.C01 high gs1 | D09.C11 high gs1 |
| 8850389115336 | סאפה משקה אלוורה בטעם מלון | D09.C04 high gs1 | D09.C11 medium gs1 |
| 7290001594377 | משקה קל תפוזים פריגת 500 מ"ל | D09.C04 high rule | D09.C11 medium rule |
| 7290019056485 | ספרינג תה תה ירוק לימון לואיזה 1.5 ליטר | D09.C04 high gs1 | D09.C11 high gs1 |
| 7290000136516 | ג'אמפ מנגו-פסיפלורה 1.5 ליטר | D09.C04 high gs1 | D09.C11 high gs1 |
| 8850389105849 | סאפה משקה אלוורה מופחת קלוריות בטעם אפרסק 1 ליטר | D09.C04 high gs1 | D09.C11 medium gs1 |
| 7290017023823 | ספרינג תות בננה 250 מל רביעייה | D09.C04 high gs1 | D09.C11 high gs1 |
| 7290017023977 | ספרינג תות בננה 250 מ"ל | D09.C04 high rule | D09.C11 high rule |
| 4770569915607 | משקה קל פירות 2 ל elmenhorster | D09.C04 high rule | D09.C11 medium rule |
| 7290019056423 | תפוזינה משקה תפוחים 1.5 ל' | D09.C04 high gs1 | D09.C11 medium rule |
| 7290019056256 | שוופס מים בטעמים תפוח 1.5 ל' | D09.C01 high gs1 | D09.C11 high gs1 |
| 7290020209368 | ספרינג ויולט&קרים 75מל | D09.C04 high rule | D09.C11 high rule |
| 7290016006292 | ספרינג מנגו בננה מלון1ל | D09.C04 high rule | D09.C11 high rule |
| 7290018925140 | משקה קל אשכוליות 1.5 ליטר | D09.C04 high rule | D09.C11 medium rule |
| 8850389118870 | מוגו מוגו מצר גפן מתוק עם חתיכות ג'לי קוקוס | D09.C03 medium ai | D09.C11 high gs1 |

## P2: newspapers and magazines: new D16.C08, out of D16.C07

Changed 56 (category 55); confidence before {'high': 55, 'medium': 1}, after {'high': 54, 'low': 1, 'medium': 1}.
Department moves: D16->D16: 55

| item_code | name | before | after |
|---|---|---|---|
| 724133975577 | עיתון הדרך | D16.C07 high rule | D16.C08 high rule |
| 9771565051059 | עיתון ידיעות חג יום | D16.C07 high rule | D16.C08 high rule |
| 679723456007 | עיתון הדרך 459 | D16.C07 high rule | D16.C08 high rule |
| 9771565038340 | עיתון ידיעות יום ד | D16.C07 high rule | D16.C08 high rule |
| 9789655203547 | עיתון חצרות | D16.C07 high rule | D16.C08 high rule |
| 9771565038326 | עיתון ידיעות יום ב | D16.C07 high rule | D16.C08 high rule |
| 9779771752432 | עיתון בינה שבועות/ר"ה | D16.C07 high rule | D16.C08 high rule |
| 9771565039118 | עיתון לאישה יום א | D16.C07 high rule | D16.C08 high rule |
| 679723456014 | עיתון הדרך גיליון 460 | D16.C07 high rule | D16.C08 high rule |
| 724133975508 | עיתון הדרך | D16.C07 high rule | D16.C08 high rule |
| 724133975546 | עיתון הדרך | D16.C07 high rule | D16.C08 high rule |
| 9779771752258 | עיתון בינה | D16.C07 high rule | D16.C08 high rule |
| 90 | עיתון לאשה | D16.C07 high rule | D16.C08 high rule |
| 9779771752265 | עיתון בינה סוכות | D16.C07 high rule | D16.C08 high rule |
| 9771565051028 | עיתון ידיעות כפול יו | D16.C07 high rule | D16.C08 high rule |
| 9789655203523 | שבועון במה | D16.C07 high rule | D16.C08 high rule |
| 9789655203462 | עיתון רגע לחג | D16.C07 high rule | D16.C08 high rule |
| 9771565038333 | ידיעות אחרונות יום ג | D16.C07 high ai | D16.C08 high rule |
| 7290015678797 | עיתון משפחה אנגלית סוכות | D16.C07 high rule | D16.C08 high rule |
| 7290005816901 | עיתון הדרך | D16.C07 high rule | D16.C08 high rule |

## P3: shelf-stable pickles and olives: new D07.C08.S01 by storage evidence

Changed 621 (category 621); confidence before {'medium': 14, 'high': 522, 'low': 85}, after {'medium': 57, 'high': 502, 'low': 62}.
Department moves: D04->D07: 602; D07->D07: 19

| item_code | name | before | after |
|---|---|---|---|
| 7290018023884 | זיתים ממולאים בשום זכוכית 500 גרם-יחידה | D04.C05 high rule | D07.C08.S01 high rule |
| 5201306803455 | זיתים ירוקים 465 גר | D04.C05 high rule | D07.C08.S01 high rule |
| 8906118240739 | קורנישונים מוחמצים ע | D04.C05 high rule | D07.C08.S01 high rule |
| 7290117268643 | מלפפונים כבושים במי מלח 700/400 גרם SERA )12( | D04.C05 high gs1 | D07.C08.S01 medium gs1 |
| 8410134026104 | זיתים ירוקים כבושים 420 גר FRAGATA | D04.C05 high rule | D07.C08.S01 high rule |
| 3592860018037 | מלפפון חמוץ דקים - ב | D04.C05 high rule | D07.C08.S01 high rule |
| 4607029054180 | פלפל ירוק פרוס כבוש | D04.C05 high rule | D07.C08.S01 high rule |
| 6901489340264 | פטריות כבושות גרוזדי | D04.C05 low ai | D07.C08.S01 low ai |
| 7290002057437 | שיפקונית  560 ג' יבנה | D04.C05 high gs1 | D07.C08.S01 high gs1 |
| 7290113192577 | כרוב כבוש בית השיטה | D04.C05 high rule | D07.C08.S01 high rule |
| 8690777202015 | ירקות כבושים מעורבים | D04.C05 high rule | D07.C08.S01 high rule |
| 7290002057345 | מלפפון במלח ‏36‏-‏30‏ ‏10‏A‏ יבנה | D04.C05 high gs1 | D07.C08.S01 medium gs1 |
| 7290020244857 | פלפלים ירוקים פיקנטי תומר 540 גרם | D04.C05 high gs1 | D07.C08.S01 high gs1 |
| 7290115413267 | טבעות פלפל חריף 250 גרם | D04.C05 low ai | D07.C08.S01 low ai |
| 7290002317142 | מלפפון במלח 18-25 A2 מוטולה | D04.C05 high rule | D07.C08.S01 high rule |
| 77975088234 | סניידרס חלפיניו 340 | D04.C05 high rule | D07.C08.S01 high rule |
| 7290019333395 | מלפפונים במלח קורנישון 75-95 בית השיטה 320 גרם | D04.C05 high rule | D07.C08.S01 high rule |
| 6253505512545 | חצילים כבושים 600 ג' זיתא | D04.C05 high rule | D07.C08.S01 high rule |
| 7290002057628 | טבעות מושחר ‏2‏-‏A‏ יבנה | D04.C05 high gs1 | D07.C08.S01 high gs1 |
| 7290018946275 | מיקס חמוצים 600 גרם | D04.C05 high rule | D07.C08.S01 high rule |

## P4: no dragée sub-type; dragées are chocolate (D08.C01), never frozen fruit

No change on the export: dragées were already D08.C01 (SU11A-55 F5). The new negatives only stop a future dragée from matching frozen fruit. Frozen chocolate-coated fruit (פטל קפוא מצופה שוקולד ...) stays in D06.C02 - open question for Dude.

## P3 split, both ways (v1.2 final labels)

**shelf-stable (D07.C08.S01): 621 items.** 20 samples:

| item_code | name | weighed | source / confidence |
|---|---|---|---|
| 7290002845287 | זיתים ירוקים טבעות  560 ג' תמי | 0 | rule / high |
| 9002859046346 | עגבניות מיובשות בשמן 280 גר פיאצלי | 0 | rule / high |
| 5901008990292 | סלט כרוב וגזר כבוש 900 גרם Polan | 0 | ai / low |
| 7290020244895 | פלפלים ארוכים ירוקים חריף תומר 295 גרם | 0 | gs1 / high |
| 7290019333692 | קוקטיל זיתים 340 ג ר | 0 | rule / high |
| 7290018770283 | זית סורי בטעם לימון 215 גר` | 0 | rule / high |
| 7290015569293 | עגבניות מיובשות 250 גרם לחיץ | 0 | rule / high |
| 8436024294750 | זיתים שחורים מגולעני | 0 | rule / high |
| 8410134002580 | זיתים ירוקים עם טונה | 0 | rule / high |
| 8690777202015 | ירקות כבושים מעורבים | 0 | rule / high |
| 7290018554616 | כרוב כבוש 430גר | 0 | rule / high |
| 5202429109387 | זיתים ירוקים 400 גר | 0 | rule / high |
| 7290016995473 | אגבה כחול 660 מ"ל | 0 | gs1 / medium |
| 7290002845102 | חצילים כבושים 580 גרם | 0 | rule / high |
| 4607044609532 | זנגביל כבוש 190 גר | 0 | rule / high |
| 7290018770276 | זית עריביקה עם שמן זית 215 גר` | 0 | ai / high |
| 5904603191323 | מלפפונים כבושים | 0 | rule / high |
| 852852004008 | מלפפון במלח 18-25 54 | 0 | rule / high |
| 8722700202325 | קורנישון מלפפונים אקסטרא מיני 400 גרם | 0 | gs1 / high |
| 7290002317302 | זיתים ירוק מבוקע A2 מוטולה | 0 | rule / high |

**deli / refrigerated / weighed (D04.C05): 534 items.** 20 samples:

| item_code | name | weighed | source / confidence |
|---|---|---|---|
| 7290018554012 | מלפפונים בחומץ 7-9 ר | 0 | rule / high |
| 7290001970324 | זית סורי במשקל | 1 | rule / high |
| 7290019934615 | זית קלמטה עם גלעין 3 | 0 | rule / high |
| 7290009077681 | זית קוקטייל צרפתי | 1 | rule / high |
| 7290113192522 | מלפפון בחומץ 18-25 2 | 0 | rule / high |
| 7290018023174 | זיתים סורים שבורים 2 | 0 | rule / high |
| 7290002317562 | זיתים טבעי | 0 | rule / high |
| 4433 | חמוצים | 1 | rule / high |
| 7290000029184 | מלפפון חמוץ ביתי | 1 | rule / high |
| 7290012212277 | מלפפון במלח 10-12 | - | rule / high |
| 7290016440928 | ירקות כבושים חמוץ מת | 0 | rule / high |
| 6182 | זית ירוק ממולא שום | 1 | rule / high |
| 475091 | זיתים/חמוצים טורשי | 1 | ai / high |
| 19024 | זית חרוזית ירוק (ח) | 1 | rule / high |
| 7290009077650 | זית יווני במשקל | 1 | rule / high |
| 7290004981273 | חמוצים ב-6.90ל100 גר | 1 | rule / high |
| 7290000935423 | עגבניות מיובשות | 1 | rule / high |
| 7296073726098 | זיתים ירוקים שלמים A2 56 | 0 | rule / high |
| 6951 | זיתים ירוקים עם חריף | 1 | rule / high |
| 7290000022932 | זית ירוק ושום | 1 | rule / high |

Storage evidence (`classify_rules.storage_of`): deli = weighed row or store code of 7 digits or fewer, שקיל / במשקל / לפי משקל / לק"ג / תפזורת / מעדנייה / דלי / טרי, salad brands (ברדה, שמיר, צבר, אחלה, סלטי). Shelf = a pack size with a unit, an imported GTIN (8+ digits not 729), צנצנת / פחית / פח / קופסה / שימורי / משומר, shelf brands (יכין, פרי הגליל, גפן, ויליפוד, זיתא, זאדונא, ולאסיק, יבנה, בית השיטה, מוטולה, דון פרננדו, איליאדה, סבא חביב, ביכורי השדה). Deli wins; no evidence = deli. The count grade (13-17) is not used. Of the 534 items left in D04.C05, 269 have deli evidence and 265 have none (mostly truncated names of packaged Israeli items whose size was cut off); they stay deli by default and are the place to look if the split should go further.

## Sonnet 5.5 pilot (100 graded AI-only items, thinking off = `between_tools`, taxonomy v1.2)

Exact id against Dude's grade. Buckets = the confidence column of the audit sample.

| | all | high | medium | low |
|---|---|---|---|---|
| Haiku (existing labels) | 64/100 = 64% | 28/34 = 82% | 21/33 = 64% | 15/33 = 45% |
| Sonnet 5.5 | 53/100 = 53% | 21/34 = 62% | 13/33 = 39% | 19/33 = 58% |
| Sonnet where it disagrees with Haiku | 16/58 = 28% | 0/9 = 0% | 5/25 = 20% | 11/24 = 46% |
| Haiku on those same rows | 27/58 = 47% | 7/9 = 78% | 13/25 = 52% | 7/24 = 29% |
| Haiku, category level | 64/100 = 64% | 28/34 = 82% | 21/33 = 64% | 15/33 = 45% |
| Sonnet, category level | 59/100 = 59% | 24/34 = 71% | 15/33 = 45% | 20/33 = 61% |

Cost: 2 requests, $0.07 (3,728 input + 9,573 cache write + 9,573 cache read + 4,024 output tokens).
Gate (Sonnet >= Haiku + 10 points overall and not worse on high): **failed** (53% vs 64%; high 62% vs 82%). The full re-check was not run; ai_labels_v1.csv stays the AI source.

| row | bucket | name | grade | Haiku | Sonnet |
|---|---|---|---|---|---|
| 3 | high | מור ק.לחות שיער נערה750מ | D12.C03 | D12.C01 | D12.C01 (medium) |
| 7 | high | לואקר מקסי אגוזי לוז פרווה | D08.C06 | D08.C06 | D08.C07 (medium) |
| 12 | high | דיספלין תחליב לשיער | D12.C03 | D12.C03 | D12.C01 (medium) |
| 13 | high | בפלות בטעם שוקולד 200 גרם. | D08.C06 | D08.C06 | D08.C07 (high) |
| 15 | high | גריל עוף | D07.C14 | D03.C06 | D03.C06 (medium) |
| 19 | high | אדיר כרם בן זמרה שנין בלאן 750 מל | D10.C01.S01 | D10.C01.S01 | D10.C01.S02 (high) |
| 21 | high | ויצינה סבינייה חזיר כפרית במשקל | D04.C01.S01 | D04.C01.S01 | D04.C01.S03 (medium) |
| 24 | high | מגן קריסטל 2 ליטר | D11.C03 | D09.C02 | D11.C04 (medium) |
| 26 | high | נטורטינט תחליב לטיפול טיפוח וחיזוק שיער | D12.C03 | D12.C01 | D12.C01 (medium) |
| 31 | high | שפק מעושן גוש בואקום | D04.C01.S01 | D04.C04 | D04.C01.S03 (medium) |
| 32 | high | חומוס מקסיקו גדול | D07.C05 | D04.C02 | D04.C02 (medium) |
| 34 | high | כדוריות הבושם בניחוח אריאל 210 ג' לנור | D11.C03 | D11.C03 | D11.C01.S03 (medium) |
| 35 | high | גולד פלוס עם HMO5 שלב3 700גר סימילאק | D13.C04 | D13.C04 | D13.C03 (high) |
| 36 | medium | 200+15% תוספת | D09.C08.S04 | D09.C08.S04 | D09.C08.S01 (low) |
| 37 | medium | אפנזלר לבן במשקל | D02.C02.S01 | D07.C11 | D02.C02.S02 (low) |
| 38 | medium | לבלו טיפוח יופי ורוד | D12.C07 | D12.C07 | D12.C06 (medium) |
| 41 | medium | מטרית מותגים מטוסים - איכותית | D16.C04 | D16.C04 | D16.C03 (medium) |
| 42 | medium | סטרונגר וויט יו 100 מ"ל | D12.C14 | D12.C05 | D12.C09 (medium) |
| 43 | medium | גרוס TINYS משפחתי אבטיח | D08.C02 | D08.C02 | D13.C01 (medium) |
| 44 | medium | סט 8 חותכי עגיות פלו | D15.C03 | D15.C03 | D15.C02 (high) |
| 45 | medium | עגלת שירות צרה 3 קומ | D15.C04 | D15.C04 | D15.C11 (medium) |
| 46 | medium | בורקיטס בונז'ור 1 ק"ג | D06.C04 | D08.C05.S01 | D06.C04 (high) |
| 47 | medium | להבונים 50 יח' 3 שעו | D16.C06 | D16.C05 | D16.C06 (high) |
| 49 | medium | מנגו  מסוכר | D01.C05 | D01.C04 | D01.C05 (medium) |
| 50 | medium | טרנצטו שמיניות 200 ג | D05.C05 | D05.C05 | D08.C05.S03 (low) |
| 51 | medium | סט שירותים ידית עץ | D11.C04 | D11.C04 | D15.C11 (medium) |
| 52 | medium | נאטי ציוז משפחתי 283 | D08.C01 | D06.C07 | D07.C22 (medium) |
| 53 | medium | בודי ספלאש ביזו 180 מ"ל | D12.C14 | D12.C14 | D12.C07 (medium) |
| 56 | medium | ידית טלסקופית נפתח ל1.5מ | D15.C12 | D15.C12 | D11.C07 (medium) |
| 57 | medium | מרינה ג'ינג'ר במגשית 200 גרם | D01.C01 | D04.C03 | D07.C08.S01 (medium) |
| 58 | medium | סינימיניס צ'ורוס 360 | D07.C22 | D08.C06 | D07.C22 (medium) |
| 59 | medium | משולש אקרילי | D16.C07 | D16.C07 | D16.C06 (low) |
| 60 | medium | קוקוס במשקל לפי משקל | D01.C04 | D01.C04 | D08.C09 (low) |
| 61 | medium | פופ טארטס אכמניות | D08.C06 | D08.C06 | D07.C22 (low) |
| 62 | medium | ויניס קראנצ' מארז זהב5יח | D08.C01 | D08.C05 | D08.C07 (medium) |
| 63 | medium | פטרוצאן מצונן מזרע 7 | D04.C01.S02 | D01.C02 | D01.C03 (medium) |
| 64 | medium | ליפתניות צבע  25 יח | D11.C10 | D16.C07 | D12.C02 (low) |
| 66 | medium | מוגו מוגו ליצ'י עם חתיכות ג'לי קוקוס 1ל | D09.C11 | D09.C03.S02 | D09.C11 (high) |
| 69 | low | פטאקי 16% שומרון | D02.C02.S01 | D03.C06 | D07.C14 (low) |
| 70 | low | צ. נוגה אפור פס זהב10+10 | D11.C10 | D16.C01 | D12.C09 (low) |
| 71 | low | משחת נעליים אריסטוקר | D16.C02 | D12.C07 | D16.C02 (medium) |
| 73 | low | משקה מוגז בטעם פטל 5 | D09.C03.S02 | D09.C02 | D09.C03.S02 (high) |
| 74 | low | מייב אינק וויניל ניוד145 | D12.C12 | D16.C07 | D12.C13 (low) |
| 75 | low | פארו סרט דנטלי 1762 | D12.C09 | D12.C15 | D12.C09 (high) |
| 76 | low | קליק ביסקויט 65 ג' | D08.C01.S02 | D08.C06 | D08.C06 (medium) |
| 77 | low | פריכיות דגנים בטעם אוכמניות 100 גרם | D08.C10 | D08.C10 | D08.C08 (high) |
| 78 | low | מפות שולחן ניילון 18 יח | D11.C10 | D16.C05 | D11.C10 (high) |
| 80 | low | מועך תפוח אדמה נירוסטה סטיל | D15.C03 | D15.C01 | D15.C03 (high) |
| 81 | low | גליל מפת שולחן צלופן | D11.C10 | D11.C11 | D11.C10 (medium) |
| 82 | low | מארז 2 יח' עצם קשר 8 אינץ 180 ג' GOODY | D14.C01 | D16.C04 | D12.C03 (medium) |
| 83 | low | דאב סטיק פרש מלפפונים 40 גרם | D12.C05 | D12.C07 | D12.C05 (high) |
| 85 | low | קברט 4 חן BAMBOO | D15.C04 | D15.C04 | D15.C03 (low) |
| 86 | low | אהיל לד לסוכה | D15.C07 | D15.C07 | D16.C06 (medium) |
| 87 | low | מפות ניילון שקופות 8 יח' | D11.C10 | D16.C05 | D11.C10 (high) |
| 88 | low | מלטיזרס 300 גרם | D08.C01.S02 | D07.C15 | D08.C01 (high) |
| 91 | low | לאור דספאור נוצה100 מ"ל | D12.C14 | D12.C07 | D12.C14 (medium) |
| 92 | low | אוזנייה עם דיבורית | D15.C08 | D11.C10 | D15.C08 (high) |
| 93 | low | חוות תקוע לקט פטריות מיובשות למרק 25 גרם | D07.C16 | D07.C16 | D07.C14 (low) |
| 95 | low | פנסי פיסט סלמון וסול 85ג | D07.C07 | D07.C07 | D14.C02 (high) |
| 96 | low | שניצל בקר טרי | D03.C01 | D03.C01 | D03.C02 (medium) |
| 97 | low | ציבורק מתוגן 600 גרם | D06.C04 | D11.C03 | D06.C07 (medium) |
| 98 | low | ווין וינטר 60 כמוסות | D12.C16 | D12.C15 | D12.C16 (medium) |
| 99 | low | רולר להסרת סיבים | D15.C10 | D15.C10 | D15.C11 (high) |
