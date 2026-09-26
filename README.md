# NYC Heat & Mind

Heat risk and mental distress overlap across NYC neighborhoods. The overlap largely tracks income and racial composition. Street trees show no measurable link.

## What it shows

A neighborhood map of heat vulnerability, frequent mental distress, depression and street-tree density (2015) across New York City's 197 residential neighborhoods.

Spearman correlations across the 197 residential neighborhoods (heat risk is the city's Heat Vulnerability Index rank; distress is the PLACES estimate of frequent mental distress):

1. Heat risk vs distress, unadjusted: ρ = 0.73, p = 1.97 × 10⁻³³
2. Adjusted for median income: ρ = 0.41, p = 2.20 × 10⁻⁹
3. Adjusted for income and racial composition: ρ = 0.13, p = 0.0797 (not statistically significant at 0.05)
4. Street trees per km² (2015) vs distress: ρ = -0.07, p = 0.352

Racial composition is percent Black population, an HVI input and one of the variables the [PLACES models](https://www.cdc.gov/places/methodology/index.html) can draw on. It is used only for this adjustment and is not mapped.

These values are copied from `web/public/data/stats.json` as of the last pipeline run.

## Run it

Requirements: Python 3.13, Node 26 and pnpm 12.

```sh
# Pipeline: downloads public data into data/raw/, builds web/public/data/
python3 -m venv .venv
.venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python pipeline/fetch.py
.venv/bin/python pipeline/build.py

# Web app
cd web
pnpm install
pnpm dev          # local dev server
pnpm build        # production build into web/dist/
pnpm run check:private
```

`scripts/check_nta_geojson.py` checks the built neighborhood file (feature count, required properties, size under 2 MB).

## Credit

Built by Tung Nguyen (Cornell MBA). All data comes directly from the public sources below.

## Sources

| Name | Dataset id | Date | License or terms | Link |
|---|---|---|---|---|
| NYC Heat Vulnerability Index by 2020 NTA (NYC Health Department) | `hvi-nta-2020.csv` in nychealth/EHDP-data | File last changed 2023-10-21 | Apache-2.0 (repository license) | https://github.com/nychealth/EHDP-data/blob/production/key-topics/heat-vulnerability-index/hvi-nta-2020.csv |
| PLACES: Census Tract Data (GIS Friendly Format), 2025 release (CDC) | `yjkw-uj5s` | 2025 release; rows updated 2025-12-04 | Public domain | https://data.cdc.gov/d/yjkw-uj5s |
| 2020 Census Tracts to 2020 NTAs and CDTAs Equivalency (NYC Planning) | `hm78-6dwm` | Rows updated 2021-09-20 | NYC Open Data terms of use | https://data.cityofnewyork.us/d/hm78-6dwm |
| 2020 Neighborhood Tabulation Areas (NYC Planning) | `9nt8-h7nd` | Rows updated 2026-05-28 | NYC Open Data terms of use | https://data.cityofnewyork.us/d/9nt8-h7nd |
| 2015 Street Tree Census – Tree Data (NYC Parks) | `uvpi-gqnh` | Census 2015; rows updated 2017-10-04 | NYC Open Data terms of use | https://data.cityofnewyork.us/d/uvpi-gqnh |
| OpenFreeMap Positron basemap | `styles/positron` | Served live | OpenFreeMap © OpenMapTiles Data from OpenStreetMap (ODbL) | https://openfreemap.org/ |

NYC Open Data terms of use: https://opendata.cityofnewyork.us/overview/#termsofuse

## Caveats

- PLACES figures are model-based estimates. They are modeled partly from demographic data, so they share inputs with income-based measures.
- The tree data is from 2015.
- All figures are correlations across neighborhoods only.

## License

The code is MIT licensed (see `LICENSE`). Data remains under its sources' terms.
