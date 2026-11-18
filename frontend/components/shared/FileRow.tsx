import React from "react";
import { Download, Trash, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge, StatusType } from "@/components/shared/StatusBadge";

export interface FileItem {
  id: string;
  name: string;
  sizeBytes: number;
  uploadedAt: string;
  status: StatusType;
  errorMessage?: string;
}

interface FileRowProps {
  file: FileItem;
  isTeacher?: boolean;
  onDownload?: (file: FileItem) => void;
  onDelete?: (file: FileItem) => void;
  onRetry?: (file: FileItem) => void;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function FileRow({
  file,
  isTeacher = false,
  onDownload,
  onDelete,
  onRetry,
}: FileRowProps) {
  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border px-4 py-2 hover:bg-panel transition-colors text-sm gap-2">
      <div className="flex flex-wrap items-center gap-2 md:gap-3 min-w-0 flex-1">
        <span className="font-medium text-text truncate max-w-full">{file.name}</span>
        <span className="shrink-0 text-xs text-text-muted">{formatBytes(file.sizeBytes)}</span>
        <span className="shrink-0 text-xs text-text-muted">{file.uploadedAt}</span>
        {isTeacher && <StatusBadge status={file.status} />}
        {isTeacher && file.status === "failed" && file.errorMessage && (
          <span className="text-xs text-danger" title={file.errorMessage}>
            {file.errorMessage}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1 shrink-0 self-end md:self-auto">
        {file.status === "ready" && onDownload && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDownload(file)}
            aria-label={`Download ${file.name}`}
            className="gap-1.5 text-xs"
          >
            <Download className="h-4 w-4" strokeWidth={1.5} />
            Download
          </Button>
        )}

        {isTeacher && file.status === "failed" && onRetry && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onRetry(file)}
            aria-label={`Retry ${file.name}`}
            className="gap-1.5 text-xs text-text"
          >
            <RotateCcw className="h-4 w-4" strokeWidth={1.5} />
            Retry
          </Button>
        )}

        {isTeacher && onDelete && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(file)}
            aria-label={`Delete ${file.name}`}
            className="text-text-muted hover:text-danger"
          >
            <Trash className="h-4 w-4" strokeWidth={1.5} />
          </Button>
        )}
      </div>
    </div>
  );
}
