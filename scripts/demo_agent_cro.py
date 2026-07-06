#!/usr/bin/env python3
"""External CRO science-agent demo - POST /query gate before synthesis.

Usage:
  python scripts/demo_agent_cro.py
  BIOVAULT_BASE_URL=https://your-deploy.example python scripts/demo_agent_cro.py

Requires a running BioVault backend. Seeds on first run if tokens are unavailable.
Stdlib only - no third-party dependencies and no model calls.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BIOVAULT_BASE_URL", "http://localhost:8000").rstrip("/")
ARTIFACT_ID = "phase2_readiness_memo"
AGENT_QUESTION = "Summarise Phase II readiness for the investor deck"


def _request(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _seed_tokens() -> dict[str, str]:
    result = _request("POST", "/seed")
    return result["tokens"]


def main() -> int:
    print(f"BioVault CRO agent demo - base URL: {BASE_URL}")
    print(f"Agent question: {AGENT_QUESTION!r}")
    print(f"Target artifact: {ARTIFACT_ID}")
    print()

    try:
        tokens = _seed_tokens()
    except urllib.error.URLError as exc:
        print(f"ERROR: Could not reach BioVault at {BASE_URL}: {exc}", file=sys.stderr)
        print("Start the backend: uvicorn app.main:app --reload", file=sys.stderr)
        return 1

    cro_token = tokens.get("u_cro")
    if not cro_token:
        print("ERROR: Seed response missing u_cro token.", file=sys.stderr)
        return 1

    try:
        result = _request(
            "POST",
            "/query",
            token=cro_token,
            body={"artifact_id": ARTIFACT_ID, "purpose": "cro_agent_demo"},
        )
    except urllib.error.HTTPError as exc:
        print(f"ERROR: /query failed: {exc.read().decode()}", file=sys.stderr)
        return 1

    decision = result.get("decision", "unknown")
    reason = result.get("reason", "unknown")
    request_id = result.get("request_id", "")
    audit_ref = result.get("audit_ref") or {}

    print(f"POST /query -> {decision.upper()} ({reason})")
    if request_id:
        print(f"request_id: {request_id}")
    if audit_ref:
        print(f"audit_ref.request_id: {audit_ref.get('request_id', '')}")

    if decision == "allow":
        if not result.get("authorized_context"):
            print("ERROR: Allow response missing authorized_context.", file=sys.stderr)
            return 1
        print("WARNING: Expected DENY for External CRO on Phase II memo.")
        return 1

    if result.get("authorized_context") is not None:
        print("ERROR: Denied response must return authorized_context: null.", file=sys.stderr)
        return 1

    forbidden = {"plaintext_content", "content", "context", "synthesis"}
    leaked = forbidden.intersection(result)
    if leaked:
        print(f"ERROR: Denied response leaked text fields: {sorted(leaked)}", file=sys.stderr)
        return 1

    print()
    print("No authorized context returned; no synthesis from protected scientific data.")
    print("BioVault denied access to Phase II Readiness Memo. No model call was made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
