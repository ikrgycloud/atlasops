export type Environment = {
  id: string;
  name: string;
  provider: string;
  description: string;
  health: string;
  demo: boolean;
  last_observed_at: string | null;
  resource_scope: string[];
};
export type Me = {
  email: string;
  role: string;
  tenant_name: string;
  demo: boolean;
  ai_available: boolean;
  ai_status?: {
    available: boolean;
    reason: string | null;
    provider: string;
    response_format: string;
  };
};
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export type Coverage = {
  status: string;
  complete: boolean;
  sources_queried: string[];
  most_recent_observation: string | null;
  missing_telemetry: string[];
  unavailable_integrations: string[];
  observations: number;
  synthetic_observations: number;
  window_start: string;
  window_end: string;
};
export type Summary = {
  environments: number;
  active_incidents: number;
  pending_approvals: number;
  verified_actions: number;
  coverage: Coverage;
  incident_series: { day: string; incidents: number }[];
};
export type Evidence = {
  id: string;
  source: string;
  resource: string;
  observed_at: string;
  quality: string;
  data: Record<string, unknown>;
};
export type Incident = {
  id: string;
  title: string;
  severity: string;
  status: string;
  source: string;
  environment_id: string;
  created_at: string;
  owner: string;
  evidence: Evidence[];
};
export type IncidentEvent = {
  id: string;
  kind: string;
  message: string;
  created_at: string;
  data: Record<string, unknown>;
};
export type Finding = {
  classification: string;
  summary: string;
  confidence: number;
  evidence_ids: string[];
  missing_data: string[];
  next_queries: string[];
  hypotheses: {
    statement: string;
    supporting_evidence: string[];
    contradicting_evidence: string[];
  }[];
  evidence: Evidence[];
  error_code?: string;
  planner?: {
    iterations: number;
    tool_calls: number;
    max_iterations: number;
    max_tool_calls: number;
    termination_reason: string;
    elapsed_seconds: number;
  };
  sources?: Record<
    string,
    {
      status: string;
      count: number;
      latest_observation: string | null;
      capability: string;
    }
  >;
  evidence_partial?: boolean;
};
export type Investigation = {
  id: string;
  status: string;
  created_at: string;
  findings: Partial<Finding>;
};
export type Plan = {
  version: number;
  action_type: string;
  environment_id: string;
  tenant_id: string;
  incident_id: string;
  resource_id: string;
  parameters: { expected_revision: number };
  reason: string;
  evidence_ids: string[];
  expected_effect: string;
  risk: string;
  impact: string;
  required_permissions: string[];
  preconditions: string[];
  verification: string;
  rollback: string;
  expires_at: string;
  created_at: string;
  timeout_seconds: number;
};
export type Proposal = {
  id: string;
  state: string;
  plan: Plan;
  plan_hash: string;
  expires_at: string;
  incident_id: string;
};
export type Approval = {
  id: string;
  decision: string | null;
  plan_hash: string;
  expires_at: string;
  consumed_at: string | null;
  proposal: Proposal;
};
export type Resource = {
  id: string;
  name: string;
  environment_id: string;
  healthy: boolean;
  revision: number;
};
export type Integration = {
  id: string;
  name: string;
  provider: string;
  environment_id: string;
  status: string;
  last_checked_at: string | null;
  error_code: string | null;
  capabilities: string[];
  credential_configured: boolean;
  config: { url: string; repository: string; region: string; query: string };
};
export type Service = {
  id: string;
  name: string;
  owner: string;
  criticality: string;
  health: string;
  environment_id: string;
};
export type Deployment = {
  id: string;
  provider: string;
  workflow: string;
  repository: string;
  revision: string;
  branch: string;
  status: string;
  observed_at: string;
  run_url: string;
  environment_id: string;
};
export type DailyReport = {
  id: string;
  created_at: string;
  window_start: string;
  window_end: string;
  data: {
    title: string;
    summary: string;
    timezone: string;
    coverage: Coverage;
    incidents: {
      id: string;
      title: string;
      severity: string;
      status: string;
    }[];
    deployments: { workflow: string; status: string; revision: string }[];
    executions: { proposal_id: string; status: string }[];
    findings: {
      incident_id: string;
      status: string;
      findings: Partial<Finding>;
    }[];
    actions: { id: string; state: string }[];
    unresolved_incidents_snapshot: number;
    pending_approvals_snapshot: number;
    follow_up: string[];
    slo_assessment: string;
    infrastructure_trends: string;
  };
  deliveries?: {
    id: string;
    status: string;
    attempts: number;
    error_code: string | null;
  }[];
};
let token = sessionStorage.getItem("atlasops-token") || "";
export function setToken(value: string) {
  token = value;
  if (value) sessionStorage.setItem("atlasops-token", value);
  else sessionStorage.removeItem("atlasops-token");
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !path.includes("dev-token")) {
      setToken("");
      window.dispatchEvent(new Event("atlasops-unauthorized"));
    }
    throw new Error(
      data.error?.message || `Request failed (${response.status})`,
    );
  }
  return data as T;
}
