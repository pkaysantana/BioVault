import { useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type User = { id: string; name: string; role: string; team: string };

type ArtifactStatus = "active" | "revoked" | "quarantined" | "redacted";
type ArtifactSensitivity = "public" | "internal" | "restricted" | "confidential";

type Artifact = {
  id: string;
  title: string;
  type: "source" | "derived";
  sensitivity: ArtifactSensitivity;
  status: ArtifactStatus;
  created_by: string;
  created_at: string;
  plaintext_content?: string;
};

type AccessResult = {
  decision: "allow" | "deny";
  reason: string;
  latency_ms: number;
  request_id?: string;
};

type ArtifactResponse = { access: AccessResult; principal_id: string; artifact: Artifact };

type ParentEdge = {
  artifact: Artifact;
  inclusion: "included" | "redacted";
  dependency_type: string;
  source_hash: string | null;
  reason: string | null;
};

type RedactionAttestation = {
  id: string;
  artifact_id: string;
  created_by: string;
  reason: string;
  created_at: string;
  detail: string;
};

type LineageResponse = {
  artifact: Artifact;
  parents: ParentEdge[];
  children: Artifact[];
  ancestors: Artifact[];
  descendants: Artifact[];
  redaction_attestation: RedactionAttestation | null;
};

type AuditEvent = {
  id: string;
  timestamp: string;
  user_id: string;
  artifact_id: string;
  operation: string;
  decision: "allow" | "deny";
  reason: string;
  latency_ms: number;
  request_id?: string;
};

type LatencyMetrics = {
  count: number;
  allow_count: number;
  deny_count: number;
  mean_ms: number;
  median_ms: number;
  p95_ms: number;
  p99_ms: number;
  min_ms: number;
  max_ms: number;
  message?: string;
};

type SeedResponse = { status: string; users: number; artifacts: number; tokens: Record<string, string> };

// ---------------------------------------------------------------------------
// API helpers — identity is carried ONLY by the bearer capability token.
// ---------------------------------------------------------------------------

function authHeaders(token?: string): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function getJson<T>(path: string, token?: string): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, { headers: authHeaders(token) });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function postJson<T>(path: string, body: unknown, token?: string): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------

const STATUS_CLASS: Record<ArtifactStatus, string> = {
  active: "badge-active",
  revoked: "badge-revoked",
  quarantined: "badge-quarantined",
  redacted: "badge-redacted",
};
const SENSITIVITY_CLASS: Record<ArtifactSensitivity, string> = {
  public: "badge-public",
  internal: "badge-internal",
  restricted: "badge-restricted",
  confidential: "badge-confidential",
};

const StatusBadge = ({ status }: { status: ArtifactStatus }) => (
  <span className={`badge ${STATUS_CLASS[status]}`}>{status}</span>
);
const SensitivityBadge = ({ sensitivity }: { sensitivity: ArtifactSensitivity }) => (
  <span className={`badge ${SENSITIVITY_CLASS[sensitivity]}`}>{sensitivity}</span>
);

// ---------------------------------------------------------------------------
// Demo steps — each demonstrates the capability-bound boundary.
// ---------------------------------------------------------------------------

const DEMO_STEPS = [
  { label: "Seed data", description: "Reset; mint principal tokens" },
  { label: "CEO reads Phase II memo", description: "ALLOW — has read capability" },
  { label: "CRO reads Phase II memo", description: "DENY — missing capability grant" },
  { label: "Regulatory reads Phase II memo", description: "ALLOW — sources healthy" },
  { label: "CEO derives redacted memo", description: "Governed redaction on healthy sources" },
  { label: "CEO revokes Adverse Event Memo", description: "Quarantine propagates downstream" },
  { label: "Regulatory reads Phase II memo", description: "DENY — derived_from_revoked_source" },
  { label: "CEO retries redacted derive", description: "DENY — cannot_redact_revoked_source" },
];

const REDACT_PARENTS = ["public_target_paper", "internal_sar_table", "toxicity_report", "adverse_event_memo"];

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [users, setUsers] = useState<User[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [metrics, setMetrics] = useState<LatencyMetrics | null>(null);
  const [tokens, setTokens] = useState<Record<string, string>>({});
  const [selectedUserId, setSelectedUserId] = useState("u_ceo");
  const [selectedArtifactId, setSelectedArtifactId] = useState("phase2_readiness_memo");
  const [artifactResponse, setArtifactResponse] = useState<ArtifactResponse | null>(null);
  const [lineage, setLineage] = useState<LineageResponse | null>(null);
  const [message, setMessage] = useState("Loading demo data…");
  const [loading, setLoading] = useState(false);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [activeStep, setActiveStep] = useState<number | null>(null);

  const selectedUser = useMemo(() => users.find((u) => u.id === selectedUserId), [selectedUserId, users]);
  const tokenFor = useCallback((userId: string) => tokens[userId], [tokens]);

  const refresh = useCallback(async () => {
    const [u, a, ev, m] = await Promise.all([
      getJson<User[]>("/users"),
      getJson<Artifact[]>("/artifacts"),
      getJson<AuditEvent[]>("/audit"),
      getJson<LatencyMetrics>("/metrics/permission-latency"),
    ]);
    setUsers(u);
    setArtifacts(a);
    setAudit(ev);
    setMetrics(m);
  }, []);

  const loadLineage = useCallback(async (artifactId: string) => {
    setLineage(await getJson<LineageResponse>(`/lineage/${artifactId}`));
  }, []);

  async function seedDemo() {
    setLoading(true);
    try {
      const res = await postJson<SeedResponse>("/seed", {});
      setTokens(res.tokens);
      setSelectedUserId("u_ceo");
      setSelectedArtifactId("phase2_readiness_memo");
      setArtifactResponse(null);
      setCompletedSteps(new Set());
      await refresh();
      await loadLineage("phase2_readiness_memo");
      setMessage("Seeded. Principal tokens minted (stored hashed). Follow the demo steps →");
      setActiveStep(null);
      return res.tokens;
    } catch (e) {
      setMessage(`Seed failed: ${(e as Error).message}`);
      return {};
    } finally {
      setLoading(false);
    }
  }

  async function openArtifact(
    artifactId = selectedArtifactId,
    userId = selectedUserId,
    tokenOverride?: Record<string, string>,
  ) {
    const token = (tokenOverride ?? tokens)[userId];
    setLoading(true);
    try {
      const response = await getJson<ArtifactResponse>(`/artifacts/${artifactId}`, token);
      setSelectedArtifactId(artifactId);
      setArtifactResponse(response);
      await Promise.all([refresh(), loadLineage(artifactId)]);
      setMessage(`${response.access.decision.toUpperCase()}: ${response.access.reason} (${response.access.latency_ms} ms)`);
    } catch (e) {
      setMessage(`Open failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  async function revokeAdverseEventMemo(userId = selectedUserId) {
    setLoading(true);
    try {
      const result = await postJson<{ revoked: boolean; quarantined: string[]; access: AccessResult }>(
        "/artifacts/adverse_event_memo/revoke",
        { purpose: "demo_revocation" },
        tokenFor(userId),
      );
      await refresh();
      await loadLineage(selectedArtifactId);
      setMessage(
        result.revoked
          ? `Revoked adverse_event_memo. Quarantined: ${result.quarantined.join(", ") || "none"}.`
          : `Revocation denied: ${result.access?.reason}.`,
      );
    } catch (e) {
      setMessage(`Revoke failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  async function deriveRedactedMemo(userId = selectedUserId) {
    setLoading(true);
    try {
      const res = await postJson<{ created: boolean; reason?: string; artifact?: Artifact }>(
        "/derive",
        {
          title: "Redacted Phase II Readiness Memo",
          parent_artifact_ids: REDACT_PARENTS,
          redacted: true,
          redact_parent_ids: ["adverse_event_memo"],
          reason: "broad_distribution",
        },
        tokenFor(userId),
      );
      await refresh();
      if (res.created && res.artifact) {
        setSelectedArtifactId(res.artifact.id);
        await openArtifact(res.artifact.id, userId);
        setMessage("Governed redaction created (attested). Adverse-event content excluded.");
      } else {
        await loadLineage(selectedArtifactId);
        setMessage(`Redaction denied: ${res.reason}. Redaction is not a bypass.`);
      }
    } catch (e) {
      setMessage(`Derive failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  async function runStep(i: number) {
    setActiveStep(i);
    try {
      if (i === 0) {
        await seedDemo();
      } else if (i === 1) {
        setSelectedUserId("u_ceo");
        await openArtifact("phase2_readiness_memo", "u_ceo");
      } else if (i === 2) {
        setSelectedUserId("u_cro");
        await openArtifact("phase2_readiness_memo", "u_cro");
      } else if (i === 3) {
        setSelectedUserId("u_regulatory");
        await openArtifact("phase2_readiness_memo", "u_regulatory");
      } else if (i === 4) {
        setSelectedUserId("u_ceo");
        await deriveRedactedMemo("u_ceo");
      } else if (i === 5) {
        setSelectedUserId("u_ceo");
        await revokeAdverseEventMemo("u_ceo");
      } else if (i === 6) {
        setSelectedUserId("u_regulatory");
        await openArtifact("phase2_readiness_memo", "u_regulatory");
      } else if (i === 7) {
        setSelectedUserId("u_ceo");
        await deriveRedactedMemo("u_ceo");
      }
      setCompletedSteps((prev) => new Set([...prev, i]));
    } finally {
      setActiveStep(null);
    }
  }

  useEffect(() => {
    seedDemo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedArtifactId) loadLineage(selectedArtifactId).catch(() => {});
  }, [selectedArtifactId, loadLineage]);

  const maskedToken = selectedUser && tokens[selectedUser.id]
    ? `${tokens[selectedUser.id].slice(0, 6)}…${tokens[selectedUser.id].slice(-4)}`
    : "—";

  return (
    <main className="app-shell">
      <header className="hero">
        <div className="hero-text">
          <p className="eyebrow">BioVault · BasedAI Enterprise Memory Governance</p>
          <h1>Capability-secured artifact memory for AI science agents</h1>
          <p>
            Identity is proven by an unforgeable capability token, never a client-supplied user id.
            Deterministic permission checks (no LLM), governed redaction with attestation, and
            lineage-aware revocation propagation — every attempt audited.
          </p>
        </div>
        <div className="actions">
          <button disabled={loading} onClick={() => seedDemo()} className="btn-primary">↺ Seed / Reset Demo</button>
          <button disabled={loading} onClick={() => revokeAdverseEventMemo()} className="btn-danger">⊘ Revoke Adverse Event Memo</button>
          <button disabled={loading} onClick={() => deriveRedactedMemo()} className="btn-secondary">✦ Derive Redacted Memo</button>
        </div>
      </header>

      <section className="card demo-steps">
        <h2>Demo Flow</h2>
        <ol className="step-list">
          {DEMO_STEPS.map((step, i) => (
            <li
              key={i}
              className={["step", completedSteps.has(i) ? "step-done" : "", activeStep === i ? "step-active" : ""].filter(Boolean).join(" ")}
            >
              <button className="step-btn" disabled={loading} onClick={() => runStep(i)} title={step.description}>
                <span className="step-num">{completedSteps.has(i) ? "✓" : i + 1}</span>
                <span className="step-label">{step.label}</span>
                <span className="step-desc">{step.description}</span>
              </button>
            </li>
          ))}
        </ol>
      </section>

      <section className="toolbar card">
        <label>
          Acting principal (selects that user's capability token)
          <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.name} — {u.role}</option>
            ))}
          </select>
        </label>
        <div className="user-meta">
          <strong>{selectedUser?.team ?? "—"}</strong>
          <span>token: {maskedToken}</span>
        </div>
        <button disabled={loading || !selectedArtifactId} onClick={() => openArtifact()}>Open Selected Artifact</button>
        <p className="status-line">{loading ? "Working…" : message}</p>
      </section>

      <section className="dashboard">
        <div className="card artifact-list">
          <h2>Artifacts</h2>
          {artifacts.map((a) => (
            <button
              className={`artifact-row${a.id === selectedArtifactId ? " selected" : ""} status-${a.status}`}
              key={a.id}
              onClick={() => { setSelectedArtifactId(a.id); setArtifactResponse(null); }}
            >
              <span className="artifact-title">{a.title}</span>
              <div className="artifact-badges">
                <span className="artifact-type">{a.type}</span>
                <SensitivityBadge sensitivity={a.sensitivity} />
                <StatusBadge status={a.status} />
              </div>
            </button>
          ))}
        </div>

        <div className="card detail-panel">
          <h2>Selected Artifact</h2>
          {artifactResponse ? (
            <>
              <div className={`decision ${artifactResponse.access.decision}`}>
                <strong>{artifactResponse.access.decision.toUpperCase()}</strong>
                <span className="reason">{artifactResponse.access.reason}</span>
                <small>{artifactResponse.access.latency_ms} ms</small>
              </div>
              <p className="meta">principal: {artifactResponse.principal_id} · {artifactResponse.access.request_id}</p>
              <h3>{artifactResponse.artifact.title}</h3>
              <div className="artifact-badges" style={{ marginBottom: 12 }}>
                <span className="artifact-type">{artifactResponse.artifact.type}</span>
                <SensitivityBadge sensitivity={artifactResponse.artifact.sensitivity} />
                <StatusBadge status={artifactResponse.artifact.status} />
              </div>
              <pre>{artifactResponse.artifact.plaintext_content ?? "Content withheld — access was denied."}</pre>
            </>
          ) : (
            <p className="empty">Select an artifact and click "Open Selected Artifact" to trigger a token-authenticated, logged permission check.</p>
          )}
        </div>

        <div className="card lineage-panel">
          <h2>Lineage</h2>
          {lineage ? (
            <>
              <h3>Direct Parents</h3>
              {lineage.parents.length === 0 ? (
                <p className="empty">No parents.</p>
              ) : (
                <ul className="lineage-list">
                  {lineage.parents.map((p) => (
                    <li key={p.artifact.id} className={`lineage-item status-${p.artifact.status}`}>
                      <span>{p.artifact.title}</span>
                      <div className="artifact-badges">
                        <StatusBadge status={p.artifact.status} />
                        <span className={`badge ${p.inclusion === "redacted" ? "badge-revoked" : "badge-active"}`}>{p.inclusion}</span>
                        {p.source_hash && <span className="hash">#{p.source_hash}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {lineage.redaction_attestation && (
                <div className="attestation">
                  <strong>Redaction attestation</strong>
                  <span>by {lineage.redaction_attestation.created_by} · {lineage.redaction_attestation.reason}</span>
                </div>
              )}
              <h3>All Descendants</h3>
              <SimpleLineageList artifacts={lineage.descendants} empty="No downstream artifacts." />
            </>
          ) : (
            <p className="empty">No lineage loaded.</p>
          )}
        </div>
      </section>

      {metrics && metrics.count > 0 && (
        <section className="card metrics-card">
          <h2>Permission Latency</h2>
          <div className="metrics-grid">
            <MetricTile label="Checks" value={String(metrics.count)} />
            <MetricTile label="Allow" value={String(metrics.allow_count)} accent="green" />
            <MetricTile label="Deny" value={String(metrics.deny_count)} accent="red" />
            <MetricTile label="Mean" value={`${metrics.mean_ms} ms`} />
            <MetricTile label="Median" value={`${metrics.median_ms} ms`} />
            <MetricTile label="p95" value={`${metrics.p95_ms} ms`} />
            <MetricTile label="p99" value={`${metrics.p99_ms} ms`} accent={metrics.p99_ms < 200 ? "green" : "red"} />
            <MetricTile label="Max" value={`${metrics.max_ms} ms`} />
          </div>
        </section>
      )}

      <section className="card audit-card">
        <h2>Audit Log <span className="audit-count">{audit.length} events</span></h2>
        <div className="audit-table">
          <div className="audit-grid header">
            <span>Time</span>
            <span>Principal</span>
            <span>Artifact</span>
            <span>Op</span>
            <span>Decision</span>
            <span>Reason</span>
            <span>Latency</span>
          </div>
          {audit.map((ev) => (
            <div className="audit-grid" key={ev.id}>
              <span>{new Date(ev.timestamp).toLocaleTimeString()}</span>
              <span>{ev.user_id}</span>
              <span className="audit-artifact">{ev.artifact_id}</span>
              <span>{ev.operation}</span>
              <span className={ev.decision}>{ev.decision}</span>
              <span className="audit-reason">{ev.reason}</span>
              <span>{ev.latency_ms} ms</span>
            </div>
          ))}
          {audit.length === 0 && <p className="empty" style={{ padding: "12px 0" }}>No audit events yet.</p>}
        </div>
      </section>
    </main>
  );
}

function SimpleLineageList({ artifacts, empty }: { artifacts: Artifact[]; empty: string }) {
  if (artifacts.length === 0) return <p className="empty">{empty}</p>;
  return (
    <ul className="lineage-list">
      {artifacts.map((a) => (
        <li key={a.id} className={`lineage-item status-${a.status}`}>
          <span>{a.title}</span>
          <div className="artifact-badges">
            <SensitivityBadge sensitivity={a.sensitivity} />
            <StatusBadge status={a.status} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function MetricTile({ label, value, accent }: { label: string; value: string; accent?: "green" | "red" }) {
  return (
    <div className={`metric-tile${accent ? ` metric-${accent}` : ""}`}>
      <span className="metric-value">{value}</span>
      <span className="metric-label">{label}</span>
    </div>
  );
}
