"""Regression tests for weaknesses found in the BioVault evidence audit (main @ d832cf6).

Each test reproduces a previously observed weakness and asserts the fixed behaviour.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.conftest import ADMIN_TOKEN, auth

PHASE2 = "phase2_readiness_memo"
ADVERSE = "adverse_event_memo"
BIOTECH_PARENTS = ["public_target_paper", "internal_sar_table", "toxicity_report", ADVERSE]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def read(client, token, artifact_id):
    return client.get(f"/artifacts/{artifact_id}", headers=auth(token))


def grant(client, issuer_token, artifact_id, subject, operation="read", **extra):
    body = {"subject_user_id": subject, "operation": operation, "purpose": "security_regression", **extra}
    return client.post(f"/artifacts/{artifact_id}/grant", headers=auth(issuer_token), json=body)


def audit_count(client, tokens):
    return len(client.get("/audit", headers=auth(tokens["u_ceo"])).json())


# ---------------------------------------------------------------------------
# W1. requirements.txt was UTF-16, breaking `pip install -r requirements-dev.txt`
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["requirements.txt", "requirements-dev.txt"])
def test_requirements_files_are_plain_utf8(name):
    raw = (BACKEND_ROOT / name).read_bytes()
    assert b"\x00" not in raw
    assert not raw.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf"))
    raw.decode("utf-8")


def test_requirements_txt_lists_runtime_dependencies():
    text = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")
    names = {line.split("==")[0].strip().lower() for line in text.splitlines() if "==" in line}
    assert {"fastapi", "uvicorn", "cryptography", "python-dotenv"} <= names


# ---------------------------------------------------------------------------
# W2. Unauthenticated POST /seed wiped the store and returned every token
# ---------------------------------------------------------------------------

def test_seed_disabled_unless_demo_mode(seeded, client, monkeypatch):
    before = audit_count(client, seeded)
    monkeypatch.delenv("BIOVAULT_DEMO_MODE", raising=False)
    r = client.post("/seed", headers=auth(ADMIN_TOKEN))
    assert r.status_code == 403
    assert r.json()["detail"]["reason"] == "seed_disabled"
    assert "tokens" not in r.json()
    # Existing principals and audit rows survive.
    assert read(client, seeded["u_ceo"], PHASE2).status_code == 200
    assert audit_count(client, seeded) >= before


def test_seed_without_authorisation_is_rejected(seeded, client):
    before = audit_count(client, seeded)
    r = client.post("/seed")
    assert r.status_code == 401
    assert "tokens" not in r.json()
    assert read(client, seeded["u_ceo"], PHASE2).status_code == 200
    assert audit_count(client, seeded) >= before


def test_seed_rejects_principal_and_wrong_admin_tokens(seeded, client):
    for bad in (seeded["u_ceo"], ADMIN_TOKEN + "x", "short"):
        r = client.post("/seed", headers=auth(bad))
        assert r.status_code == 403, bad
        assert r.json()["detail"]["reason"] == "invalid_admin_token"
    assert read(client, seeded["u_ceo"], PHASE2).status_code == 200


def test_seed_fails_closed_without_strong_admin_token(seeded, client, monkeypatch):
    monkeypatch.delenv("BIOVAULT_ADMIN_TOKEN", raising=False)
    r = client.post("/seed", headers=auth(ADMIN_TOKEN))
    assert r.status_code == 403
    assert r.json()["detail"]["reason"] == "admin_token_not_configured"

    monkeypatch.setenv("BIOVAULT_ADMIN_TOKEN", "too-short")
    r = client.post("/seed", headers=auth("too-short"))
    assert r.status_code == 403
    assert r.json()["detail"]["reason"] == "admin_token_not_configured"


def test_seed_admin_token_in_url_rejected(client):
    r = client.post(f"/seed?token={ADMIN_TOKEN}")
    assert r.status_code == 401
    assert r.json()["detail"]["reason"] == "token_in_url_rejected"


# ---------------------------------------------------------------------------
# W3. Metadata, audit, lineage and metrics endpoints needed no authentication
# ---------------------------------------------------------------------------

METADATA_PATHS = ["/users", "/artifacts", "/audit", f"/lineage/{PHASE2}", "/metrics/permission-latency"]


@pytest.mark.parametrize("path", METADATA_PATHS)
def test_metadata_endpoints_require_bearer(seeded, client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth("not-a-real-token")).status_code == 401


def test_health_stays_public(client):
    assert client.get("/health").status_code == 200


def test_artifact_list_limited_to_caller_grants(seeded, client):
    cro_ids = {a["id"] for a in client.get("/artifacts", headers=auth(seeded["u_cro"])).json()}
    assert cro_ids == {"public_target_paper", "cro_assay_report"}
    intern_ids = {a["id"] for a in client.get("/artifacts", headers=auth(seeded["u_intern"])).json()}
    assert intern_ids == {"public_target_paper"}
    ceo_ids = {a["id"] for a in client.get("/artifacts", headers=auth(seeded["u_ceo"])).json()}
    assert PHASE2 in ceo_ids and len(ceo_ids) == 8


def test_audit_scoped_to_own_events_or_audit_capability(seeded, client):
    cro_deny = read(client, seeded["u_cro"], PHASE2).json()["access"]["request_id"]
    reg_allow = read(client, seeded["u_regulatory"], PHASE2).json()["access"]["request_id"]

    cro_events = client.get("/audit", headers=auth(seeded["u_cro"])).json()
    assert cro_events and {e["user_id"] for e in cro_events} == {"u_cro"}
    assert reg_allow not in {e["request_id"] for e in cro_events}

    ceo_rids = {e["request_id"] for e in client.get("/audit", headers=auth(seeded["u_ceo"])).json()}
    assert {cro_deny, reg_allow} <= ceo_rids


def test_audit_capability_survives_source_revocation(seeded, client):
    rid = read(client, seeded["u_regulatory"], ADVERSE).json()["access"]["request_id"]
    client.post(f"/artifacts/{ADVERSE}/revoke", headers=auth(seeded["u_ceo"]), json={})
    ceo_rids = {e["request_id"] for e in client.get("/audit", headers=auth(seeded["u_ceo"])).json()}
    assert rid in ceo_rids


def test_lineage_requires_visibility_on_target(seeded, client):
    r = client.get(f"/lineage/{PHASE2}", headers=auth(seeded["u_cro"]))
    assert r.status_code == 403
    assert r.json()["detail"]["reason"] == "missing_lineage_visibility"
    # Unknown artifacts are indistinguishable from invisible ones.
    assert client.get("/lineage/no_such_artifact", headers=auth(seeded["u_cro"])).status_code == 403


def test_lineage_hides_nodes_caller_cannot_see(seeded, client):
    body = client.get("/lineage/public_target_paper", headers=auth(seeded["u_intern"])).json()
    assert body["children"] == [] and body["descendants"] == []
    ceo = client.get("/lineage/public_target_paper", headers=auth(seeded["u_ceo"])).json()
    assert PHASE2 in {c["id"] for c in ceo["children"]}

    # A reader of the derived memo without source grants sees only the parents it may read.
    assert grant(client, seeded["u_ceo"], PHASE2, "u_cro", "read").json()["granted"] is True
    cro = client.get(f"/lineage/{PHASE2}", headers=auth(seeded["u_cro"])).json()
    assert {p["artifact"]["id"] for p in cro["parents"]} == {"public_target_paper"}
    assert {a["id"] for a in cro["ancestors"]} == {"public_target_paper"}


def test_metrics_scoped_to_visible_audit_rows(seeded, client):
    read(client, seeded["u_regulatory"], PHASE2)
    read(client, seeded["u_cro"], PHASE2)
    cro = client.get("/metrics/permission-latency", headers=auth(seeded["u_cro"])).json()
    assert cro["count"] == 1 and cro["deny_count"] == 1


# ---------------------------------------------------------------------------
# W4. Bearer tokens accepted in the URL query string
# ---------------------------------------------------------------------------

def test_token_query_param_rejected(seeded, client):
    r = client.get(f"/artifacts/{PHASE2}?token={seeded['u_ceo']}")
    assert r.status_code == 401
    assert r.json()["detail"]["reason"] == "token_in_url_rejected"


def test_token_query_param_rejected_even_with_valid_header(seeded, client):
    r = client.get(f"/artifacts/{PHASE2}?token={seeded['u_ceo']}", headers=auth(seeded["u_ceo"]))
    assert r.status_code == 401
    r = client.post(f"/query?token={seeded['u_ceo']}", headers=auth(seeded["u_ceo"]),
                    json={"artifact_id": PHASE2})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# W5. expires_at compared as an unvalidated string
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["not-a-date", "9", "2020-01-01", "2020-01-01T00:00:00", 9, ""])
def test_malformed_or_naive_expiry_rejected(seeded, client, bad):
    r = grant(client, seeded["u_ceo"], "internal_sar_table", "u_intern", expires_at=bad)
    assert r.status_code == 422
    assert read(client, seeded["u_intern"], "internal_sar_table").json()["access"]["decision"] == "deny"


def test_past_expiry_with_non_utc_offset_denies(seeded, client):
    plus5 = timezone(timedelta(hours=5))
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).astimezone(plus5).isoformat()
    r = grant(client, seeded["u_ceo"], "internal_sar_table", "u_intern", expires_at=past)
    assert r.json()["granted"] is True
    assert read(client, seeded["u_intern"], "internal_sar_table").json()["access"]["decision"] == "deny"


def test_future_expiry_with_negative_offset_allows_and_is_normalised(seeded, client):
    minus5 = timezone(timedelta(hours=-5))
    instant = datetime.now(timezone.utc) + timedelta(hours=1)
    r = grant(client, seeded["u_ceo"], "internal_sar_table", "u_intern",
              expires_at=instant.astimezone(minus5).isoformat())
    stored = r.json()["grant"]["expires_at"]
    assert stored.endswith("+00:00")
    assert datetime.fromisoformat(stored) == instant
    assert read(client, seeded["u_intern"], "internal_sar_table").json()["access"]["decision"] == "allow"


def test_z_suffix_expiry_accepted(seeded, client):
    r = grant(client, seeded["u_ceo"], "internal_sar_table", "u_intern", expires_at="2020-01-01T00:00:00Z")
    assert r.json()["granted"] is True
    assert r.json()["grant"]["expires_at"] == "2020-01-01T00:00:00+00:00"
    assert read(client, seeded["u_intern"], "internal_sar_table").json()["access"]["decision"] == "deny"


def test_legacy_malformed_expiry_row_fails_closed(seeded, client):
    from app.main import add_grant, connect

    with connect() as conn:
        add_grant(conn, "u_intern", "internal_sar_table", "read", "not-a-date")
    assert read(client, seeded["u_intern"], "internal_sar_table").json()["access"]["decision"] == "deny"


# ---------------------------------------------------------------------------
# W6. Grant-only authority could self-grant (or hand out) read
# ---------------------------------------------------------------------------

def test_grant_only_holder_cannot_self_grant_read(seeded, client):
    assert grant(client, seeded["u_ceo"], ADVERSE, "u_intern", "grant").json()["granted"] is True
    r = grant(client, seeded["u_intern"], ADVERSE, "u_intern", "read")
    assert r.json()["granted"] is False
    assert r.json()["access"]["reason"] == "self_grant_forbidden"
    assert read(client, seeded["u_intern"], ADVERSE).json()["access"]["decision"] == "deny"


def test_grant_only_holder_cannot_delegate_read_to_others(seeded, client):
    grant(client, seeded["u_ceo"], ADVERSE, "u_intern", "grant")
    r = grant(client, seeded["u_intern"], ADVERSE, "u_cro", "read")
    assert r.json()["granted"] is False
    assert r.json()["access"]["reason"] == "delegation_exceeds_issuer_capability"
    assert read(client, seeded["u_cro"], ADVERSE).json()["access"]["decision"] == "deny"


def test_self_grant_forbidden_for_any_issuer(seeded, client):
    r = grant(client, seeded["u_ceo"], "board_update", "u_ceo", "read")
    assert r.json()["granted"] is False
    assert r.json()["access"]["reason"] == "self_grant_forbidden"


def test_rejected_delegation_is_audited(seeded, client):
    grant(client, seeded["u_ceo"], ADVERSE, "u_intern", "grant")
    r = grant(client, seeded["u_intern"], ADVERSE, "u_cro", "read")
    rid = r.json()["access"]["request_id"]
    events = client.get("/audit", headers=auth(seeded["u_ceo"])).json()
    assert any(e["request_id"] == rid and e["decision"] == "deny"
               and e["reason"] == "delegation_exceeds_issuer_capability" for e in events)


# ---------------------------------------------------------------------------
# W7. Redaction could omit every source; revoked included source untested
# ---------------------------------------------------------------------------

def test_redaction_must_include_at_least_one_source(seeded, client):
    r = client.post("/derive", headers=auth(seeded["u_ceo"]), json={
        "title": "Empty Redaction", "parent_artifact_ids": BIOTECH_PARENTS,
        "redacted": True, "redact_parent_ids": BIOTECH_PARENTS, "reason": "omit_all",
    })
    assert r.json()["created"] is False
    assert r.json()["reason"] == "redaction_must_include_source"
    ids = {a["id"] for a in client.get("/artifacts", headers=auth(seeded["u_ceo"])).json()}
    assert "redacted_phase2_readiness_memo" not in ids


def test_redacted_derivative_denied_when_included_source_revoked(seeded, client):
    r = client.post("/derive", headers=auth(seeded["u_ceo"]), json={
        "title": "Redacted Phase II Memo", "parent_artifact_ids": BIOTECH_PARENTS,
        "redacted": True, "redact_parent_ids": [ADVERSE], "reason": "broad_distribution",
    })
    redacted_id = r.json()["artifact"]["id"]
    assert read(client, seeded["u_regulatory"], redacted_id).json()["access"]["decision"] == "allow"

    client.post("/artifacts/toxicity_report/revoke", headers=auth(seeded["u_ceo"]), json={})

    body = read(client, seeded["u_regulatory"], redacted_id).json()
    assert body["access"]["decision"] == "deny"
    assert body["access"]["reason"] == "derived_from_revoked_source"
    assert "plaintext_content" not in body["artifact"]
    q = client.post("/query", headers=auth(seeded["u_regulatory"]),
                    json={"artifact_id": redacted_id}).json()
    assert q["decision"] == "deny" and q["authorized_context"] is None
    assert q["lineage_metadata"]["blocked_source_artifact_id"] == "toxicity_report"


# ---------------------------------------------------------------------------
# Least privilege for the remediation itself
# ---------------------------------------------------------------------------

def test_users_directory_limited_to_audit_holders(seeded, client):
    for uid in ("u_cro", "u_intern", "u_regulatory"):
        users = client.get("/users", headers=auth(seeded[uid])).json()
        assert [u["id"] for u in users] == [uid]
    ceo = client.get("/users", headers=auth(seeded["u_ceo"])).json()
    assert len(ceo) == 6
    assert all(set(u) == {"id", "name", "role", "team"} for u in ceo)


def test_derivative_creator_gets_no_audit_capability(seeded, client):
    r = client.post("/derive", headers=auth(seeded["u_compchem"]), json={
        "title": "SAR Docking Summary",
        "parent_artifact_ids": ["public_target_paper", "internal_sar_table"],
    })
    assert r.json()["created"] is True
    new_id = r.json()["artifact"]["id"]
    read(client, seeded["u_research"], new_id)

    compchem_events = client.get("/audit", headers=auth(seeded["u_compchem"])).json()
    assert {e["user_id"] for e in compchem_events} == {"u_compchem"}
    assert [u["id"] for u in client.get("/users", headers=auth(seeded["u_compchem"])).json()] == ["u_compchem"]

    ceo_events = client.get("/audit", headers=auth(seeded["u_ceo"])).json()
    assert any(e["artifact_id"] == new_id and e["user_id"] == "u_research" for e in ceo_events)


# ---------------------------------------------------------------------------
# W9. /audit limit had a maximum but no minimum; SQLite treats LIMIT -1 as unbounded
# ---------------------------------------------------------------------------

def make_audit_events(client, tokens, n=3):
    for _ in range(n):
        read(client, tokens["u_cro"], PHASE2)
        read(client, tokens["u_regulatory"], PHASE2)


@pytest.mark.parametrize("limit", [-1, 0, -500])
def test_audit_rejects_non_positive_limit(seeded, client, limit):
    make_audit_events(client, seeded)
    r = client.get("/audit", params={"limit": limit}, headers=auth(seeded["u_ceo"]))
    assert r.status_code == 422


def test_audit_limit_keeps_maximum_and_pagination(seeded, client):
    make_audit_events(client, seeded)
    ceo = auth(seeded["u_ceo"])
    assert client.get("/audit", params={"limit": 501}, headers=ceo).status_code == 422
    assert len(client.get("/audit", params={"limit": 1}, headers=ceo).json()) == 1
    assert len(client.get("/audit", params={"limit": 2}, headers=ceo).json()) == 2
    assert client.get("/audit", params={"limit": 500}, headers=ceo).status_code == 200
    assert len(client.get("/audit", headers=ceo).json()) == audit_count(client, seeded) >= 6


@pytest.mark.parametrize("limit", [-1, 0, 1])
def test_audit_limit_does_not_bypass_authentication(seeded, client, limit):
    make_audit_events(client, seeded)
    r = client.get("/audit", params={"limit": limit})
    assert r.status_code == 401
    assert "detail" in r.json() and not isinstance(r.json(), list)


def test_audit_limit_keeps_principal_scope(seeded, client):
    make_audit_events(client, seeded)
    cro = auth(seeded["u_cro"])
    assert client.get("/audit", params={"limit": -1}, headers=cro).status_code == 422
    for limit in (1, 500):
        events = client.get("/audit", params={"limit": limit}, headers=cro).json()
        assert events and {e["user_id"] for e in events} == {"u_cro"}
