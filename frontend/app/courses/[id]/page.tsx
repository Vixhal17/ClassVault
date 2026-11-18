"use client";

import * as React from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { AppShell } from "@/components/shared/AppShell";
import { PageHeader } from "@/components/shared/PageHeader";
import { CopyField } from "@/components/shared/CopyField";
import { DataTable, Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { FormField } from "@/components/shared/FormField";
import { FileRow, FileItem } from "@/components/shared/FileRow";
import { StatusType } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Plus, Loader2, Upload, RotateCcw } from "lucide-react";
import { toast } from "sonner";

interface CourseDetail {
  id: string;
  name: string;
  code: string;
  teacher_id: string;
  teacher_name?: string;
  join_code?: string;
  join_enabled: boolean;
  student_count: number;
  pending_count: number;
}

interface UnitItem {
  id: string;
  title: string;
  position: number;
  is_published: boolean;
}

interface EnrollmentItem {
  id: string;
  student_id: string;
  student_name?: string;
  student_email?: string;
  status: string;
  requested_at: string;
  decided_at?: string;
}

interface BackendFileItem {
  id: string;
  unit_id: string;
  course_id: string;
  original_name: string;
  size_bytes: number;
  status: string;
  error_msg?: string;
  page_count?: number;
  created_at: string;
  deleted_at?: string;
}

export default function CourseDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user, loading: authLoading, logout } = useAuth();
  const courseId = params?.id as string;

  const [course, setCourse] = React.useState<CourseDetail | null>(null);
  const [units, setUnits] = React.useState<UnitItem[]>([]);
  const [requests, setRequests] = React.useState<EnrollmentItem[]>([]);
  const [students, setStudents] = React.useState<EnrollmentItem[]>([]);
  const [loading, setLoading] = React.useState(true);

  // Files state keyed by unitId
  const [unitFiles, setUnitFiles] = React.useState<Record<string, BackendFileItem[]>>({});
  const [uploadingUnitId, setUploadingUnitId] = React.useState<string | null>(null);
  const [showRecycleBin, setShowRecycleBin] = React.useState(false);

  // File action dialogs
  const [deleteFileOpen, setDeleteFileOpen] = React.useState(false);
  const [selectedFile, setSelectedFile] = React.useState<BackendFileItem | null>(null);
  const [deleteFileLoading, setDeleteFileLoading] = React.useState(false);

  // Tab state
  const initialTab = searchParams?.get("tab") || "materials";
  const [activeTab, setActiveTab] = React.useState(initialTab);

  // Unit creation dialog
  const [unitOpen, setUnitOpen] = React.useState(false);
  const [unitTitle, setUnitTitle] = React.useState("");
  const [unitLoading, setUnitLoading] = React.useState(false);

  // Remove student confirmation dialog
  const [removeOpen, setRemoveOpen] = React.useState(false);
  const [selectedStudent, setSelectedStudent] = React.useState<EnrollmentItem | null>(null);
  const [removeLoading, setRemoveLoading] = React.useState(false);

  // Join code rotate state
  const [rotating, setRotating] = React.useState(false);

  const fileInputRefs = React.useRef<Record<string, HTMLInputElement | null>>({});

  const isTeacher = user?.role === "teacher" || user?.role === "admin";

  const fetchUnitFiles = React.useCallback(async (unitList: UnitItem[], includeDeleted = false) => {
    const filesMap: Record<string, BackendFileItem[]> = {};
    for (const unit of unitList) {
      try {
        const query = includeDeleted ? "?include_deleted=true" : "";
        const files = await apiFetch<BackendFileItem[]>(`/units/${unit.id}/files${query}`);
        filesMap[unit.id] = files;
      } catch {
        filesMap[unit.id] = [];
      }
    }
    setUnitFiles(filesMap);
  }, []);

  const fetchCourseData = React.useCallback(async () => {
    try {
      const courseData = await apiFetch<CourseDetail>(`/courses/${courseId}`);
      setCourse(courseData);

      const unitsData = await apiFetch<UnitItem[]>(`/courses/${courseId}/units`);
      setUnits(unitsData);
      await fetchUnitFiles(unitsData, showRecycleBin);

      if (user?.role === "teacher" || user?.role === "admin") {
        const reqData = await apiFetch<EnrollmentItem[]>(`/courses/${courseId}/requests`);
        setRequests(reqData);

        const studData = await apiFetch<EnrollmentItem[]>(`/courses/${courseId}/students`);
        setStudents(studData);
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        toast.error(err.message);
      }
      router.push("/courses");
    } finally {
      setLoading(false);
    }
  }, [courseId, user, router, fetchUnitFiles, showRecycleBin]);

  React.useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    } else if (user && courseId) {
      fetchCourseData();
    }
  }, [user, authLoading, courseId, router, fetchCourseData]);

  // Polling for queued/processing files every 3 seconds (Section 4.2)
  React.useEffect(() => {
    const allFiles = Object.values(unitFiles).flat();
    const hasActiveFiles = allFiles.some((f) => f.status === "queued" || f.status === "processing");

    if (!hasActiveFiles) return;

    const intervalId = setInterval(async () => {
      if (units.length > 0) {
        await fetchUnitFiles(units, showRecycleBin);
      }
    }, 3000);

    return () => clearInterval(intervalId);
  }, [unitFiles, units, fetchUnitFiles, showRecycleBin]);

  const handleRotateCode = async () => {
    setRotating(true);
    try {
      const updated = await apiFetch<CourseDetail>(`/courses/${courseId}/rotate-code`, {
        method: "POST",
      });
      setCourse(updated);
      toast.success("Join code rotated");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to rotate code");
    } finally {
      setRotating(false);
    }
  };

  const handleCreateUnit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!unitTitle.trim()) return;
    setUnitLoading(true);
    try {
      await apiFetch(`/courses/${courseId}/units`, {
        method: "POST",
        body: JSON.stringify({ title: unitTitle, position: units.length + 1 }),
      });
      toast.success("Unit created");
      setUnitOpen(false);
      setUnitTitle("");
      fetchCourseData();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to create unit");
    } finally {
      setUnitLoading(false);
    }
  };

  const handleEnrollmentDecision = async (enrollmentId: string, status: "approved" | "rejected") => {
    try {
      await apiFetch(`/enrollments/${enrollmentId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      toast.success(`Request ${status}`);
      fetchCourseData();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : `Failed to ${status} request`);
    }
  };

  const handleRemoveStudent = async () => {
    if (!selectedStudent) return;
    setRemoveLoading(true);
    try {
      await apiFetch(`/enrollments/${selectedStudent.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "removed" }),
      });
      toast.success("Student removed");
      setRemoveOpen(false);
      setSelectedStudent(null);
      fetchCourseData();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to remove student");
    } finally {
      setRemoveLoading(false);
    }
  };

  // Upload handler
  const handleFileUpload = async (unitId: string, file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Only PDF files are supported");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      toast.error("File exceeds 20 MB size limit");
      return;
    }

    setUploadingUnitId(unitId);
    const formData = new FormData();
    formData.append("file", file);

    try {
      await apiFetch(`/units/${unitId}/files`, {
        method: "POST",
        body: formData,
      });
      toast.success(`Uploaded ${file.name}. Ingestion in progress...`);
      await fetchUnitFiles(units, showRecycleBin);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploadingUnitId(null);
    }
  };

  // Download handler (60-second presigned URL)
  const handleDownload = async (fileItem: BackendFileItem) => {
    try {
      const res = await apiFetch<{ download_url: string; expires_in: number }>(
        `/files/${fileItem.id}/download`
      );
      window.open(res.download_url, "_blank");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Download failed");
    }
  };

  // Retry handler
  const handleRetry = async (fileItem: BackendFileItem) => {
    try {
      await apiFetch(`/files/${fileItem.id}/retry`, { method: "POST" });
      toast.info(`Retrying ${fileItem.original_name}...`);
      await fetchUnitFiles(units, showRecycleBin);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Retry failed");
    }
  };

  // Delete handler
  const handleDeleteConfirm = async () => {
    if (!selectedFile) return;
    setDeleteFileLoading(true);
    try {
      await apiFetch(`/files/${selectedFile.id}`, { method: "DELETE" });
      toast.success("File deleted");
      setDeleteFileOpen(false);
      setSelectedFile(null);
      await fetchUnitFiles(units, showRecycleBin);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to delete file");
    } finally {
      setDeleteFileLoading(false);
    }
  };

  // Restore handler
  const handleRestore = async (fileItem: BackendFileItem) => {
    try {
      await apiFetch(`/files/${fileItem.id}/restore`, { method: "POST" });
      toast.success(`Restored ${fileItem.original_name}. Re-indexing...`);
      await fetchUnitFiles(units, showRecycleBin);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Restore failed");
    }
  };

  if (loading || !course) {
    return (
      <div className="flex h-screen items-center justify-center bg-bg">
        <Loader2 className="h-6 w-6 animate-spin text-text-muted" strokeWidth={1.5} />
      </div>
    );
  }

  const studentColumns: Column<EnrollmentItem>[] = [
    { header: "Name", cell: (i) => i.student_name || "Student" },
    { header: "Email", accessorKey: "student_email" },
    {
      header: "Enrolled",
      cell: (i) =>
        i.decided_at ? new Date(i.decided_at).toLocaleDateString("en-IN") : "-",
    },
    {
      header: "Actions",
      cell: (i) => (
        <Button
          variant="destructive"
          size="sm"
          onClick={() => {
            setSelectedStudent(i);
            setRemoveOpen(true);
          }}
        >
          Remove
        </Button>
      ),
      className: "text-right",
    },
  ];

  const requestColumns: Column<EnrollmentItem>[] = [
    { header: "Name", cell: (i) => i.student_name || "Student" },
    { header: "Email", accessorKey: "student_email" },
    {
      header: "Requested",
      cell: (i) => new Date(i.requested_at).toLocaleDateString("en-IN"),
    },
    {
      header: "Actions",
      cell: (i) => (
        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => handleEnrollmentDecision(i.id, "rejected")}
          >
            Reject
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => handleEnrollmentDecision(i.id, "approved")}
          >
            Approve
          </Button>
        </div>
      ),
      className: "text-right",
    },
  ];

  return (
    <AppShell
      userEmail={user?.email}
      userRole={user?.role}
      currentCourseTitle={course.name}
      onSignOut={logout}
    >
      <div className="space-y-6">
        <PageHeader
          title={`${course.code}: ${course.name}`}
          description={
            isTeacher
              ? `Course Code: ${course.code} • ${course.student_count} enrolled`
              : `Instructor: ${course.teacher_name || "Faculty"} • ${course.code}`
          }
          action={
            isTeacher && course.join_code ? (
              <CopyField
                value={course.join_code}
                onRotate={handleRotateCode}
                isRotating={rotating}
              />
            ) : null
          }
        />

        {/* Tabs: Materials, Ask, and for teachers: Students, Requests */}
        <TabsPrimitive.Root value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsPrimitive.List className="flex border-b border-border gap-6 text-sm mb-6">
            <TabsPrimitive.Trigger
              value="materials"
              className="pb-2.5 font-medium transition-colors text-text-muted hover:text-text data-[state=active]:text-accent data-[state=active]:border-b-2 data-[state=active]:border-accent"
            >
              Materials
            </TabsPrimitive.Trigger>

            <TabsPrimitive.Trigger
              value="ask"
              className="pb-2.5 font-medium transition-colors text-text-muted hover:text-text data-[state=active]:text-accent data-[state=active]:border-b-2 data-[state=active]:border-accent"
            >
              Ask
            </TabsPrimitive.Trigger>

            {isTeacher && (
              <>
                <TabsPrimitive.Trigger
                  value="students"
                  className="pb-2.5 font-medium transition-colors text-text-muted hover:text-text data-[state=active]:text-accent data-[state=active]:border-b-2 data-[state=active]:border-accent"
                >
                  Students ({students.length})
                </TabsPrimitive.Trigger>

                <TabsPrimitive.Trigger
                  value="requests"
                  className="pb-2.5 font-medium transition-colors text-text-muted hover:text-text data-[state=active]:text-accent data-[state=active]:border-b-2 data-[state=active]:border-accent"
                >
                  Requests {requests.length > 0 && `(${requests.length})`}
                </TabsPrimitive.Trigger>
              </>
            )}
          </TabsPrimitive.List>

          {/* TAB: MATERIALS */}
          <TabsPrimitive.Content value="materials" className="space-y-6 focus:outline-none">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <h2 className="text-base font-semibold text-text">Course Units</h2>
                {isTeacher && (
                  <button
                    type="button"
                    onClick={() => {
                      const next = !showRecycleBin;
                      setShowRecycleBin(next);
                      fetchUnitFiles(units, next);
                    }}
                    className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                      showRecycleBin
                        ? "border-accent text-accent bg-panel font-medium"
                        : "border-border text-text-muted hover:text-text"
                    }`}
                  >
                    {showRecycleBin ? "Viewing Recycle Bin" : "Recycle Bin"}
                  </button>
                )}
              </div>

              {isTeacher && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setUnitOpen(true)}
                  className="gap-1.5"
                >
                  <Plus className="h-4 w-4" strokeWidth={1.5} />
                  New unit
                </Button>
              )}
            </div>

            {units.length === 0 ? (
              <div className="rounded border border-border bg-bg p-6">
                <EmptyState
                  message="No units created for this course yet."
                  actionLabel={isTeacher ? "Create unit" : undefined}
                  onAction={isTeacher ? () => setUnitOpen(true) : undefined}
                />
              </div>
            ) : (
              <div className="space-y-6">
                {units.map((unit) => {
                  const files = unitFiles[unit.id] || [];
                  const activeFiles = files.filter((f) => !f.deleted_at);
                  const deletedFiles = files.filter((f) => !!f.deleted_at);
                  const displayedFiles = showRecycleBin ? deletedFiles : activeFiles;

                  return (
                    <section key={unit.id} className="rounded border border-border bg-bg p-4 space-y-3">
                      <div className="flex items-center justify-between border-b border-border pb-2">
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-semibold text-text">{unit.title}</h3>
                          <span className="text-xs text-text-muted">
                            ({displayedFiles.length} {displayedFiles.length === 1 ? "file" : "files"})
                          </span>
                        </div>

                        {isTeacher && !showRecycleBin && (
                          <div>
                            <input
                              type="file"
                              accept="application/pdf"
                              className="hidden"
                              ref={(el) => {
                                fileInputRefs.current[unit.id] = el;
                              }}
                              onChange={(e) => {
                                const file = e.target.files?.[0];
                                if (file) {
                                  handleFileUpload(unit.id, file);
                                }
                                e.target.value = "";
                              }}
                            />
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => fileInputRefs.current[unit.id]?.click()}
                              disabled={uploadingUnitId === unit.id}
                              className="gap-1.5 text-xs text-accent hover:text-accent-hover"
                            >
                              {uploadingUnitId === unit.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                              ) : (
                                <Upload className="h-3.5 w-3.5" strokeWidth={1.5} />
                              )}
                              Upload PDF
                            </Button>
                          </div>
                        )}
                      </div>

                      {displayedFiles.length === 0 ? (
                        <p className="text-xs text-text-muted py-2">
                          {showRecycleBin
                            ? "No deleted files in this unit."
                            : "No PDF files uploaded to this unit yet."}
                        </p>
                      ) : (
                        <div className="divide-y divide-border">
                          {displayedFiles.map((f) => {
                            const fileItem: FileItem = {
                              id: f.id,
                              name: f.original_name,
                              sizeBytes: f.size_bytes,
                              uploadedAt: new Date(f.created_at).toLocaleDateString("en-IN"),
                              status: f.status as StatusType,
                              errorMessage: f.error_msg,
                            };

                            if (showRecycleBin) {
                              return (
                                <div
                                  key={f.id}
                                  className="flex items-center justify-between py-2 text-sm"
                                >
                                  <div className="flex items-center gap-2 truncate">
                                    <span className="font-medium text-text truncate">
                                      {f.original_name}
                                    </span>
                                    <span className="text-xs text-text-muted">
                                      (deleted {new Date(f.deleted_at!).toLocaleDateString("en-IN")})
                                    </span>
                                  </div>
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    onClick={() => handleRestore(f)}
                                    className="gap-1 text-xs"
                                  >
                                    <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.5} />
                                    Restore
                                  </Button>
                                </div>
                              );
                            }

                            return (
                              <FileRow
                                key={f.id}
                                file={fileItem}
                                isTeacher={isTeacher}
                                onDownload={() => handleDownload(f)}
                                onRetry={() => handleRetry(f)}
                                onDelete={() => {
                                  setSelectedFile(f);
                                  setDeleteFileOpen(true);
                                }}
                              />
                            );
                          })}
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            )}
          </TabsPrimitive.Content>

          {/* TAB: ASK (RAG Assistant) */}
          <TabsPrimitive.Content value="ask" className="focus:outline-none">
            <div className="rounded border border-border bg-bg p-6 max-w-[720px] space-y-4">
              <h2 className="text-base font-semibold text-text">Course AI Assistant</h2>
              <p className="text-sm text-text-muted">
                Ask questions about your course materials with page-level citations.
              </p>
              <div className="border border-border rounded p-4 bg-panel text-xs text-text-muted">
                AI Q&A will be enabled once unit PDFs are ingested in Phases 3 and 4.
              </div>
            </div>
          </TabsPrimitive.Content>

          {/* TAB: STUDENTS */}
          {isTeacher && (
            <TabsPrimitive.Content value="students" className="space-y-4 focus:outline-none">
              <DataTable
                columns={studentColumns}
                data={students}
                emptyMessage="No students currently enrolled in this course."
              />
            </TabsPrimitive.Content>
          )}

          {/* TAB: REQUESTS */}
          {isTeacher && (
            <TabsPrimitive.Content value="requests" className="space-y-4 focus:outline-none">
              <DataTable
                columns={requestColumns}
                data={requests}
                emptyMessage="No pending join requests."
              />
            </TabsPrimitive.Content>
          )}
        </TabsPrimitive.Root>

        {/* Dialog: Create Unit */}
        <DialogPrimitive.Root open={unitOpen} onOpenChange={setUnitOpen}>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
            <DialogPrimitive.Content className="fixed left-[50%] top-[50%] z-50 w-full max-w-md translate-x-[-50%] translate-y-[-50%] rounded border border-border bg-bg p-6 shadow-dialog focus:outline-none">
              <DialogPrimitive.Title className="text-base font-semibold text-text">
                New unit
              </DialogPrimitive.Title>
              <form onSubmit={handleCreateUnit} className="mt-4 space-y-4">
                <FormField
                  label="Unit title"
                  placeholder="e.g. Unit 1: Memory Virtualization"
                  value={unitTitle}
                  onChange={(e) => setUnitTitle(e.target.value)}
                  disabled={unitLoading}
                  required
                />
                <div className="flex justify-end gap-3 pt-2">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setUnitOpen(false)}
                    disabled={unitLoading}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" disabled={unitLoading}>
                    {unitLoading && <Loader2 className="h-4 w-4 animate-spin mr-1.5" strokeWidth={1.5} />}
                    Create unit
                  </Button>
                </div>
              </form>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>

        {/* Confirm Dialog: Remove Student */}
        <ConfirmDialog
          open={removeOpen}
          onOpenChange={setRemoveOpen}
          title={`Remove ${selectedStudent?.student_name || "student"} from ${course.name}?`}
          description="The student will lose access to course materials immediately."
          confirmLabel="Remove"
          onConfirm={handleRemoveStudent}
          isLoading={removeLoading}
        />

        {/* Confirm Dialog: Delete File */}
        <ConfirmDialog
          open={deleteFileOpen}
          onOpenChange={setDeleteFileOpen}
          title={`Delete ${selectedFile?.original_name || "file"}?`}
          description="The file and its search index will be deleted immediately. You can restore it from the Recycle Bin within 30 days."
          confirmLabel="Delete"
          onConfirm={handleDeleteConfirm}
          isLoading={deleteFileLoading}
        />
      </div>
    </AppShell>
  );
}
