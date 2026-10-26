import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bell,
  BookOpen,
  Cable,
  ChevronRight,
  FileText,
  GitBranch,
  Layers3,
  LayoutDashboard,
  LogOut,
  Server,
  ShieldCheck,
} from "lucide-react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, setToken, type Me } from "./api";
import {
  Dashboard,
  Environments,
  Services,
  Incidents,
  IncidentDetails,
  Approvals,
  Deployments,
  Reports,
  ReportDetails,
  Integrations,
  Audit,
} from "./pages";
import { date, ErrorBox, useAPI } from "./ui";

function Login({ done }: { done: () => void }) {
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <main className="login">
      <div className="brand">
        <Layers3 /> AtlasOps <span>AI</span>
      </div>
      <div className="eyebrow login-eyebrow">YOUR OPERATIONS, IN FOCUS</div>
      <h1>
        Clarity in every
        <br />
        critical moment.
      </h1>
      <p>
        Evidence-driven investigations.
        <br />
        Human-approved actions.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          const form = new FormData(e.currentTarget);
          try {
            const r = await api<{ access_token: string }>(
              "/auth/dev-token",
              "POST",
              { email: form.get("email"), secret: form.get("secret") },
            );
            setToken(r.access_token);
            done();
          } catch (e) {
            setError(e as Error);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>Development sign in</h2>
        <label>
          Email
          <input
            name="email"
            type="email"
            defaultValue="administrator@atlasops.local"
            autoComplete="username"
            required
          />
        </label>
        <label>
          Development secret
          <input
            name="secret"
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        <ErrorBox error={error} />
        <button disabled={busy}>
          {busy ? "Signing in…" : "Enter workspace"}
          <ChevronRight size={16} />
        </button>
        <small>
          Requires development mode and a locally configured secret.
        </small>
      </form>
      <details className="oidc">
        <summary>Sign in with an OIDC access token</summary>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const value = new FormData(e.currentTarget)
              .get("token")
              ?.toString();
            if (value) {
              setToken(value);
              done();
            }
          }}
        >
          <label>
            Access token
            <input name="token" type="password" required />
          </label>
          <button>Continue with token</button>
        </form>
      </details>
    </main>
  );
}

const links = [
  ["/", "Overview", LayoutDashboard],
  ["/environments", "Environments", Server],
  ["/services", "Services", Layers3],
  ["/incidents", "Incidents", Activity],
  ["/approvals", "Approval inbox", ShieldCheck],
  ["/deployments", "Deployments", GitBranch],
  ["/reports", "Daily reports", FileText],
  ["/integrations", "Integrations", Cable],
  ["/audit", "Audit trail", BookOpen],
] as const;
export default function App() {
  const cache = useQueryClient();
  const [logged, setLogged] = useState(
    !!sessionStorage.getItem("atlasops-token"),
  );
  useEffect(() => {
    const reset = () => {
      setLogged(false);
      cache.clear();
    };
    window.addEventListener("atlasops-unauthorized", reset);
    return () => window.removeEventListener("atlasops-unauthorized", reset);
  }, [cache]);
  if (!logged) return <Login done={() => setLogged(true)} />;
  return (
    <Workspace
      logout={() => {
        setToken("");
        setLogged(false);
        cache.clear();
      }}
    />
  );
}
function Workspace({ logout }: { logout: () => void }) {
  const me = useAPI<Me>("/me", 30000);
  const location = useLocation();
  const section =
    links.find(([path]) =>
      path === "/"
        ? location.pathname === "/"
        : location.pathname.startsWith(path),
    )?.[1] || "Workspace";
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <Layers3 /> AtlasOps <span>AI</span>
        </div>
        <div className="workspace">OPERATIONS WORKSPACE</div>
        <nav>
          {links
            .filter(
              ([path]) => path != "/audit" || me.data?.role === "administrator",
            )
            .map(([path, label, Icon]) => (
              <NavLink end={path === "/"} key={path} to={path}>
                <Icon size={17} />
                {label}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-policy">
          <ShieldCheck size={18} />
          <strong>Human in command</strong>
          <p>Every infrastructure change requires explicit approval.</p>
        </div>
        <footer>
          <div>
            <span className="dot" /> API authentication active
          </div>
          <div className="profile">
            <span className="avatar">{me.data?.email[0]?.toUpperCase()}</span>
            <div>
              <strong>{me.data?.role}</strong>
              <small>{me.data?.email}</small>
            </div>
            <button className="icon" aria-label="Sign out" onClick={logout}>
              <LogOut size={15} />
            </button>
          </div>
        </footer>
      </aside>
      <main className="content">
        <header>
          <span>
            <span className="muted">Workspace</span>
            <ChevronRight size={12} />
            {section}
          </span>
          <span>
            <Bell size={15} />
            <span className="timezone">
              {date(new Date().toISOString())} IST
            </span>
          </span>
        </header>
        {me.data?.demo && (
          <div className="demo">
            <span>DEMO WORKSPACE</span> Synthetic sandbox data · external
            infrastructure must be connected separately.
          </div>
        )}
        <ErrorBox error={me.error} />
        {me.data && (
          <Routes>
            <Route path="/" element={<Dashboard me={me.data} />} />
            <Route
              path="/environments"
              element={<Environments me={me.data} />}
            />
            <Route path="/services" element={<Services me={me.data} />} />
            <Route path="/incidents" element={<Incidents me={me.data} />} />
            <Route
              path="/incidents/:id"
              element={<IncidentDetails me={me.data} />}
            />
            <Route path="/approvals" element={<Approvals me={me.data} />} />
            <Route path="/deployments" element={<Deployments />} />
            <Route path="/reports" element={<Reports me={me.data} />} />
            <Route path="/reports/:id" element={<ReportDetails />} />
            <Route
              path="/integrations"
              element={<Integrations me={me.data} />}
            />
            <Route path="/audit" element={<Audit />} />
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        )}
        <div className="page-footer">
          <span>ATLASOPS AI · CONTROL PLANE</span>
          <span>Evidence first. Approval always.</span>
        </div>
      </main>
    </div>
  );
}
