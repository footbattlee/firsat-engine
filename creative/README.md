# Fiyatzade Creative Generator

Deterministic 1080x1350 deal-card renderer.

- Reads a current `deal_candidates` row from Supabase.
- Resolves `cheapest_offer_id -> offers.image_url` and uses the real marketplace product image.
- Prices and `gap_percent` are rendered directly from database values; generative AI is not used for product, price, or copy.
- Output is written to `creative_output/` by default.

## Run

```bat
C:\firsat-engine\.venv\Scripts\python.exe -m pip install -r requirements.txt
C:\firsat-engine\.venv\Scripts\python.exe run_creative_generator.py
```

Specific candidate:

```bat
C:\firsat-engine\.venv\Scripts\python.exe run_creative_generator.py --candidate-id <uuid>
```

Required environment variable: `SUPABASE_SERVICE_ROLE_KEY`.

This module is intentionally separate from publishing. Telegram approval/publication queue integration comes next.
