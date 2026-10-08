# Manual pin tool (SU11A-19)

A local, keyboard-first page for giving every store a human-confirmed position.
Static HTML/JS, no build step. Leaflet 1.9.4 from unpkg, pinned with SRI.

## Data (never committed)
`scripts/export_pin_queue.py` writes, on the server, to `~/pin_tool_data/` (mode 700):
- `queue.csv` – one row per live physical store not yet `geo_source='manual'`, with tier
  (`unplaced`, `street`, `house_unconfirmed`, `house_confirmed`) and flags.
- `candidates.json` – same-chain shop points per store from OpenStreetMap (ODbL) and
  Overture places (CDLA-Permissive-2.0), with a suggested point where exactly one matches the
  store's street + number.

## Run
```
cd C:\xxl-archive\pin_tool
python -m http.server 8765
```
Open http://localhost:8765, load `queue.csv` and `candidates.json` with the two pickers.

## Keys
| key | action |
|---|---|
| click a candidate, then Enter | use that point (`candidate_osm` / `candidate_overture`) |
| click the map, then Enter | place a pin there (`clicked`) |
| C | confirm the existing pin (house-level stores only) |
| S | skip · B back · N next · U undo · Esc clear the selection |

Guards ask before confirming a pin more than 3 km from the city centre, outside Israel, or
within 30 m of another store of the same chain. Every action autosaves to this browser's
localStorage. **Export picks** downloads `picks_YYYYMMDD_HHMM.csv` for
`scripts/import_manual_pins.py`.

## Sources and rules
- Since 2026-10-08 (SU11A-23, Dude's decision) the Google results are the source of truth for store
  coordinates and are loaded with `scripts/import_google_coordinates.py`; OSM / Nominatim / Overture are
  retired as coordinate sources (CLAUDE.md "Store positions"). This tool is now for single fixes.
- A pin may come from an OSM / Overture candidate, a click on the map, or a Google Maps point. The raw
  Google result files stay out of the repo and docs (`~/google_compare/` on the server only).
- Every pin imported by `scripts/import_manual_pins.py` becomes `geo_source='manual'`, which no
  automated run ever overwrites (the importer does not yet set `coord_source`; the guards key on either).
- OSM tile usage policy: attribution stays visible; tiles load only for the visible map
  (`updateWhenIdle`), no prefetching or offline download; the browser's own User-Agent,
  Referer and cache are used. Keep use interactive and light.

## Tests
`node tests/pin_tool/test_pinlib.js` (the pure logic in `pinlib.js`). Set `PIN_SAMPLE_DIR` to a
folder with a 5-store `queue.csv` + `candidates.json` to include a real-data check.
