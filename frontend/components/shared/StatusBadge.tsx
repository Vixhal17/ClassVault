import React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusType = "queued" | "processing" | "ready" | "failed" | "pending";

interface StatusBadgeProps {
  status: StatusType;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  switch (status) {
    case "queued":
      return (
        <span
          className={cn(
            "inline-flex items-center rounded-sm bg-panel px-2 py-0.5 text-xs font-medium text-text-muted border border-border",
            className
          )}
        >
          Queued
        </span>
      );
    case "processing":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-sm bg-panel px-2 py-0.5 text-xs font-medium text-text-muted border border-border",
            className
          )}
        >
          <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.5} />
          Processing
        </span>
      );
    case "ready":
      return (
        <span
          className={cn(
            "inline-flex items-center rounded-sm bg-success-bg px-2 py-0.5 text-xs font-medium text-success border border-success/20",
            className
          )}
        >
          Ready
        </span>
      );
    case "failed":
      return (
        <span
          className={cn(
            "inline-flex items-center rounded-sm bg-danger-bg px-2 py-0.5 text-xs font-medium text-danger border border-danger/20",
            className
          )}
        >
          Failed
        </span>
      );
    case "pending":
      return (
        <span
          className={cn(
            "inline-flex items-center rounded-sm bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning border border-warning/20",
            className
          )}
        >
          Pending
        </span>
      );
  }
}
