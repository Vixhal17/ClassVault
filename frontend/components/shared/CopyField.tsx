"use client";

import * as React from "react";
import { Copy, RefreshCw, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

interface CopyFieldProps {
  value: string;
  onRotate?: () => void;
  isRotating?: boolean;
}

export function CopyField({ value, onRotate, isRotating = false }: CopyFieldProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <div className="flex items-center gap-2">
      <div className="flex h-[36px] max-md:h-[44px] items-center rounded border border-border bg-panel px-3 font-mono text-sm tracking-wide text-text select-all">
        {value}
      </div>
      <Button
        variant="secondary"
        size="sm"
        onClick={handleCopy}
        aria-label="Copy join code"
        className="gap-1.5"
      >
        {copied ? (
          <>
            <Check className="h-4 w-4 text-success" strokeWidth={1.5} />
            Copied
          </>
        ) : (
          <>
            <Copy className="h-4 w-4" strokeWidth={1.5} />
            Copy
          </>
        )}
      </Button>
      {onRotate && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRotate}
          disabled={isRotating}
          aria-label="Rotate join code"
          className="gap-1.5"
        >
          <RefreshCw
            className={`h-4 w-4 ${isRotating ? "animate-spin" : ""}`}
            strokeWidth={1.5}
          />
          Rotate
        </Button>
      )}
    </div>
  );
}
