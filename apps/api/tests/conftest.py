"""Test bootstrap — make the `app` package importable without a running DB."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("ADMIN_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
