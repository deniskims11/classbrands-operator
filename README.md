# Class Brands Operator

Operator dashboard across Class Brands clients (Haritaki, Natural Rems, Blushe, Seora): Meta spend and Meta-reported performance per client, plus spend on our tagged creatives, pace to target and fees.

- **Data:** Triple Whale SQL API, every ~3 hours via GitHub Actions (`scripts/fetch_tw.py` → `scripts/build.py` → `scripts/encrypt_data.py`). Nothing is committed; only the encrypted `data/latest.json` is published.
- **Secrets:** `TW_API_KEYS` (JSON `{client key: Triple Whale key}`, one per shop; `TW_API_KEY` is an optional fallback), `DASHBOARD_PASSWORD` (page password), `CBO_CONFIG` (client list: shops, tags, fee terms — kept out of this public repo).
- **Local preview:** put the config in `config.json` (gitignored), then `python3 scripts/make_sample.py && python3 scripts/build.py` (sample data) or `TW_API_KEY=… python3 scripts/fetch_tw.py && python3 scripts/build.py` (real data), and serve `public/`.
- **Full brand dashboards:** `scripts/brand_data.py` (data, one file per brand, ad-name parsing in `scripts/brand_names.py`) + `brand/` (the React app, built once and copied to `public/b/<client key>/`). Same password as the operator page. A client with `dashboard_url` in the config links to its own site instead.
