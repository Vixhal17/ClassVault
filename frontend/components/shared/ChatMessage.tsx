"use client";

import React from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface SourceCitation {
  fileId: string;
  fileName: string;
  page: number;
}

export interface ChatMessageItem {
  id: string;
  sender: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
  rating?: "helpful" | "unhelpful" | null;
}

interface ChatMessageProps {
  message: ChatMessageItem;
  onRating?: (messageId: string, rating: "helpful" | "unhelpful") => void;
  onSourceClick?: (source: SourceCitation) => void;
}

export function ChatMessage({
  message,
  onRating,
  onSourceClick,
}: ChatMessageProps) {
  if (message.sender === "user") {
    return (
      <div className="flex justify-end my-4">
        <div className="max-w-[80%] rounded bg-panel border border-border px-4 py-2.5 text-base text-text">
          {message.content}
        </div>
      </div>
    );
  }

  // Assistant: plain text on page background (no bubble, no avatar, no AI icon)
  return (
    <div className="flex flex-col items-start my-4 text-left max-w-[720px]">
      <div className="text-base text-text leading-relaxed whitespace-pre-wrap">
        {message.content}
      </div>

      {message.sources && message.sources.length > 0 && (
        <div className="mt-3 text-xs text-text-muted">
          <span className="font-medium mr-1.5">Sources:</span>
          {message.sources.map((s, idx) => (
            <React.Fragment key={idx}>
              <button
                type="button"
                onClick={() => onSourceClick?.(s)}
                className="text-accent hover:underline hover:text-accent-hover font-normal"
              >
                {s.fileName}, page {s.page}
              </button>
              {idx < message.sources!.length - 1 && <span>, </span>}
            </React.Fragment>
          ))}
        </div>
      )}

      {onRating && (
        <div className="mt-2.5 flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onRating(message.id, "helpful")}
            aria-label="Helpful answer"
            className={cn(
              "h-8 w-8 text-text-muted hover:text-text",
              message.rating === "helpful" && "text-accent"
            )}
          >
            <ThumbsUp className="h-4 w-4" strokeWidth={1.5} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onRating(message.id, "unhelpful")}
            aria-label="Not helpful answer"
            className={cn(
              "h-8 w-8 text-text-muted hover:text-text",
              message.rating === "unhelpful" && "text-danger"
            )}
          >
            <ThumbsDown className="h-4 w-4" strokeWidth={1.5} />
          </Button>
        </div>
      )}
    </div>
  );
}
