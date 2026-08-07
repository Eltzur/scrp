# Promo recon fixtures (SU10A-7)

Raw promo XML samples preserved from the SU10A-5 / SU10A-7 recon work.

**All captures in this directory are Aug-2 2026 vintage (SU10A-5-era).** None of them
post-dates the King Store flat→standard migration handled in SU10A-7. Read every file
below as a *pre-migration* snapshot unless stated otherwise.

## Files

| File | Shape | Size | Notes |
|---|---|---|---|
| `Bina_King_Promo_001.xml` | flat | 5 KB | King Store **PRE-migration flat delta**. The "before" side of the flat→standard migration — **irreplaceable** once the portal finishes rolling over. |
| `Bina_King_PromoFull_001.xml` | flat | 1.7 MB | King Store **PRE-migration flat full snapshot**. Same irreplaceable "before" side, full catalogue. |
| `HaziHinam_201.xml` | flat | 25 KB | Clean, well-formed flat capture (12 promotions / 51 items). **NOT the corrupt store-201 file from the SU10A-7 recon** — see below. |
| `Shufersal_001.xml` | standard | 30 KB | Standard-variant reference. |
| `Carrefour_002.xml` | standard | 224 KB | Standard-variant, PublishPrice portal. |

## What is deliberately NOT here

**Rami Levy (7 MB) and Victory (4.2 MB) standard feeds were excluded on purpose** —
regenerable current-shape data, too heavy to carry in the repo. `Shufersal_001.xml`
covers the standard-variant reference at 30 KB.

**The corrupt store-201 Hazi Hinam file is not preserved.** That was a separate, later
capture with mismatched `Groups` / `PromotionItems` tags on which *both* parsers error —
the file that SU10A-7 classifies as corruption rather than a schema migration. It was
transient and has since been overwritten. The `HaziHinam_201.xml` in this directory is a
clean earlier capture of the same store and must not be mistaken for it.

**A post-migration King Store standard-shape file is not preserved either** — that shape
is now the chain's default output and can be re-fetched at any time.

Both of those are the evidence behind the SU10A-7 findings; neither is kept here, for the
opposite reasons (the first is gone, the second is always available).
