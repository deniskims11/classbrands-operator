# Class Brands Operator

Operator dashboard across Class Brands clients (Haritaki, Natural Rems, Blushe, Seora): business numbers per shop plus spend on our tagged creatives, pace to target and fees.

- **Data:** Triple Whale SQL API, every ~3 hours via GitHub Actions (`scripts/fetch_tw.py` → `scripts/build.py` → `scripts/encrypt_data.py`). Nothing is committed; only the encrypted `data/latest.json` is published.
- **Secrets:** `TW_API_KEYS` (JSON `{client key: Triple Whale key}`, one per shop; `TW_API_KEY` is an optional fallback), `DASHBOARD_PASSWORD` (page password), `CBO_CONFIG` (client list: shops, tags, fee terms — kept out of this public repo).
- **Local preview:** put the config in `config.json` (gitignored), then `python3 scripts/make_sample.py && python3 scripts/build.py` (sample data) or `TW_API_KEY=… python3 scripts/fetch_tw.py && python3 scripts/build.py` (real data), and serve `public/`.
