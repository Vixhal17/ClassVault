"use client";

import * as React from "react";
import { AppShell } from "@/components/shared/AppShell";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { FormField } from "@/components/shared/FormField";
import { CopyField } from "@/components/shared/CopyField";
import { DataTable, Column } from "@/components/shared/DataTable";
import { FileRow, FileItem } from "@/components/shared/FileRow";
import { EmptyState } from "@/components/shared/EmptyState";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { ChatMessage, ChatMessageItem } from "@/components/shared/ChatMessage";
import { toast } from "sonner";
import { Plus } from "lucide-react";

interface StudentRow {
  id: string;
  name: string;
  email: string;
  status: "approved" | "pending";
}

export default function StyleguidePage() {
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [rotating, setRotating] = React.useState(false);
  const [joinCode, setJoinCode] = React.useState("CS401-X7K2");

  const sampleCourses = [
    { id: "1", name: "CS401 Operating Systems", code: "CS401" },
    { id: "2", name: "CS402 Computer Networks", code: "CS402" },
  ];

  const sampleStudents: StudentRow[] = [
    { id: "1", name: "Aarav Sharma", email: "aarav@univ.edu", status: "approved" },
    { id: "2", name: "Diya Patel", email: "diya@univ.edu", status: "pending" },
  ];

  const studentColumns: Column<StudentRow>[] = [
    { header: "Name", accessorKey: "name" },
    { header: "Email", accessorKey: "email" },
    {
      header: "Status",
      cell: (item) => (
        <StatusBadge status={item.status === "approved" ? "ready" : "pending"} />
      ),
    },
    {
      header: "Actions",
      cell: (item) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => toast(`Action clicked for ${item.name}`)}
        >
          {item.status === "pending" ? "Approve" : "Remove"}
        </Button>
      ),
      className: "text-right",
    },
  ];

  const sampleFiles: FileItem[] = [
    {
      id: "f1",
      name: "Unit 1: Memory Virtualization.pdf",
      sizeBytes: 2450000,
      uploadedAt: "18 Nov 2026",
      status: "ready",
    },
    {
      id: "f2",
      name: "Unit 2: Process Scheduling.pdf",
      sizeBytes: 1820000,
      uploadedAt: "18 Nov 2026",
      status: "processing",
    },
    {
      id: "f3",
      name: "Unit 3: File Systems Draft.pdf",
      sizeBytes: 3100000,
      uploadedAt: "17 Nov 2026",
      status: "failed",
      errorMessage: "The file is password protected.",
    },
  ];

  const chatMessages: ChatMessageItem[] = [
    {
      id: "m1",
      sender: "user",
      content: "What is the difference between paging and segmentation?",
    },
    {
      id: "m2",
      sender: "assistant",
      content:
        "Paging divides memory into fixed-size blocks called pages (and corresponding physical frames), which avoids external fragmentation. Segmentation divides memory into logical units of variable sizes (such as code, stack, or heap), reflecting the programmer's view of the program.\n\nPaging can cause internal fragmentation when a process does not fill the last page, whereas segmentation may suffer from external fragmentation.",
      sources: [
        { fileId: "f1", fileName: "Unit 1: Memory Virtualization.pdf", page: 14 },
        { fileId: "f1", fileName: "Unit 1: Memory Virtualization.pdf", page: 18 },
      ],
      rating: null,
    },
  ];

  return (
    <AppShell
      courses={sampleCourses}
      userEmail="teacher@classvault.local"
      userRole="teacher"
      currentCourseTitle="Design System & Styleguide"
      onSignOut={() => toast("Signed out")}
    >
      <div className="space-y-12">
        <PageHeader
          title="UI Design System Styleguide"
          description="Design tokens, typography, shadcn primitives, and shared components defined per Section 11."
          action={
            <Button
              variant="primary"
              onClick={() => toast("Primary action clicked")}
              className="gap-1.5"
            >
              <Plus className="h-4 w-4" strokeWidth={1.5} />
              New course
            </Button>
          }
        />

        {/* 1. Design Tokens */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            1. Design Tokens & Palette
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="border border-border p-3 rounded">
              <div className="h-6 w-full rounded bg-bg border border-border mb-2" />
              <div className="font-semibold">--bg</div>
              <div className="text-text-muted">#FFFFFF</div>
            </div>
            <div className="border border-border p-3 rounded">
              <div className="h-6 w-full rounded bg-panel border border-border mb-2" />
              <div className="font-semibold">--panel</div>
              <div className="text-text-muted">#F6F7F8</div>
            </div>
            <div className="border border-border p-3 rounded">
              <div className="h-6 w-full rounded bg-border mb-2" />
              <div className="font-semibold">--border</div>
              <div className="text-text-muted">#E4E6EA</div>
            </div>
            <div className="border border-border p-3 rounded">
              <div className="h-6 w-full rounded bg-accent mb-2" />
              <div className="font-semibold">--accent</div>
              <div className="text-text-muted">#1F4E79</div>
            </div>
            <div className="border border-border p-3 rounded">
              <div className="h-6 w-full rounded bg-success-bg border border-success/30 mb-2 flex items-center justify-center text-success font-medium">
                Success
              </div>
              <div className="font-semibold">--success / bg</div>
              <div className="text-text-muted">#166534 / #EFF7F1</div>
            </div>
            <div className="border border-border p-3 rounded">
              <div className="h-6 w-full rounded bg-warning-bg border border-warning/30 mb-2 flex items-center justify-center text-warning font-medium">
                Warning
              </div>
              <div className="font-semibold">--warning / bg</div>
              <div className="text-text-muted">#8A4B08 / #FBF4E8</div>
            </div>
            <div className="border border-border p-3 rounded">
              <div className="h-6 w-full rounded bg-danger-bg border border-danger/30 mb-2 flex items-center justify-center text-danger font-medium">
                Danger
              </div>
              <div className="font-semibold">--danger / bg</div>
              <div className="text-text-muted">#B42318 / #FDF1F0</div>
            </div>
            <div className="border border-border p-3 rounded">
              <div className="h-6 w-full rounded bg-panel flex items-center justify-center text-text mb-2">
                Radius: 6px
              </div>
              <div className="font-semibold">Border Radius</div>
              <div className="text-text-muted">Uniform 6px (4px badge)</div>
            </div>
          </div>
        </section>

        {/* 2. Typography */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            2. Typography (IBM Plex Sans & Mono)
          </h2>
          <div className="space-y-2 text-left">
            <div className="text-2xl font-semibold">24px/600: Login title only</div>
            <div className="text-xl font-semibold">20px/600: Page title</div>
            <div className="text-base font-semibold">16px/600: Section heading</div>
            <div className="text-base font-normal">16px/400: Chat body text and mobile inputs</div>
            <div className="text-sm font-normal text-text">14px/400: UI body and table cell text</div>
            <div className="text-xs text-text-muted">12px/400: Metadata and table headers (sentence case)</div>
            <div className="font-mono text-sm">IBM Plex Mono: CS401-X7K2 (join codes only)</div>
          </div>
        </section>

        {/* 3. Buttons */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            3. Buttons
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">Upload PDF</Button>
            <Button variant="secondary">Cancel</Button>
            <Button variant="ghost">Secondary action</Button>
            <Button variant="destructive">Remove student</Button>
            <Button variant="destructiveFilled">Delete file</Button>
            <Button variant="primary" disabled>
              Submitting
            </Button>
          </div>
        </section>

        {/* 4. Status Badges */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            4. Status Badges
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status="queued" />
            <StatusBadge status="processing" />
            <StatusBadge status="ready" />
            <StatusBadge status="pending" />
            <StatusBadge status="failed" />
          </div>
        </section>

        {/* 5. Form Fields */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            5. Form Fields
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-xl">
            <FormField
              label="Course name"
              placeholder="e.g. Operating Systems"
              hint="Visible to all enrolled students"
            />
            <FormField
              label="Email address"
              defaultValue="invalid-email"
              error="Enter a valid university email address."
            />
          </div>
        </section>

        {/* 6. CopyField */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            6. Join Code CopyField (IBM Plex Mono)
          </h2>
          <div className="max-w-md">
            <CopyField
              value={joinCode}
              isRotating={rotating}
              onRotate={() => {
                setRotating(true);
                setTimeout(() => {
                  setJoinCode(`CS401-${Math.random().toString(36).substring(2, 6).toUpperCase()}`);
                  setRotating(false);
                  toast("Join code rotated");
                }, 600);
              }}
            />
          </div>
        </section>

        {/* 7. DataTable */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            7. Data Table (48px rows, 1px dividers, sentence case header)
          </h2>
          <DataTable
            columns={studentColumns}
            data={sampleStudents}
            emptyMessage="No students found."
          />
        </section>

        {/* 8. File Rows */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            8. File Rows (Ready, Processing, Failed with Retry)
          </h2>
          <div className="rounded border border-border bg-bg overflow-hidden">
            {sampleFiles.map((file) => (
              <FileRow
                key={file.id}
                file={file}
                isTeacher={true}
                onDownload={(f) => toast(`Downloading ${f.name}`)}
                onRetry={(f) => toast(`Retrying ingestion for ${f.name}`)}
                onDelete={() => setConfirmOpen(true)}
              />
            ))}
          </div>
        </section>

        {/* 9. Empty State */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            9. Empty State
          </h2>
          <div className="rounded border border-border bg-bg p-4">
            <EmptyState
              message="No files in this unit yet."
              actionLabel="Upload PDF"
              onAction={() => toast("Upload dialog opened")}
            />
          </div>
        </section>

        {/* 10. Chat Message (Ask Tab) */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            10. Chat Message & Page Citations
          </h2>
          <div className="rounded border border-border bg-bg p-4 max-w-[760px]">
            {chatMessages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onRating={(id, rating) =>
                  toast(`Marked answer ${rating}`)
                }
                onSourceClick={(source) =>
                  toast(`Opening ${source.fileName} at page ${source.page}`)
                }
              />
            ))}
            <div className="mt-4 pt-3 border-t border-border text-xs text-text-muted">
              Answers can be wrong. Check the PDF.
            </div>
          </div>
        </section>

        {/* 11. Confirm Dialog */}
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-text border-b border-border pb-2">
            11. Confirm Dialog
          </h2>
          <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
            Open delete confirmation dialog
          </Button>
          <ConfirmDialog
            open={confirmOpen}
            onOpenChange={setConfirmOpen}
            title="Delete Unit 3: File Systems Draft.pdf?"
            description="Students lose access immediately. You can restore it from the recycle bin for 30 days."
            confirmLabel="Delete"
            onConfirm={() => {
              setConfirmOpen(false);
              toast("File moved to recycle bin");
            }}
          />
        </section>
      </div>
    </AppShell>
  );
}
