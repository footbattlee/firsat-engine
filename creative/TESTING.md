## Windows test

After checking out this branch:

```bat
C:\firsat-engine\.venv\Scripts\python.exe -m pip install -r requirements.txt
creative\run_stanley_test.bat
```

Expected: `SMOKE TEST OK` and `creative_output\stanley_smoke_test.png`.

Then test live Supabase data:

```bat
creative\run_live_test.bat
```

Expected: `CREATIVE OK` and a `deal_<uuid>_1080x1350.png` file. The live runner chooses the current candidate with the highest `gap_percent` unless `--candidate-id` is supplied through the Python CLI.
