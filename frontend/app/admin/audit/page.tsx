"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { AppShell } from "@/components/shared/AppShell";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Search, RefreshCw, ChevronLeft, ChevronRight, AlertCircle, Info } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface AuditLogItem {
  id: string;
  user_id: string | null;
  user_email: string | null;
  user_role: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  ip: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

interface AuditLogResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: AuditLogItem[];
}

export default function AdminAuditPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();

  const [logs, setLogs] = React.useState<AuditLogItem[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(1);
  const [totalPages, setTotalPages] = React.useState(1);
  const [pageSize] = React.useState(25);
  const [loading, setLoading] = React.useState(true);

  // Filters
  const [search, setSearch] = React.useState("");
  const [actionFilter, setActionFilter] = React.useState("");
  const [expandedId, setExpandedId] = React.useState<string | null>(null);

  const fetchAuditLogs = React.useCallback(
    async (currentPage = 1, currentSearch = search, currentAction = actionFilter) => {
      try {
        setLoading(true);
        const params = new URLSearchParams();
        params.set("page", currentPage.toString());
        params.set("page_size", pageSize.toString());
        if (currentSearch.trim()) {
          params.set("search", currentSearch.trim());
        }
        if (currentAction.trim()) {
          params.set("action", currentAction.trim());
        }

        const data = await apiFetch<AuditLogResponse>(`/admin/audit-logs?${params.toString()}`);
        setLogs(data.items);
        setTotal(data.total);
        setPage(data.page);
        setTotalPages(data.total_pages);
      } catch (err: unknown) {
        if (err instanceof Error) {
          toast.error(err.message);
        }
      } finally {
        setLoading(false);
      }
    },
    [pageSize, search, actionFilter]
  );

  React.useEffect(() => {
    if (!authLoading && user) {
      if (user.role !== "admin") {
        router.push("/courses");
        return;
      }
      fetchAuditLogs(1);
    }
  }, [authLoading, user, router, fetchAuditLogs]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchAuditLogs(1, search, actionFilter);
  };

  const handleActionChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setActionFilter(val);
    fetchAuditLogs(1, search, val);
  };

  const formatDate = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleString("en-US", {
        month: "short",
        day: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    } catch {
      return isoStr;
    }
  };

  const getActionBadgeClass = (action: string) => {
    const act = action.toLowerCase();
    if (act.includes("delete")) {
      return "bg-danger-bg text-danger border-danger/20";
    }
    if (act.includes("upload") || act.includes("restore")) {
      return "bg-success-bg text-success border-success/20";
    }
    if (act.includes("join") || act.includes("review")) {
      return "bg-warning-bg text-warning border-warning/20";
    }
    if (act.includes("auth") || act.includes("login") || act.includes("register")) {
      return "bg-primary/5 text-primary border-primary/20";
    }
    return "bg-panel text-text border-border";
  };

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg text-text-muted text-sm font-mono">
        Loading...
      </div>
    );
  }

  if (user && user.role !== "admin") {
    return (
      <AppShell userEmail={user.email} userRole={user.role} onSignOut={logout}>
        <div className="max-w-[700px] mx-auto mt-12 p-6 rounded-md border border-border bg-panel text-center space-y-4">
          <AlertCircle className="h-8 w-8 text-danger mx-auto" strokeWidth={1.5} />
          <h2 className="text-lg font-semibold text-text">Access Denied</h2>
          <p className="text-sm text-text-muted">
            The Audit Log console is restricted exclusively to system administrators.
          </p>
          <Button variant="secondary" onClick={() => router.push("/courses")}>
            Return to Courses
          </Button>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell userEmail={user?.email} userRole={user?.role} onSignOut={logout}>
      <div className="space-y-6">
        <PageHeader
          title="Audit Logs"
          description="Inspect system activity, authentication events, and course material modifications."
          action={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => fetchAuditLogs(page, search, actionFilter)}
              disabled={loading}
              className="gap-2 text-xs"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} strokeWidth={1.5} />
              Refresh
            </Button>
          }
        />

        {/* Filter Controls Bar */}
        <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between p-3.5 rounded-md border border-border bg-panel">
          <form onSubmit={handleSearchSubmit} className="flex-1 flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-muted" strokeWidth={1.5} />
              <input
                type="text"
                placeholder="Filter by user email, target ID, or action..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border border-border bg-bg text-text focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <Button type="submit" variant="secondary" size="sm" className="text-xs h-8">
              Search
            </Button>
          </form>

          <div className="flex items-center gap-2">
            <label htmlFor="action-filter-select" className="text-xs text-text-muted shrink-0">Action:</label>
            <select
              id="action-filter-select"
              aria-label="Filter by action"
              value={actionFilter}
              onChange={handleActionChange}
              className="py-1.5 px-2.5 text-xs rounded-md border border-border bg-bg text-text focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">All Actions</option>
              <option value="auth.login">auth.login</option>
              <option value="auth.register">auth.register</option>
              <option value="auth.logout">auth.logout</option>
              <option value="FILE_UPLOAD">FILE_UPLOAD</option>
              <option value="FILE_DOWNLOAD">FILE_DOWNLOAD</option>
              <option value="FILE_DELETE">FILE_DELETE</option>
              <option value="FILE_RESTORE">FILE_RESTORE</option>
              <option value="create_teacher">create_teacher</option>
              <option value="course.join_request">course.join_request</option>
              <option value="course.review_request">course.review_request</option>
            </select>
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="rounded-md border border-border bg-panel overflow-hidden">
          {logs.length === 0 && !loading ? (
            <div className="p-6">
              <EmptyState message="No audit events found matching the selected search criteria or filter." />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-border bg-bg/50 text-text-muted">
                    <th className="py-2.5 px-3 font-medium">Timestamp</th>
                    <th className="py-2.5 px-3 font-medium">Action</th>
                    <th className="py-2.5 px-3 font-medium">Actor</th>
                    <th className="py-2.5 px-3 font-medium">Target</th>
                    <th className="py-2.5 px-3 font-medium">Client IP</th>
                    <th className="py-2.5 px-3 font-medium text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {logs.map((item) => {
                    const isExpanded = expandedId === item.id;
                    return (
                      <React.Fragment key={item.id}>
                        <tr className="hover:bg-bg/40 transition-colors">
                          <td className="py-2.5 px-3 font-mono text-[11px] text-text-muted whitespace-nowrap">
                            {formatDate(item.created_at)}
                          </td>
                          <td className="py-2.5 px-3 whitespace-nowrap">
                            <span
                              className={cn(
                                "inline-flex items-center px-1.5 py-0.5 rounded-[4px] text-[11px] font-medium border",
                                getActionBadgeClass(item.action)
                              )}
                            >
                              {item.action}
                            </span>
                          </td>
                          <td className="py-2.5 px-3">
                            <div className="flex flex-col">
                              <span className="font-medium text-text truncate max-w-[180px]">
                                {item.user_email || "System / Anonymous"}
                              </span>
                              {item.user_role && (
                                <span className="text-[10px] text-text-muted capitalize">
                                  {item.user_role}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-2.5 px-3">
                            {item.target_type ? (
                              <div className="flex items-center gap-1.5">
                                <span className="text-[11px] text-text-muted uppercase font-medium">
                                  {item.target_type}:
                                </span>
                                <span className="font-mono text-[11px] text-text truncate max-w-[120px]" title={item.target_id || ""}>
                                  {item.target_id ? item.target_id.slice(0, 8) + "..." : "—"}
                                </span>
                              </div>
                            ) : (
                              <span className="text-text-muted">—</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-[11px] text-text-muted whitespace-nowrap">
                            {item.ip || "—"}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {item.metadata ? (
                              <button
                                type="button"
                                onClick={() => setExpandedId(isExpanded ? null : item.id)}
                                className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                              >
                                <Info className="h-3 w-3" strokeWidth={1.5} />
                                {isExpanded ? "Hide" : "View"}
                              </button>
                            ) : (
                              <span className="text-[11px] text-text-muted">—</span>
                            )}
                          </td>
                        </tr>
                        {isExpanded && item.metadata && (
                          <tr className="bg-bg/60">
                            <td colSpan={6} className="p-3">
                              <div className="p-2.5 rounded border border-border bg-panel space-y-1">
                                <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider block">
                                  Event Metadata & Payload
                                </span>
                                <pre className="font-mono text-[11px] text-text overflow-x-auto whitespace-pre-wrap leading-relaxed">
                                  {JSON.stringify(item.metadata, null, 2)}
                                </pre>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination Footer */}
          <div className="flex items-center justify-between px-3.5 py-2.5 border-t border-border bg-bg/30 text-xs text-text-muted">
            <div>
              Showing {logs.length} of {total} {total === 1 ? "entry" : "entries"}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px]">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="secondary"
                size="icon"
                className="h-7 w-7"
                onClick={() => fetchAuditLogs(page - 1)}
                disabled={page <= 1 || loading}
                aria-label="Previous page"
              >
                <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
              </Button>
              <Button
                variant="secondary"
                size="icon"
                className="h-7 w-7"
                onClick={() => fetchAuditLogs(page + 1)}
                disabled={page >= totalPages || loading}
                aria-label="Next page"
              >
                <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.5} />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
