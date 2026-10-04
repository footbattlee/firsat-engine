# Firsat Engine

Turkey-focused price comparison and deal discovery across Amazon, Trendyol,
Hepsiburada, n11, MediaMarkt and Vatan.

The pipeline discovers campaign products independently of the category list,
searches other stores for the same products, runs the ordinary category scans,
matches products, refreshes competitor offers, evaluates deals and sends new
candidate cards to the Telegram admin chat. Both collector pools default to
three workers. Previously sent cards are skipped unless a qualifying new price
drop reopens them.

## Install on another Windows computer

Install Git and Python 3.11 or newer. In PowerShell:

```powershell
git clone --branch feature/creative-generator https://github.com/footbattlee/firsat-engine.git
cd firsat-engine
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
notepad .env
```

Set SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TELEGRAM_BOT_TOKEN and
TELEGRAM_APPROVAL_CHAT_ID in the local .env file. Obtain the values separately
from the existing machine/account; GitHub contains no credentials. Existing
Windows environment variables override .env values.

Start a full scan and watch the output:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
New-Item -ItemType Directory -Force logs | Out-Null
$scanLog = "logs\pipeline_$(Get-Date -Format yyyyMMdd_HHmmss).log"
.\.venv\Scripts\python.exe run_pipeline.py 2>&1 | Tee-Object -FilePath $scanLog
```

Alternatively, run `.\run_firsat_engine.bat`; it writes a log under logs and uses
the .venv next to the script, regardless of the installation directory.

For an existing checkout of this branch, stop its scan before updating and use
`git pull --ff-only`, then reinstall requirements and Chromium if needed.
Preserve any local changes reported by `git status`; do not reset them to update.
Avoid overlapping full scans from two PCs against the same database.

## Cloud publications

Scans from either computer feed the same Supabase database and durable queue.
The already deployed cloud worker runs independently of both PCs, with one
Instagram post per half hour between 10:00 and 23:30 Europe/Istanbul. A successful
post is followed by a Telegram story document/link. Reels remain manually
selected in the admin chat.

Only completed scans within the configured source boundary are eligible. Posts
use the completed scan's stored prices; publication does not recheck storefront
access or stock. Details: [PUBLICATION_QUEUE.md](PUBLICATION_QUEUE.md) and
[collectors/DEAL_DISCOVERY.md](collectors/DEAL_DISCOVERY.md).

Cloning the repo does not redeploy cloud functions or change the cloud schedule.
The checked-in SQL is deployment/reference material; do not rerun the dated
scan-boundary SQL just to install the collector on another PC.

## Tests

Python tests are offline unit/integration fixtures; they do not launch a full
store scan or publish posts. Install pytest if needed and run:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
```

Cloud helper tests require a Node version supporting native TypeScript (for
example the Node 24 runtime used for validation):

```powershell
node --test tests/cloud_queue.test.ts
```

Credentials, virtual environments, generated creatives, scan logs and generated
competitor-search reports are excluded from Git.
