"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, LogOut, X, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface CourseNav {
  id: string;
  name: string;
  code: string;
}

interface AppShellProps {
  userEmail?: string;
  userRole?: string;
  courses?: CourseNav[];
  currentCourseTitle?: string;
  onSignOut?: () => void;
  children: React.ReactNode;
}

export function AppShell({
  userEmail = "student@classvault.local",
  userRole = "student",
  courses = [],
  currentCourseTitle,
  onSignOut,
  children,
}: AppShellProps) {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false);

  const sidebarContent = (
    <div className="flex h-full flex-col justify-between p-4">
      <div className="space-y-6">
        {/* Text Wordmark */}
        <div className="flex items-center justify-between">
          <Link href="/courses" className="text-base font-semibold text-text tracking-tight">
            ClassVault
          </Link>
          <span className="text-xs text-text-muted capitalize">({userRole})</span>
        </div>

        {/* Course List Navigation */}
        <div className="space-y-1">
          <div className="px-2 py-1 text-xs font-medium text-text-muted">Courses</div>
          {courses.length === 0 ? (
            <p className="px-2 text-xs text-text-muted">No courses yet.</p>
          ) : (
            courses.map((course) => {
              const active = pathname?.includes(`/courses/${course.id}`);
              return (
                <Link
                  key={course.id}
                  href={`/courses/${course.id}`}
                  onClick={() => setMobileMenuOpen(false)}
                  className={cn(
                    "flex items-center gap-2 rounded px-2.5 py-1.5 text-sm transition-colors",
                    active
                      ? "bg-bg font-medium text-text border border-border"
                      : "text-text-muted hover:bg-bg/50 hover:text-text"
                  )}
                >
                  <BookOpen className="h-4 w-4 shrink-0 text-text-muted" strokeWidth={1.5} />
                  <span className="truncate">{course.name}</span>
                </Link>
              );
            })
          )}
        </div>
      </div>

      {/* User Footer / Sign Out */}
      <div className="border-t border-border pt-4">
        <div className="truncate text-xs text-text-muted mb-2" title={userEmail}>
          {userEmail}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onSignOut}
          className="w-full justify-start gap-2 text-xs text-text-muted hover:text-danger px-2"
        >
          <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
          Sign out
        </Button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-bg">
      {/* Desktop Left Sidebar (232px) */}
      <aside className="hidden md:flex w-[232px] shrink-0 flex-col border-r border-border bg-panel">
        {sidebarContent}
      </aside>

      {/* Mobile Top Bar */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 flex h-14 items-center justify-between border-b border-border bg-panel px-4">
        <span className="font-semibold text-text text-sm truncate">
          {currentCourseTitle || "ClassVault"}
        </span>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Open menu"
        >
          {mobileMenuOpen ? (
            <X className="h-5 w-5" strokeWidth={1.5} />
          ) : (
            <Menu className="h-5 w-5" strokeWidth={1.5} />
          )}
        </Button>
      </div>

      {/* Mobile Sheet Overlay */}
      {mobileMenuOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/40"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="relative z-50 w-[260px] bg-panel shadow-dialog">
            {sidebarContent}
          </div>
        </div>
      )}

      {/* Main Content Area: max-w-[960px], padding 24px desktop, 16px mobile */}
      <main className="flex-1 w-full max-w-[960px] p-6 max-md:p-4 max-md:pt-16 text-left">
        {children}
      </main>
    </div>
  );
}
