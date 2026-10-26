import { useEffect, useRef, useId, type ReactNode } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, type Page } from "./api";

export function useAPI<T>(path: string, interval = 10000) {
  return useQuery({
    queryKey: [path],
    queryFn: () => api<T>(path),
    refetchInterval: interval,
  });
}
export function useAction<T = unknown>(
  path: string,
  onSuccess?: (data: T) => void,
) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (body: unknown) => api<T>(path, "POST", body),
    onSuccess: (data) => {
      void cache.invalidateQueries();
      onSuccess?.(data);
    },
  });
}
export function date(value: string | null | undefined) {
  if (!value) return "Not observed";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}
export function Badge({ value }: { value: string }) {
  const good = [
    "SUCCEEDED",
    "CONNECTED",
    "APPROVED",
    "RESOLVED",
    "SENT",
    "COMPLETED",
  ];
  const bad = [
    "FAILED",
    "CRITICAL",
    "HIGH",
    "REJECTED",
    "UNAVAILABLE",
    "RECONCILIATION_REQUIRED",
  ];
  return (
    <span
      className={`badge ${good.includes(value.toUpperCase()) ? "good" : bad.includes(value.toUpperCase()) ? "bad" : ""}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}
export function Heading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>
          {title}
          <span className="dot" />
        </h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function ErrorBox({ error }: { error: Error | null | undefined }) {
  return error ? (
    <div role="alert" className="error">
      <AlertCircle size={16} />
      {error.message}
    </div>
  ) : null;
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={17} /> Loading operational data…
      <div className="skeleton" />
      <div className="skeleton" />
    </div>
  );
}
export function Data<T>({
  query,
  children,
}: {
  query: UseQueryResult<T, Error>;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorBox error={query.error} />;
  return <>{children(query.data)}</>;
}
export function Empty({
  title = "No records yet",
  children,
}: {
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">◈</div>
      <h3>{title}</h3>
      <p>
        {children ||
          "Connect an authorized source or create a record to begin."}
      </p>
    </div>
  );
}
export function Pagination({
  page,
  offset,
  setOffset,
}: {
  page: Page<unknown>;
  offset: number;
  setOffset: (n: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {page.total === 0 ? "0" : offset + 1}–
        {Math.min(offset + page.limit, page.total)} of {page.total}
      </span>
      <button
        className="secondary compact"
        aria-label="Previous page"
        disabled={offset === 0}
        onClick={() => setOffset(Math.max(0, offset - page.limit))}
      >
        <ChevronLeft size={14} />
      </button>
      <button
        className="secondary compact"
        aria-label="Next page"
        disabled={offset + page.limit >= page.total}
        onClick={() => setOffset(offset + page.limit)}
      >
        <ChevronRight size={14} />
      </button>
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const titleId = useId();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog ref={ref} aria-labelledby={titleId} onCancel={onClose}>
      <div className="dialog-heading">
        <h2 id={titleId}>{title}</h2>
        <button className="icon" onClick={onClose} aria-label="Close dialog">
          ✕
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function SafeLink({
  url,
  label = "View run",
}: {
  url: string;
  label?: string;
}) {
  try {
    const parsed = new URL(url);
    if (!["https:", "http:"].includes(parsed.protocol)) return null;
    return (
      <a
        className="text-link"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {label}
        <ArrowUpRight size={12} />
      </a>
    );
  } catch {
    return null;
  }
}
export function IncidentLink({ id, title }: { id: string; title: string }) {
  return (
    <Link className="text-link" to={`/incidents/${id}`}>
      {title}
      <ArrowUpRight size={12} />
    </Link>
  );
}
