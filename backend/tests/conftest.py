import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make the backend package importable and point the app at an isolated DB
# BEFORE importing app.main (DB_PATH is read at import time).
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

_TMP_DB = Path(tempfile.gettempdir()) / "biovault_test.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["BIOVAULT_DB"] = str(_TMP_DB)

# Test-only demo admin credential; not a real secret.
ADMIN_TOKEN = "test-only-demo-admin-token-0123456789"
os.environ["BIOVAULT_DEMO_MODE"] = "true"
os.environ["BIOVAULT_ADMIN_TOKEN"] = ADMIN_TOKEN

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded(client):
    """Seed the biotech dataset and return the plaintext principal token map."""
    resp = client.post("/seed", headers=auth(ADMIN_TOKEN))
    assert resp.status_code == 200
    return resp.json()["tokens"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
