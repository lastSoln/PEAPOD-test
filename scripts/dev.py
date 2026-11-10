"""Local dev server: no password, a throwaway bench file. Not for deployment.

    python scripts/dev.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("BENCH_NO_AUTH", "1")
os.environ.setdefault("BENCH_DB", str(ROOT / "bench.dev.sqlite"))

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
