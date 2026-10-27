"""
Vercel Services deliver the original public path (`/api/...`) to the backend
service. The app must serve exactly one public interface there — `/api/*` —
and keep the unprefixed interface for local and Render deployments.
"""
import json
from pathlib import Path

import pytest

from app.main import app
from tests.conftest import ADMIN_TOKEN, auth

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE2 = "phase2_readiness_memo"

UNAUTHENTICATED_PROTECTED = [
    ("post", "/api/seed", None),
    ("post", "/api/query", {"artifact_id": PHASE2, "purpose": "routing_regression"}),
    ("get", "/api/audit", None),
    ("get", "/api/users", None),
    ("get", "/api/artifacts", None),
    ("get", f"/api/artifacts/{PHASE2}", None),
    ("post", f"/api/artifacts/{PHASE2}/grant",
     {"subject_user_id": "u_intern", "operation": "read", "purpose": "routing_regression"}),
    ("post", f"/api/artifacts/{PHASE2}/revoke", {}),
    ("post", "/api/derive", {"title": "x", "parent_artifact_ids": [PHASE2]}),
    ("get", f"/api/lineage/{PHASE2}", None),
    ("get", "/api/metrics/permission-latency", None),
]


@pytest.fixture()
def on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")


def test_vercel_serves_api_prefix(client, on_vercel):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/health", "/api/api/health", "/apihealth", "/seed"])
def test_vercel_has_no_alias_paths(client, on_vercel, path):
    assert client.get(path).status_code == 404
    assert client.post(path).status_code == 404


def test_local_interface_unchanged(client, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    assert client.get("/health").status_code == 200
    assert client.get("/api/health").status_code == 404


@pytest.mark.parametrize("method,path,body", UNAUTHENTICATED_PROTECTED)
def test_vercel_protected_endpoints_still_require_auth(seeded, client, on_vercel, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_vercel_seed_still_requires_admin_token(client, on_vercel):
    assert client.post("/api/seed", headers=auth("u_ceo-is-not-admin-0123456789")).status_code == 403
    r = client.post("/api/seed", headers=auth(ADMIN_TOKEN))
    assert r.status_code == 200 and "u_ceo" in r.json()["tokens"]


def test_vercel_authorised_calls_reach_routes(seeded, client, on_vercel):
    ceo = auth(seeded["u_ceo"])
    read = client.get(f"/api/artifacts/{PHASE2}", headers=ceo).json()
    assert read["access"]["decision"] == "allow" and read["artifact"]["id"] == PHASE2
    q = client.post("/api/query", headers=ceo, json={"artifact_id": PHASE2, "purpose": "routing_regression"})
    assert q.status_code == 200 and q.json()["decision"] == "allow"
    events = client.get("/api/audit", params={"limit": 5}, headers=ceo).json()
    assert events and any(e["artifact_id"] == PHASE2 for e in events)
    assert client.get(f"/api/lineage/{PHASE2}", headers=ceo).json()["artifact"]["id"] == PHASE2
    intern = client.get(f"/api/artifacts/{PHASE2}", headers=auth(seeded["u_intern"])).json()
    assert intern["access"]["decision"] == "deny"


def test_vercel_token_in_url_still_rejected(seeded, client, on_vercel):
    assert client.get(f"/api/artifacts/{PHASE2}?token={seeded['u_ceo']}").status_code == 401


def test_vercel_openapi_advertises_single_api_base(client, on_vercel):
    spec = client.get("/api/openapi.json").json()
    assert spec["servers"] == [{"url": "/api"}]
    assert not [p for p in spec["paths"] if p.startswith("/api")]


def test_routes_registered_once_without_prefix():
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not [p for p in paths if p.startswith("/api")]


def test_vercel_json_routes_api_to_backend_without_path_transform():
    config = json.loads((REPO_ROOT / "vercel.json").read_text())
    backend = config["services"]["backend"]
    transforms = [t for route in backend.get("routes", []) for t in route.get("transforms", [])]
    assert not [t for t in transforms if t.get("type") == "request.path"]
    rewrites = config["rewrites"]
    assert rewrites[0] == {"source": "/api(/.*)?", "destination": {"service": "backend"}}
    assert rewrites[-1] == {"source": "/(.*)", "destination": {"service": "frontend"}}
