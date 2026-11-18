"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { AppShell } from "@/components/shared/AppShell";
import { PageHeader } from "@/components/shared/PageHeader";
import { DataTable, Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Plus, UserPlus, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

interface CourseItem {
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

export default function CoursesPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();

  const [courses, setCourses] = React.useState<CourseItem[]>([]);
  const [loading, setLoading] = React.useState(true);

  // Dialog states
  const [createOpen, setCreateOpen] = React.useState(false);
  const [joinOpen, setJoinOpen] = React.useState(false);
  const [actionLoading, setActionLoading] = React.useState(false);

  // Form states
  const [newCourseName, setNewCourseName] = React.useState("");
  const [newCourseCode, setNewCourseCode] = React.useState("");
  const [joinCodeInput, setJoinCodeInput] = React.useState("");
  const [formError, setFormError] = React.useState("");

  const fetchCourses = React.useCallback(async () => {
    try {
      const data = await apiFetch<CourseItem[]>("/courses");
      setCourses(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        toast.error(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    } else if (user) {
      fetchCourses();
    }
  }, [user, authLoading, router, fetchCourses]);

  const handleCreateCourse = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    setActionLoading(true);
    try {
      await apiFetch("/courses", {
        method: "POST",
        body: JSON.stringify({ name: newCourseName, code: newCourseCode }),
      });
      toast.success("Course created");
      setCreateOpen(false);
      setNewCourseName("");
      setNewCourseCode("");
      await fetchCourses();
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Failed to create course.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleJoinCourse = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    setActionLoading(true);
    try {
      await apiFetch("/courses/join", {
        method: "POST",
        body: JSON.stringify({ code: joinCodeInput }),
      });
      toast.success("Join request submitted. Awaiting teacher approval.");
      setJoinOpen(false);
      setJoinCodeInput("");
      await fetchCourses();
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Failed to join course.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteCourse = async (courseId: string, courseName: string) => {
    if (!window.confirm(`Are you sure you want to delete course "${courseName}"?`)) {
      return;
    }
    try {
      await apiFetch(`/courses/${courseId}`, { method: "DELETE" });
      toast.success(`Course "${courseName}" deleted.`);
      await fetchCourses();
    } catch (err: unknown) {
      if (err instanceof Error) {
        toast.error(err.message);
      } else {
        toast.error("Failed to delete course.");
      }
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg text-text-muted text-sm">
        <Loader2 className="h-5 w-5 animate-spin mr-2" strokeWidth={1.5} />
        Loading courses...
      </div>
    );
  }

  const isTeacher = user?.role === "teacher" || user?.role === "admin";

  const teacherColumns: Column<CourseItem>[] = [
    {
      header: "Course",
      accessorKey: "name",
      cell: (item) => (
        <Link href={`/courses/${item.id}`} className="font-medium text-text hover:underline">
          {item.name}
        </Link>
      ),
    },
    { header: "Code", accessorKey: "code" },
    {
      header: "Students",
      cell: (item) => `${item.student_count} enrolled`,
    },
    {
      header: "Requests",
      cell: (item) =>
        item.pending_count > 0 ? (
          <Link
            href={`/courses/${item.id}?tab=requests`}
            className="text-accent hover:underline font-medium"
          >
            {item.pending_count} pending
          </Link>
        ) : (
          <span className="text-text-muted">None</span>
        ),
      className: "text-right",
    },
    {
      header: "Action",
      cell: (item) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            handleDeleteCourse(item.id, item.name);
          }}
          className="h-7 px-2 text-xs text-text-muted hover:text-danger hover:bg-danger/10"
          aria-label={`Delete ${item.name}`}
        >
          <Trash2 className="h-3.5 w-3.5 mr-1" strokeWidth={1.5} />
          Delete
        </Button>
      ),
      className: "text-right",
    },
  ];

  const studentColumns: Column<CourseItem>[] = [
    {
      header: "Course",
      accessorKey: "name",
      cell: (item) => (
        <Link href={`/courses/${item.id}`} className="font-medium text-text hover:underline">
          {item.name}
        </Link>
      ),
    },
    { header: "Code", accessorKey: "code" },
    {
      header: "Instructor",
      cell: (item) => item.teacher_name || "Instructor",
    },
  ];

  return (
    <AppShell
      courses={courses}
      userEmail={user?.email}
      userRole={user?.role}
      currentCourseTitle="Courses"
      onSignOut={logout}
    >
      <div className="space-y-6">
        <PageHeader
          title="Courses"
          description={
            isTeacher
              ? "Manage your courses, view join requests, and upload unit materials."
              : "Access your enrolled courses and view course materials."
          }
          action={
            isTeacher ? (
              <Button
                variant="primary"
                onClick={() => {
                  setFormError("");
                  setCreateOpen(true);
                }}
                className="gap-1.5"
              >
                <Plus className="h-4 w-4" strokeWidth={1.5} />
                New course
              </Button>
            ) : (
              <Button
                variant="primary"
                onClick={() => {
                  setFormError("");
                  setJoinOpen(true);
                }}
                className="gap-1.5"
              >
                <UserPlus className="h-4 w-4" strokeWidth={1.5} />
                Join course
              </Button>
            )
          }
        />

        {courses.length === 0 ? (
          <div className="rounded border border-border bg-bg p-6">
            <EmptyState
              message={
                isTeacher
                  ? "You have not created any courses yet."
                  : "You are not enrolled in any courses yet."
              }
              actionLabel={isTeacher ? "Create course" : "Join course"}
              onAction={() => {
                setFormError("");
                if (isTeacher) setCreateOpen(true);
                else setJoinOpen(true);
              }}
            />
          </div>
        ) : (
          <DataTable
            columns={isTeacher ? teacherColumns : studentColumns}
            data={courses}
          />
        )}

        {/* Dialog: New Course (Teacher) */}
        <DialogPrimitive.Root open={createOpen} onOpenChange={setCreateOpen}>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
            <DialogPrimitive.Content className="fixed left-[50%] top-[50%] z-50 w-full max-w-md translate-x-[-50%] translate-y-[-50%] rounded border border-border bg-bg p-6 shadow-dialog focus:outline-none">
              <DialogPrimitive.Title className="text-base font-semibold text-text">
                New course
              </DialogPrimitive.Title>
              <form onSubmit={handleCreateCourse} className="mt-4 space-y-4">
                <FormField
                  label="Course name"
                  placeholder="e.g. Operating Systems"
                  value={newCourseName}
                  onChange={(e) => setNewCourseName(e.target.value)}
                  disabled={actionLoading}
                  required
                />
                <FormField
                  label="Course code"
                  placeholder="e.g. CS401"
                  value={newCourseCode}
                  onChange={(e) => setNewCourseCode(e.target.value)}
                  disabled={actionLoading}
                  required
                />
                {formError && (
                  <p className="text-xs text-danger" role="alert">
                    {formError}
                  </p>
                )}
                <div className="flex justify-end gap-3 pt-2">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setCreateOpen(false)}
                    disabled={actionLoading}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" disabled={actionLoading}>
                    {actionLoading && <Loader2 className="h-4 w-4 animate-spin mr-1.5" strokeWidth={1.5} />}
                    Create course
                  </Button>
                </div>
              </form>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>

        {/* Dialog: Join Course (Student) */}
        <DialogPrimitive.Root open={joinOpen} onOpenChange={setJoinOpen}>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
            <DialogPrimitive.Content className="fixed left-[50%] top-[50%] z-50 w-full max-w-sm translate-x-[-50%] translate-y-[-50%] rounded border border-border bg-bg p-6 shadow-dialog focus:outline-none">
              <DialogPrimitive.Title className="text-base font-semibold text-text">
                Join course
              </DialogPrimitive.Title>
              <form onSubmit={handleJoinCourse} className="mt-4 space-y-4">
                <FormField
                  label="Course join code"
                  placeholder="e.g. CS401-X7K2"
                  value={joinCodeInput}
                  onChange={(e) => setJoinCodeInput(e.target.value.toUpperCase())}
                  disabled={actionLoading}
                  className="font-mono uppercase tracking-wider"
                  required
                />
                {formError && (
                  <p className="text-xs text-danger" role="alert">
                    {formError}
                  </p>
                )}
                <div className="flex justify-end gap-3 pt-2">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setJoinOpen(false)}
                    disabled={actionLoading}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" disabled={actionLoading}>
                    {actionLoading && <Loader2 className="h-4 w-4 animate-spin mr-1.5" strokeWidth={1.5} />}
                    Join course
                  </Button>
                </div>
              </form>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>
      </div>
    </AppShell>
  );
}
