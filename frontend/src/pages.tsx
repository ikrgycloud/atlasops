import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  CircleHelp,
  FileText,
  GitBranch,
  Play,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  type Approval,
  type Coverage,
  type DailyReport,
  type Deployment,
  type Environment,
  type Incident,
  type IncidentEvent,
  type Integration,
  type Investigation,
  type Me,
  type Page,
  type Proposal,
  type Resource,
  type Service,
  type Summary,
} from "./api";
import {
  Badge,
  Data,
  date,
  Empty,
  ErrorBox,
  Heading,
  IncidentLink,
  Modal,
  Pagination,
  SafeLink,
  useAction,
  useAPI,
} from "./ui";

const canOperate = (me: Me) => ["operator", "administrator"].includes(me.role);
const canApprove = (me: Me) => ["approver", "administrator"].includes(me.role);
const admin = (me: Me) => me.role === "administrator";
function Panel({
  title,
  children,
  link,
}: {
  title: string;
  children: ReactNode;
  link?: string;
}) {
  return (
    <section className="panel">
      <div className="panel-title">
        <h2>{title}</h2>
        {link && (
          <Link to={link}>
            View all <ArrowRight size={13} />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}
function CoverageView({ value }: { value: Coverage }) {
  return (
    <div className="coverage">
      <div className="coverage-top">
        <CircleHelp size={19} />
        <div>
          <strong>Telemetry coverage</strong>
          <p>
            {value.complete
              ? "Complete evidence"
              : "Partial evidence · health is not established"}
          </p>
        </div>
        <Badge value={value.status} />
      </div>
      <div className="coverage-grid">
        <div>
          <small>Reporting window</small>
          <p>
            {date(value.window_start)} — {date(value.window_end)}
          </p>
        </div>
        <div>
          <small>Most recent observation</small>
          <p>{date(value.most_recent_observation)}</p>
        </div>
        <div>
          <small>Sources queried</small>
          <p>{value.sources_queried.join(", ") || "None connected"}</p>
        </div>
        <div>
          <small>Evidence</small>
          <p>
            {value.observations} observations · {value.synthetic_observations}{" "}
            synthetic
          </p>
        </div>
      </div>
      {value.missing_telemetry.map((m, i) => (
        <div className="coverage-warning" key={i}>
          <span>!</span>
          {m}
        </div>
      ))}
    </div>
  );
}
function IncidentTable({ items }: { items: Incident[] }) {
  if (!items.length)
    return (
      <Empty title="No incidents in this view">
        New alerts and manually registered incidents will appear here.
      </Empty>
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Incident</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Source</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id}>
              <td>
                <IncidentLink id={i.id} title={i.title} />
                <small className="row-id">INC · {i.id.slice(0, 8)}</small>
              </td>
              <td>
                <Badge value={i.severity} />
              </td>
              <td>
                <Badge value={i.status} />
              </td>
              <td>{i.source}</td>
              <td>{date(i.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Dashboard({ me }: { me: Me }) {
  const query = useAPI<Summary>("/summary");
  const incidents = useAPI<Page<Incident>>("/incidents?limit=5");
  const integrations = useAPI<Page<Integration>>("/integrations");
  const latest = useAPI<DailyReport | null>("/reports/daily");
  return (
    <>
      <Heading
        eyebrow="OPERATIONS AT A GLANCE"
        title="Operations overview"
        description="Understand your systems. Investigate with evidence. Act with approval."
        action={
          <Link className="button secondary" to="/reports">
            <FileText size={15} /> View reports
          </Link>
        }
      />
      <Data query={query}>
        {(s) => (
          <>
            <div className="stats">
              {[
                [
                  Server,
                  "Environments",
                  s.environments,
                  "Registered in your scope",
                ],
                [
                  Activity,
                  "Active incidents",
                  s.active_incidents,
                  "Require investigation",
                ],
                [
                  ShieldCheck,
                  "Pending approvals",
                  s.pending_approvals,
                  "Waiting for a human decision",
                ],
                [
                  CheckCircle2,
                  "Verified actions",
                  s.verified_actions,
                  "Sandbox results verified",
                ],
              ].map(([Icon, label, value, description]) => {
                const I = Icon as typeof Server;
                return (
                  <article className="stat" key={String(label)}>
                    <span>
                      {String(label)}
                      <I size={16} />
                    </span>
                    <strong>{String(value)}</strong>
                    <small>{String(description)}</small>
                  </article>
                );
              })}
            </div>
            <div className="dashboard-grid">
              <Panel title="Incident activity · last 7 days">
                <p className="chart-subtitle">
                  Recorded incidents by day · UTC
                </p>
                <div className="chart">
                  <ResponsiveContainer width="100%" height={210}>
                    <AreaChart data={s.incident_series}>
                      <defs>
                        <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
                          <stop
                            offset="0%"
                            stopColor="#75e3bd"
                            stopOpacity={0.2}
                          />
                          <stop
                            offset="100%"
                            stopColor="#75e3bd"
                            stopOpacity={0}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#263141" vertical={false} />
                      <XAxis
                        dataKey="day"
                        tickFormatter={(v) => String(v).slice(5)}
                        stroke="#718097"
                        fontSize={10}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        allowDecimals={false}
                        stroke="#718097"
                        fontSize={10}
                        axisLine={false}
                        tickLine={false}
                        width={25}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#152130",
                          border: "1px solid #354257",
                          borderRadius: 8,
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="incidents"
                        stroke="#75e3bd"
                        strokeWidth={2}
                        fill="url(#area)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </Panel>
              <Panel title="Control plane status">
                <div className="status-line">
                  <span className="dot" />
                  <span>Approval gate enforced</span>
                  <Badge value="ACTIVE" />
                </div>
                <div className="status-line">
                  <Bot size={14} />
                  <span>AI investigation</span>
                  <Badge
                    value={me.ai_available ? "CONFIGURED" : "UNAVAILABLE"}
                  />
                </div>
                <div className="status-line">
                  <ShieldCheck size={14} />
                  <span>Production mutations</span>
                  <Badge value="DISABLED" />
                </div>
                <div className="callout">
                  {me.ai_available
                    ? "AI findings remain evidence-backed recommendations."
                    : "Connect an AI provider to generate hypotheses. Evidence collection works without one."}
                </div>
              </Panel>
            </div>
            <CoverageView value={s.coverage} />
          </>
        )}
      </Data>
      <Panel title="Recent incidents" link="/incidents">
        <Data query={incidents}>
          {(d) => <IncidentTable items={d.items} />}
        </Data>
      </Panel>
      <div className="dashboard-grid">
        <Panel title="Integration availability" link="/integrations">
          <Data query={integrations}>
            {(d) =>
              d.items.length ? (
                d.items.map((i) => (
                  <div className="list-row" key={i.id}>
                    <div>
                      <strong>{i.name}</strong>
                      <small>
                        {i.provider} · {date(i.last_checked_at)}
                      </small>
                    </div>
                    <Badge value={i.status} />
                  </div>
                ))
              ) : (
                <Empty title="Connect your first source">
                  Add Prometheus, AWS, or a signed alert source.
                </Empty>
              )
            }
          </Data>
        </Panel>
        <Panel title="Latest daily report" link="/reports">
          <Data query={latest}>
            {(r) =>
              r ? (
                <>
                  <small>
                    {date(r.window_start)} — {date(r.window_end)}
                  </small>
                  <h3>{r.data.title}</h3>
                  <p>{r.data.summary}</p>
                  <Link className="text-link" to={`/reports/${r.id}`}>
                    Read report <ArrowRight size={14} />
                  </Link>
                </>
              ) : (
                <Empty title="No report generated">
                  Generate a report or start the scheduler for daily reporting.
                </Empty>
              )
            }
          </Data>
        </Panel>
      </div>
    </>
  );
}

const environmentSchema = z.object({
  name: z.string().min(2).max(160),
  provider: z.enum(["aws", "onprem", "sandbox"]),
  description: z.string().max(2000),
  scope: z.string(),
});
export function Environments({ me }: { me: Me }) {
  const [open, setOpen] = useState(false);
  const query = useAPI<Page<Environment>>("/environments");
  const action = useAction("/environments", () => setOpen(false));
  const form = useForm<z.infer<typeof environmentSchema>>({
    resolver: zodResolver(environmentSchema),
    defaultValues: { name: "", provider: "aws", description: "", scope: "" },
  });
  return (
    <>
      <Heading
        eyebrow="INFRASTRUCTURE"
        title="Environments"
        description="Your cloud and private infrastructure, with explicit resource boundaries."
        action={
          admin(me) && (
            <button onClick={() => setOpen(true)}>
              <Plus size={16} /> Register environment
            </button>
          )
        }
      />
      <Data query={query}>
        {(d) =>
          d.items.length ? (
            <div className="cards">
              {d.items.map((e) => (
                <article className="environment panel" key={e.id}>
                  <div className="environment-top">
                    <div className="provider-icon">
                      <Server size={21} />
                    </div>
                    <Badge value={e.health} />
                  </div>
                  <small>
                    {e.provider.toUpperCase()}
                    {e.demo ? " · DEMO" : ""}
                  </small>
                  <h3>{e.name}</h3>
                  <p>{e.description || "No description provided."}</p>
                  <dl>
                    <dt>Last observation</dt>
                    <dd>{date(e.last_observed_at)}</dd>
                    <dt>Resource scope</dt>
                    <dd>
                      {e.resource_scope.length
                        ? e.resource_scope.join(", ")
                        : "Not configured"}
                    </dd>
                  </dl>
                  <Link className="text-link" to="/integrations">
                    Configure sources <ArrowRight size={13} />
                  </Link>
                </article>
              ))}
            </div>
          ) : (
            <Empty title="No environments registered" />
          )
        }
      </Data>
      {open && (
        <Modal title="Register an environment" onClose={() => setOpen(false)}>
          <form
            onSubmit={form.handleSubmit((v) =>
              action.mutate({
                name: v.name,
                provider: v.provider,
                description: v.description,
                resource_scope: v.scope
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              }),
            )}
          >
            <label>
              Name
              <input {...form.register("name")} />
            </label>
            <label>
              Provider
              <select {...form.register("provider")}>
                <option value="aws">AWS</option>
                <option value="onprem">On premises</option>
                <option value="sandbox">
                  Sandbox (execution disabled unless seeded as demo)
                </option>
              </select>
            </label>
            <label>
              Description
              <textarea {...form.register("description")} />
            </label>
            <label>
              Allowed resource IDs (comma separated)
              <input {...form.register("scope")} />
            </label>
            <p className="muted">
              AWS discovery requires explicit EC2 instance IDs. Registration
              does not provision infrastructure.
            </p>
            {form.formState.errors.name && (
              <p role="alert">{form.formState.errors.name.message}</p>
            )}
            <ErrorBox error={action.error} />
            <button disabled={action.isPending}>Register environment</button>
          </form>
        </Modal>
      )}
    </>
  );
}

const serviceSchema = z.object({
  name: z.string().min(2).max(160),
  environment_id: z.string().uuid(),
  owner: z.string().min(1),
  criticality: z.enum(["low", "medium", "high", "critical"]),
});
export function Services({ me }: { me: Me }) {
  const query = useAPI<Page<Service>>("/services");
  const envs = useAPI<Page<Environment>>("/environments");
  const [open, setOpen] = useState(false);
  const action = useAction("/services", () => setOpen(false));
  const form = useForm<z.infer<typeof serviceSchema>>({
    resolver: zodResolver(serviceSchema),
    defaultValues: { name: "", owner: "Platform", criticality: "medium" },
  });
  return (
    <>
      <Heading
        eyebrow="SERVICE CATALOG"
        title="Services"
        description="Ownership, criticality, and monitoring for your application services."
        action={
          admin(me) && (
            <button onClick={() => setOpen(true)}>
              <Plus size={16} /> Register service
            </button>
          )
        }
      />
      <Panel title="Service inventory">
        <Data query={query}>
          {(d) =>
            d.items.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Service</th>
                      <th>Owner</th>
                      <th>Environment</th>
                      <th>Criticality</th>
                      <th>Health</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((s) => (
                      <tr key={s.id}>
                        <td>
                          <strong>{s.name}</strong>
                        </td>
                        <td>{s.owner}</td>
                        <td>
                          {envs.data?.items.find(
                            (e) => e.id === s.environment_id,
                          )?.name || s.environment_id}
                        </td>
                        <td>
                          <Badge value={s.criticality} />
                        </td>
                        <td>
                          <Badge value={s.health} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No services registered" />
            )
          }
        </Data>
      </Panel>
      {open && (
        <Modal title="Register service" onClose={() => setOpen(false)}>
          <form onSubmit={form.handleSubmit((v) => action.mutate(v))}>
            <label>
              Name
              <input {...form.register("name")} />
            </label>
            <label>
              Environment
              <select {...form.register("environment_id")}>
                <option value="">Select environment</option>
                {envs.data?.items.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Owner
              <input {...form.register("owner")} />
            </label>
            <label>
              Criticality
              <select {...form.register("criticality")}>
                {["low", "medium", "high", "critical"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            {Object.entries(form.formState.errors).map(([key, v]) => (
              <p className="error" key={key}>
                {key}: {v.message}
              </p>
            ))}
            <ErrorBox error={action.error} />
            <button disabled={action.isPending}>Register service</button>
          </form>
        </Modal>
      )}
    </>
  );
}

const incidentSchema = z.object({
  title: z.string().min(3).max(255),
  environment_id: z.string().uuid(),
  severity: z.enum(["low", "medium", "high", "critical"]),
});
export function Incidents({ me }: { me: Me }) {
  const [offset, setOffset] = useState(0);
  const [severity, setSeverity] = useState("");
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const query = useAPI<Page<Incident>>(
    `/incidents?limit=15&offset=${offset}&severity=${severity}`,
  );
  const envs = useAPI<Page<Environment>>("/environments");
  const action = useAction<Incident>("/incidents", (i) =>
    navigate(`/incidents/${i.id}`),
  );
  const synthetic = useAction<Incident>("/sandbox/scenario", (i) =>
    navigate(`/incidents/${i.id}`),
  );
  const form = useForm<z.infer<typeof incidentSchema>>({
    resolver: zodResolver(incidentSchema),
    defaultValues: { title: "", severity: "medium" },
  });
  return (
    <>
      <Heading
        eyebrow="RELIABILITY"
        title="Incidents"
        description="A single evidence trail from first alert through verified recovery."
        action={
          canOperate(me) && (
            <div className="actions">
              {me.demo && (
                <button
                  className="secondary"
                  disabled={synthetic.isPending}
                  onClick={() => synthetic.mutate({})}
                >
                  <Play size={14} /> Ingest synthetic alert
                </button>
              )}
              <button onClick={() => setOpen(true)}>
                <Plus size={15} /> Create incident
              </button>
            </div>
          )
        }
      />
      <ErrorBox error={synthetic.error} />
      <Panel title="Incident queue">
        <div className="filters">
          <label>
            Severity
            <select
              value={severity}
              onChange={(e) => {
                setSeverity(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All severities</option>
              {["critical", "high", "medium", "low"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        </div>
        <Data query={query}>
          {(d) => (
            <>
              <IncidentTable items={d.items} />
              <Pagination page={d} offset={offset} setOffset={setOffset} />
            </>
          )}
        </Data>
      </Panel>
      {open && (
        <Modal title="Create incident" onClose={() => setOpen(false)}>
          <form
            onSubmit={form.handleSubmit((v) =>
              action.mutate({
                ...v,
                source: "manual",
                external_id: crypto.randomUUID(),
                evidence: {},
              }),
            )}
          >
            <label>
              Title
              <input {...form.register("title")} />
            </label>
            <label>
              Environment
              <select {...form.register("environment_id")}>
                <option value="">Select environment</option>
                {envs.data?.items.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Severity
              <select {...form.register("severity")}>
                {["critical", "high", "medium", "low"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            {Object.entries(form.formState.errors).map(([key, v]) => (
              <p className="error" key={key}>
                {key}: {v.message}
              </p>
            ))}
            <ErrorBox error={action.error} />
            <button disabled={action.isPending}>Create incident</button>
          </form>
        </Modal>
      )}
    </>
  );
}

export function IncidentDetails({ me }: { me: Me }) {
  const { id } = useParams();
  const incident = useAPI<Incident>(`/incidents/${id}`);
  const events = useAPI<Page<IncidentEvent>>(`/incidents/${id}/events`);
  const investigations = useAPI<Page<Investigation>>(
    `/incidents/${id}/investigations`,
  );
  const resources = useAPI<Page<Resource>>("/sandbox/resources");
  const proposals = useAPI<Page<Proposal>>("/action-proposals?limit=100");
  const investigate = useAction(`/incidents/${id}/investigations`);
  const propose = useAction(`/incidents/${id}/proposals`, () => setOpen(false));
  const [open, setOpen] = useState(false);
  const [useAI, setUseAI] = useState(true);
  return (
    <>
      <Link className="text-link back" to="/incidents">
        ← All incidents
      </Link>
      <Data query={incident}>
        {(i) => (
          <>
            <Heading
              eyebrow={`INCIDENT · ${i.id.slice(0, 8)}`}
              title={i.title}
              description={`Source: ${i.source} · Owner: ${i.owner} · Opened ${date(i.created_at)}`}
              action={
                <div className="actions">
                  <Badge value={i.severity} />
                  <Badge value={i.status} />
                </div>
              }
            />
            <div className="toolbar">
              <span>
                <ShieldCheck size={14} /> Infrastructure changes require human
                approval.
              </span>
              {canOperate(me) && (
                <div className="actions">
                  <button
                    className="secondary"
                    onClick={() => investigate.mutate({ use_ai: useAI })}
                    disabled={investigate.isPending}
                  >
                    <Bot size={15} /> Collect & investigate
                  </button>
                  <label className="investigation-mode">
                    <input
                      type="checkbox"
                      checked={useAI}
                      onChange={(event) => setUseAI(event.target.checked)}
                    />
                    Use configured AI provider
                  </label>
                  <button
                    onClick={() => setOpen(true)}
                    disabled={!i.evidence.length}
                  >
                    <Plus size={15} /> Propose sandbox recovery
                  </button>
                </div>
              )}
            </div>
            <ErrorBox error={investigate.error} />
            <div className="detail-grid">
              <div>
                <Panel title="Investigation findings">
                  <Data query={investigations}>
                    {(d) =>
                      d.items.length ? (
                        d.items.map((v) => (
                          <article className="finding" key={v.id}>
                            <div className="panel-title">
                              <Badge value={v.status} />
                              <small>{date(v.created_at)}</small>
                            </div>
                            <h3>
                              {v.findings.classification?.replaceAll(
                                "_",
                                " ",
                              ) || "Investigation in progress"}
                            </h3>
                            <p>
                              {v.findings.summary ||
                                v.findings.error_code ||
                                "Waiting for background worker to collect evidence."}
                            </p>
                            {v.findings.confidence !== undefined && (
                              <small>
                                Confidence:{" "}
                                {Math.round(v.findings.confidence * 100)}% ·{" "}
                                {v.findings.evidence_ids?.length || 0} evidence
                                references
                              </small>
                            )}
                            {v.findings.planner && (
                              <div
                                className="callout"
                                aria-label="Investigation limits"
                              >
                                <strong>Bounded investigation</strong>
                                <p>
                                  {v.findings.planner.iterations}/
                                  {v.findings.planner.max_iterations} model
                                  iterations
                                  {" · "}
                                  {v.findings.planner.tool_calls}/
                                  {v.findings.planner.max_tool_calls} read-only
                                  queries
                                  {" · "}
                                  {v.findings.planner.elapsed_seconds}s
                                </p>
                                <small>
                                  Outcome:{" "}
                                  {v.findings.planner.termination_reason.replaceAll(
                                    "_",
                                    " ",
                                  )}
                                </small>
                              </div>
                            )}
                            {v.findings.sources && (
                              <details>
                                <summary>Source coverage and freshness</summary>
                                <div className="table-scroll">
                                  <table>
                                    <thead>
                                      <tr>
                                        <th>Source</th>
                                        <th>Coverage</th>
                                        <th>Records</th>
                                        <th>Latest observation</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {Object.entries(v.findings.sources).map(
                                        ([source, coverage]) => (
                                          <tr key={source}>
                                            <td>
                                              {source}
                                              <small className="row-id">
                                                {coverage.capability}
                                              </small>
                                            </td>
                                            <td>
                                              <Badge value={coverage.status} />
                                            </td>
                                            <td>{coverage.count}</td>
                                            <td>
                                              {date(
                                                coverage.latest_observation,
                                              )}
                                            </td>
                                          </tr>
                                        ),
                                      )}
                                    </tbody>
                                  </table>
                                </div>
                              </details>
                            )}
                            {v.findings.hypotheses?.map((h, index) => (
                              <div className="callout" key={index}>
                                <strong>{h.statement}</strong>
                                <p>
                                  Supporting:{" "}
                                  {h.supporting_evidence.join(", ") || "None"}
                                  <br />
                                  Contradicting:{" "}
                                  {h.contradicting_evidence.join(", ") ||
                                    "None supplied"}
                                </p>
                              </div>
                            ))}
                            {v.findings.missing_data?.map((m, n) => (
                              <p className="muted" key={n}>
                                Missing: {m}
                              </p>
                            ))}
                            {v.findings.next_queries?.map((m, n) => (
                              <p className="muted" key={n}>
                                Next query: {m}
                              </p>
                            ))}
                          </article>
                        ))
                      ) : (
                        <Empty title="No investigation yet">
                          Collect authorized evidence to investigate this
                          incident. AI availability is stated explicitly.
                        </Empty>
                      )
                    }
                  </Data>
                </Panel>
                <Panel title="Evidence references">
                  {i.evidence.length ? (
                    i.evidence.map((e) => (
                      <article className="evidence" key={e.id}>
                        <div className="panel-title">
                          <strong>{e.source}</strong>
                          <Badge value={e.quality} />
                        </div>
                        <small>
                          {date(e.observed_at)} · {e.resource}
                        </small>
                        <pre>{JSON.stringify(e.data, null, 2)}</pre>
                        <code>{e.id}</code>
                      </article>
                    ))
                  ) : (
                    <Empty title="Insufficient evidence">
                      Configure telemetry sources before drawing conclusions.
                    </Empty>
                  )}
                </Panel>
              </div>
              <div>
                <Panel title="Incident timeline">
                  <Data query={events}>
                    {(d) =>
                      d.items.map((e) => (
                        <div className="timeline" key={e.id}>
                          <span className="timeline-dot" />
                          <small>{date(e.created_at)}</small>
                          <h3>{e.message}</h3>
                          <Badge value={e.kind} />
                        </div>
                      ))
                    }
                  </Data>
                </Panel>
                <Panel title="Remediation proposals">
                  <Data query={proposals}>
                    {(d) =>
                      d.items.filter((p) => p.incident_id === i.id).length ? (
                        d.items
                          .filter((p) => p.incident_id === i.id)
                          .map((p) => (
                            <div className="list-row" key={p.id}>
                              <div>
                                <strong>{p.plan.action_type}</strong>
                                <small>{p.id.slice(0, 8)}</small>
                              </div>
                              <Badge value={p.state} />
                            </div>
                          ))
                      ) : (
                        <Empty title="No changes proposed" />
                      )
                    }
                  </Data>
                  <Link className="text-link" to="/approvals">
                    Open approval inbox <ArrowRight size={13} />
                  </Link>
                </Panel>
              </div>
            </div>
            {open && (
              <Modal
                title="Propose sandbox recovery"
                onClose={() => setOpen(false)}
              >
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const v = new FormData(e.currentTarget);
                    const resource = resources.data?.items.find(
                      (r) => r.id === v.get("resource"),
                    );
                    if (resource)
                      propose.mutate({
                        resource_id: resource.id,
                        parameters: { expected_revision: resource.revision },
                        reason: v.get("reason"),
                        evidence_ids: i.evidence.map((e) => e.id).slice(0, 20),
                      });
                  }}
                >
                  <p>
                    This proposes a change to a synthetic database resource. An
                    authorized human must approve the exact plan before
                    execution.
                  </p>
                  <label>
                    Sandbox resource
                    <select name="resource" required>
                      <option value="">Select a resource</option>
                      {resources.data?.items
                        .filter(
                          (r) =>
                            r.environment_id === i.environment_id && !r.healthy,
                        )
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name} · revision {r.revision}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Reason
                    <textarea
                      name="reason"
                      minLength={10}
                      maxLength={2000}
                      defaultValue="Recover the synthetic sandbox resource based on the collected error-rate evidence."
                      required
                    />
                  </label>
                  <small>
                    {i.evidence.length} authorized evidence references will be
                    attached. Expiry: 30 minutes. Risk: low.
                  </small>
                  <ErrorBox error={propose.error} />
                  <button disabled={propose.isPending}>
                    Submit for approval
                  </button>
                </form>
              </Modal>
            )}
          </>
        )}
      </Data>
    </>
  );
}

export function Approvals({ me }: { me: Me }) {
  const [offset, setOffset] = useState(0);
  const query = useAPI<Page<Approval>>(`/approvals?limit=15&offset=${offset}`);
  const [selected, setSelected] = useState<Approval | null>(null);
  const [decision, setDecision] = useState<"APPROVE" | "REJECT">("APPROVE");
  const decide = useAction(`/approvals/${selected?.id}/decision`, () =>
    setSelected(null),
  );
  const [executeId, setExecuteId] = useState("");
  const execution = useAction(`/action-proposals/${executeId}/execute`);
  return (
    <>
      <Heading
        eyebrow="HUMAN IN COMMAND"
        title="Approval inbox"
        description="Review the exact target, evidence, and recovery plan before authorizing a change."
      />
      <div className="security-strip">
        <ShieldCheck size={19} />
        <div>
          <strong>Approval is bound to the exact plan.</strong>
          <p>
            Changed parameters, expired decisions, and duplicate execution are
            rejected by the server.
          </p>
        </div>
      </div>
      <ErrorBox error={execution.error} />
      {execution.isSuccess && (
        <p role="status" className="notice">
          Execution queued. The worker will revalidate approval and
          independently verify the result.
        </p>
      )}
      <Data query={query}>
        {(d) => (
          <>
            {d.items.length ? (
              d.items.map((a) => (
                <article className="panel approval-card" key={a.id}>
                  <div className="panel-title">
                    <div>
                      <div className="eyebrow">
                        {a.proposal.plan.action_type} · PLAN V
                        {a.proposal.plan.version}
                      </div>
                      <h2>{a.proposal.plan.reason}</h2>
                    </div>
                    <Badge value={a.proposal.state} />
                  </div>
                  <div className="approval-grid">
                    <div>
                      <small>Target environment</small>
                      <code>{a.proposal.plan.environment_id}</code>
                    </div>
                    <div>
                      <small>Resource</small>
                      <code>{a.proposal.plan.resource_id}</code>
                    </div>
                    <div>
                      <small>Risk / impact</small>
                      <p>
                        {a.proposal.plan.risk} · {a.proposal.plan.impact}
                      </p>
                    </div>
                    <div>
                      <small>Approval expires</small>
                      <p>{date(a.expires_at)}</p>
                    </div>
                  </div>
                  <div className="plan-description">
                    <div>
                      <strong>Expected effect</strong>
                      <p>{a.proposal.plan.expected_effect}</p>
                    </div>
                    <div>
                      <strong>Parameters</strong>
                      <pre>
                        {JSON.stringify(a.proposal.plan.parameters, null, 2)}
                      </pre>
                    </div>
                    <div>
                      <strong>Verification</strong>
                      <p>{a.proposal.plan.verification}</p>
                    </div>
                    <div>
                      <strong>Recovery strategy</strong>
                      <p>{a.proposal.plan.rollback}</p>
                    </div>
                  </div>
                  <details>
                    <summary>Inspect full canonical plan and evidence</summary>
                    <pre>{JSON.stringify(a.proposal.plan, null, 2)}</pre>
                  </details>
                  <div className="approval-footer">
                    <code title={a.plan_hash}>SHA-256 · {a.plan_hash}</code>
                    <div className="actions">
                      {canApprove(me) &&
                        a.proposal.state === "AWAITING_APPROVAL" &&
                        new Date(a.expires_at) > new Date() && (
                          <>
                            <button
                              className="secondary danger"
                              onClick={() => {
                                setSelected(a);
                                setDecision("REJECT");
                              }}
                            >
                              <X size={14} /> Reject
                            </button>
                            <button
                              onClick={() => {
                                setSelected(a);
                                setDecision("APPROVE");
                              }}
                            >
                              <Check size={15} /> Review & approve
                            </button>
                          </>
                        )}
                      {canOperate(me) && a.proposal.state === "APPROVED" && (
                        <button onClick={() => setExecuteId(a.proposal.id)}>
                          <Play size={14} /> Prepare execution
                        </button>
                      )}
                    </div>
                  </div>
                  {executeId === a.proposal.id &&
                    a.proposal.state === "APPROVED" && (
                      <div className="callout">
                        <p>Execute this exact approved sandbox plan once?</p>
                        <button
                          disabled={execution.isPending}
                          onClick={() => execution.mutate({})}
                        >
                          Confirm sandbox execution
                        </button>
                      </div>
                    )}
                </article>
              ))
            ) : (
              <Empty title="No proposals awaiting review">
                Propose a constrained remediation from an incident to begin.
              </Empty>
            )}
            <Pagination page={d} offset={offset} setOffset={setOffset} />
          </>
        )}
      </Data>
      {selected && (
        <Modal
          title={
            decision === "APPROVE"
              ? "Confirm explicit approval"
              : "Reject this plan"
          }
          onClose={() => setSelected(null)}
        >
          <p>
            You are {decision === "APPROVE" ? "authorizing" : "rejecting"}{" "}
            <strong>{selected.proposal.plan.action_type}</strong> for the exact
            target and parameters shown above.
          </p>
          <dl>
            <dt>Resource</dt>
            <dd>
              <code>{selected.proposal.plan.resource_id}</code>
            </dd>
            <dt>Plan hash</dt>
            <dd>
              <code>{selected.plan_hash}</code>
            </dd>
            <dt>Expiry</dt>
            <dd>{date(selected.expires_at)}</dd>
          </dl>
          <p>
            Approval is single use and valid for at most 15 minutes. It grants
            no authority for any other operation.
          </p>
          <ErrorBox error={decide.error} />
          <button
            disabled={decide.isPending}
            onClick={() =>
              decide.mutate({ decision, plan_hash: selected.plan_hash })
            }
          >
            {decision === "APPROVE"
              ? "I approve this exact plan"
              : "Confirm rejection"}
          </button>
        </Modal>
      )}
    </>
  );
}

export function Deployments() {
  const [offset, setOffset] = useState(0);
  const query = useAPI<Page<Deployment>>(
    `/deployments?limit=20&offset=${offset}`,
  );
  return (
    <>
      <Heading
        eyebrow="CHANGE INTELLIGENCE"
        title="Deployment history"
        description="Workflow events from connected CI/CD providers, correlated with revisions and environments."
      />
      <Panel title="Workflow and deployment events">
        <Data query={query}>
          {(d) => (
            <>
              {d.items.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Workflow</th>
                        <th>Provider</th>
                        <th>Revision</th>
                        <th>Result</th>
                        <th>Observed</th>
                        <th>Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.items.map((r) => (
                        <tr key={r.id}>
                          <td>
                            <strong>{r.workflow}</strong>
                            <small className="row-id">
                              {r.repository} · {r.branch}
                            </small>
                          </td>
                          <td>{r.provider}</td>
                          <td>
                            <code>
                              {r.revision.slice(0, 12) || "Not provided"}
                            </code>
                          </td>
                          <td>
                            <Badge value={r.status} />
                          </td>
                          <td>{date(r.observed_at)}</td>
                          <td>
                            <SafeLink url={r.run_url} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No CI/CD events received">
                  Register GitHub Actions or Jenkins and configure signed
                  webhook delivery.
                </Empty>
              )}
              <Pagination page={d} offset={offset} setOffset={setOffset} />
            </>
          )}
        </Data>
      </Panel>
    </>
  );
}

export function Reports({ me }: { me: Me }) {
  const [offset, setOffset] = useState(0);
  const query = useAPI<Page<DailyReport>>(`/reports?limit=15&offset=${offset}`);
  const [day, setDay] = useState("");
  const action = useAction("/reports/generate");
  return (
    <>
      <Heading
        eyebrow="DAILY OPERATIONS"
        title="Operations reports"
        description="Durable daily summaries with evidence coverage, action outcomes, and delivery status."
        action={
          canOperate(me) && (
            <div className="actions">
              <label className="sr-only" htmlFor="report-day">
                Report date (blank for previous operational day)
              </label>
              <input
                id="report-day"
                type="date"
                value={day}
                onChange={(e) => setDay(e.target.value)}
              />
              <button
                disabled={action.isPending}
                onClick={() => action.mutate({ day: day || null })}
              >
                <Plus size={15} /> Generate report
              </button>
            </div>
          )
        }
      />
      <ErrorBox error={action.error} />
      {action.isSuccess && (
        <p className="notice" role="status">
          Report generation queued. Start the worker and scheduler if the report
          does not appear.
        </p>
      )}
      <Panel title="Report history">
        <Data query={query}>
          {(d) => (
            <>
              {d.items.length ? (
                d.items.map((r) => (
                  <div className="report-row" key={r.id}>
                    <div className="report-icon">
                      <FileText size={23} />
                    </div>
                    <div>
                      <Link className="text-link" to={`/reports/${r.id}`}>
                        {r.data.title} · {date(r.window_start)}
                      </Link>
                      <p>{r.data.summary}</p>
                      <small>
                        {date(r.window_start)} — {date(r.window_end)} ·{" "}
                        {r.data.timezone}
                      </small>
                    </div>
                    <Badge value={r.data.coverage.status} />
                    <Link
                      className="icon"
                      aria-label="Open report"
                      to={`/reports/${r.id}`}
                    >
                      <ArrowRight size={17} />
                    </Link>
                  </div>
                ))
              ) : (
                <Empty title="No reports generated">
                  Leave the date blank to report on the previous operational
                  day. Reports persist independently of email delivery.
                </Empty>
              )}
              <Pagination page={d} offset={offset} setOffset={setOffset} />
            </>
          )}
        </Data>
      </Panel>
    </>
  );
}
export function ReportDetails() {
  const { id } = useParams();
  const query = useAPI<DailyReport>(`/reports/${id}`);
  return (
    <>
      <Link className="text-link back" to="/reports">
        ← Report history
      </Link>
      <Data query={query}>
        {(r) => (
          <>
            <Heading
              eyebrow="DAILY OPERATIONS REPORT"
              title={r.data.title}
              description={`${date(r.window_start)} — ${date(r.window_end)} · ${r.data.timezone}`}
            />
            <Panel title="Executive summary">
              <p>{r.data.summary}</p>
              <div className="inline-stats">
                <span>
                  <strong>{r.data.unresolved_incidents_snapshot}</strong>{" "}
                  unresolved incidents at snapshot
                </span>
                <span>
                  <strong>{r.data.pending_approvals_snapshot}</strong> pending
                  approvals at snapshot
                </span>
              </div>
            </Panel>
            <CoverageView value={r.data.coverage} />
            <Panel title="Incidents and findings">
              {r.data.incidents.length ? (
                r.data.incidents.map((i) => (
                  <div className="list-row" key={i.id}>
                    <IncidentLink id={i.id} title={i.title} />
                    <Badge value={i.severity} />
                    <Badge value={i.status} />
                  </div>
                ))
              ) : (
                <p>
                  No incident was first observed in this reporting window.
                  Coverage limitations still apply.
                </p>
              )}
              {r.data.findings.map((f, i) => (
                <div className="finding" key={i}>
                  <Badge value={f.status} />
                  <p>{f.findings.summary || f.findings.error_code}</p>
                </div>
              ))}
            </Panel>
            <div className="dashboard-grid">
              <Panel title="Executions and verification">
                {r.data.executions.length ? (
                  r.data.executions.map((e) => (
                    <div className="list-row" key={e.proposal_id}>
                      <code>{e.proposal_id.slice(0, 8)}</code>
                      <Badge value={e.status} />
                    </div>
                  ))
                ) : (
                  <p>No execution recorded in the window.</p>
                )}
                <p>{r.data.slo_assessment}</p>
                <p>{r.data.infrastructure_trends}</p>
              </Panel>
              <Panel title="Email delivery">
                {r.deliveries?.length ? (
                  r.deliveries.map((d) => (
                    <div className="list-row" key={d.id}>
                      <div>
                        <Badge value={d.status} />
                        <p>
                          {d.attempts} attempts ·{" "}
                          {d.error_code || "No delivery error"}
                        </p>
                      </div>
                    </div>
                  ))
                ) : (
                  <p>
                    No email delivery requested. Configure SMTP and a recipient
                    to enable delivery.
                  </p>
                )}
                <h3>Follow-up</h3>
                {r.data.follow_up.map((f, i) => (
                  <p key={i}>• {f}</p>
                ))}
              </Panel>
            </div>
          </>
        )}
      </Data>
    </>
  );
}

const integrationSchema = z.object({
  name: z.string().min(2),
  environment_id: z.string().uuid(),
  provider: z.enum([
    "aws",
    "prometheus",
    "grafana",
    "github",
    "jenkins",
    "alertmanager",
  ]),
  url: z.string(),
  region: z.string().min(1),
  repository: z.string(),
  query: z.string(),
  username: z.string(),
  secret_ref: z.string().regex(/^$|^ATLAS_SECRET_[A-Z0-9_]{1,80}$/),
});
function TestIntegration({ id }: { id: string }) {
  const action = useAction<{ status: string; error_code: string | null }>(
    `/integrations/${id}/test`,
  );
  return (
    <div>
      <button
        className="secondary compact"
        disabled={action.isPending}
        onClick={() => action.mutate({})}
      >
        <RefreshCw size={12} /> Test connection
      </button>
      <ErrorBox error={action.error} />
      {action.data && (
        <small className="test-result">
          {action.data.status}
          {action.data.error_code ? `: ${action.data.error_code}` : ""}
        </small>
      )}
    </div>
  );
}
export function Integrations({ me }: { me: Me }) {
  const query = useAPI<Page<Integration>>("/integrations");
  const envs = useAPI<Page<Environment>>("/environments");
  const [open, setOpen] = useState(false);
  const action = useAction("/integrations", () => setOpen(false));
  const form = useForm<z.infer<typeof integrationSchema>>({
    resolver: zodResolver(integrationSchema),
    defaultValues: {
      name: "",
      provider: "prometheus",
      url: "",
      region: "us-east-1",
      repository: "",
      query: "up",
      username: "",
      secret_ref: "",
    },
  });
  return (
    <>
      <Heading
        eyebrow="CONNECTED SYSTEMS"
        title="Integrations"
        description="Connect existing systems with read-only capabilities and least-privilege credentials."
        action={
          admin(me) && (
            <button onClick={() => setOpen(true)}>
              <Plus size={15} /> Add integration
            </button>
          )
        }
      />
      <div className="callout">
        <strong>Credentials stay on the server.</strong>
        <p>
          Configure secret references through secure runtime settings.
          Integration forms accept reference names, never credential values.
          Destinations must be allowed by the deployment operator.
        </p>
      </div>
      <Data query={query}>
        {(d) =>
          d.items.length ? (
            <div className="cards">
              {d.items.map((i) => (
                <article className="panel integration" key={i.id}>
                  <div className="panel-title">
                    <div className="provider-icon">
                      {i.provider === "aws" ? (
                        <Server size={20} />
                      ) : i.provider === "github" ||
                        i.provider === "jenkins" ? (
                        <GitBranch size={20} />
                      ) : (
                        <Activity size={20} />
                      )}
                    </div>
                    <Badge value={i.status} />
                  </div>
                  <small>{i.provider.toUpperCase()}</small>
                  <h3>{i.name}</h3>
                  <p>
                    {
                      envs.data?.items.find((e) => e.id === i.environment_id)
                        ?.name
                    }
                  </p>
                  <div className="capabilities">
                    {i.capabilities.map((c) => (
                      <code key={c}>{c}</code>
                    ))}
                  </div>
                  <dl>
                    <dt>Last checked</dt>
                    <dd>{date(i.last_checked_at)}</dd>
                    <dt>Credential reference</dt>
                    <dd>
                      {i.credential_configured
                        ? "Configured"
                        : "Not set / workload identity"}
                    </dd>
                  </dl>
                  {i.error_code && <p className="error">{i.error_code}</p>}
                  {admin(me) && <TestIntegration id={i.id} />}
                </article>
              ))}
            </div>
          ) : (
            <Empty title="No integrations connected">
              Register a source to start collecting authorized telemetry.
            </Empty>
          )
        }
      </Data>
      {open && (
        <Modal title="Add read-only integration" onClose={() => setOpen(false)}>
          <form
            onSubmit={form.handleSubmit((v) =>
              action.mutate({
                name: v.name,
                provider: v.provider,
                environment_id: v.environment_id,
                secret_ref: v.secret_ref || null,
                config: {
                  url: v.url,
                  region: v.region,
                  repository: v.repository,
                  query: v.query,
                  username: v.username,
                },
              }),
            )}
          >
            <label>
              Name
              <input {...form.register("name")} />
            </label>
            <label>
              Environment
              <select {...form.register("environment_id")}>
                <option value="">Select environment</option>
                {envs.data?.items.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Provider
              <select {...form.register("provider")}>
                {[
                  "prometheus",
                  "aws",
                  "grafana",
                  "github",
                  "jenkins",
                  "alertmanager",
                ].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
            <label>
              Base URL (operator allowlist required)
              <input
                {...form.register("url")}
                placeholder="https://monitoring.example.com"
              />
            </label>
            <label>
              AWS region
              <input {...form.register("region")} />
            </label>
            <label>
              GitHub repository
              <input
                {...form.register("repository")}
                placeholder="owner/repository"
              />
            </label>
            <label>
              Prometheus query
              <input {...form.register("query")} />
            </label>
            <label>
              Jenkins username
              <input {...form.register("username")} />
            </label>
            <label>
              Secret reference (optional)
              <input
                {...form.register("secret_ref")}
                placeholder="ATLAS_SECRET_MONITORING"
              />
            </label>
            {Object.entries(form.formState.errors).map(([key, v]) => (
              <p className="error" key={key}>
                {key}: {v.message}
              </p>
            ))}
            <ErrorBox error={action.error} />
            <button disabled={action.isPending}>Register integration</button>
          </form>
        </Modal>
      )}
    </>
  );
}
export function Audit() {
  const [offset, setOffset] = useState(0);
  const query = useAPI<
    Page<{
      id: string;
      kind: string;
      actor_id: string;
      object_id: string;
      created_at: string;
      data: Record<string, unknown>;
    }>
  >(`/audit-events?limit=25&offset=${offset}`);
  return (
    <>
      <Heading
        eyebrow="ACCOUNTABILITY"
        title="Audit trail"
        description="Security-relevant decisions and execution results, retained in the operational database."
      />
      <Panel title="Audit events">
        <Data query={query}>
          {(d) => (
            <>
              {d.items.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Event</th>
                        <th>Actor</th>
                        <th>Object</th>
                        <th>Timestamp</th>
                        <th>Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.items.map((e) => (
                        <tr key={e.id}>
                          <td>{e.kind}</td>
                          <td>
                            <code>{e.actor_id.slice(0, 12)}</code>
                          </td>
                          <td>
                            <code>{e.object_id.slice(0, 12)}</code>
                          </td>
                          <td>{date(e.created_at)}</td>
                          <td>
                            <details>
                              <summary>Inspect</summary>
                              <pre>{JSON.stringify(e.data, null, 2)}</pre>
                            </details>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No audit events" />
              )}
              <Pagination page={d} offset={offset} setOffset={setOffset} />
            </>
          )}
        </Data>
      </Panel>
      <p className="muted">
        The API does not expose audit modification. Database operators retain
        privileged access; use externally retained append-only storage for
        stronger integrity guarantees.
      </p>
    </>
  );
}
