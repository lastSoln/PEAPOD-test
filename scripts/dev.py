"""Local dev server: no password, a throwaway bench file. Not for deployment.

    python scripts/dev.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
env_file = ROOT / ".env"                      # optional: KEY=value lines, e.g. PEAPOD_PLACES_URL
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
os.environ.setdefault("BENCH_NO_AUTH", "1")
os.environ.setdefault("BENCH_DB", str(ROOT / "bench.dev.sqlite"))

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
