#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "1. Python version"
echo "========================================"
python --version

echo "========================================"
echo "2. Install Python dependencies"
echo "========================================"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "========================================"
echo "3. Prepare runtime data directories"
echo "========================================"
mkdir -p data/national_links
mkdir -p data/routes/od_pipeline

echo "========================================"
echo "4. Download and extract deployment assets"
echo "========================================"

python - <<'PY'
from pathlib import Path
from urllib.request import Request, urlopen
import shutil
import zipfile

ASSETS = [
    {
        "url": "https://github.com/sungbin30509-jpg/eodiga-backend/releases/download/v1.0.0/MOCT_LINK_20260812.zip",
        "zip_name": "MOCT_LINK_20260812.zip",
        "target": Path("data/national_links"),
    },
    {
        "url": "https://github.com/sungbin30509-jpg/eodiga-backend/releases/download/v1.0.0/OD_PIPELINE_600_20260812.zip",
        "zip_name": "OD_PIPELINE_600_20260812.zip",
        "target": Path("data/routes/od_pipeline"),
    },
]

tmp_dir = Path("/tmp/eodiga_assets")
tmp_dir.mkdir(parents=True, exist_ok=True)

for asset in ASSETS:
    url = asset["url"]
    zip_path = tmp_dir / asset["zip_name"]
    target = asset["target"]

    target.mkdir(parents=True, exist_ok=True)

    print(f"Downloading: {url}")

    request = Request(
        url,
        headers={
            "User-Agent": "eodiga-render-build"
        },
    )

    with urlopen(request) as response, open(zip_path, "wb") as output:
        shutil.copyfileobj(response, output)

    print(
        f"Downloaded {asset['zip_name']}: "
        f"{zip_path.stat().st_size / 1024 / 1024:.2f} MB"
    )

    print(f"Extracting to: {target}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)

    zip_path.unlink()

print("Asset extraction complete.")

moct = Path("data/national_links/MOCT_LINK.shp")

if not moct.exists():
    raise RuntimeError(
        "MOCT_LINK.shp was not found after extraction."
    )

od_files = list(
    Path("data/routes/od_pipeline").glob("*.json")
)

if not od_files:
    raise RuntimeError(
        "No OD pipeline JSON files were found after extraction."
    )

print(f"MOCT_LINK verified: {moct}")
print(f"OD pipeline JSON count: {len(od_files)}")
PY

echo "========================================"
echo "5. Build verification"
echo "========================================"

python - <<'PY'
import fastapi
import uvicorn
import pydantic
import pandas
import numpy
import pyarrow
import lightgbm
import pyproj
import shapely
import pyogrio
import requests
import yaml

print("Python dependencies: OK")

from backend.main import app

print("FastAPI import: OK")
print("App:", app.title)
PY

echo "========================================"
echo "Render build completed successfully"
echo "========================================"