"use client";

import * as React from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/shared/FormField";
import { Loader2 } from "lucide-react";

export default function RegisterPage() {
  const { register } = useAuth();
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState("student");
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name.trim()) {
      setError("Full name is required.");
      return;
    }
    if (!email.trim()) {
      setError("Email address is required.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setLoading(true);
    try {
      await register(name, email, password, role);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to create account. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-bg">
      <div className="w-full max-w-[360px] space-y-6 text-left">
        {/* Wordmark and Page Title */}
        <div className="space-y-1">
          <span className="text-sm font-semibold text-text tracking-tight">ClassVault</span>
          <h1 className="text-2xl font-semibold text-text">
            {role === "teacher" ? "Create professor account" : "Create student account"}
          </h1>
        </div>

        {/* Registration Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="role-select" className="text-xs font-medium text-text">
              Account type
            </label>
            <select
              id="role-select"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={loading}
              className="w-full px-3 py-2 text-sm rounded-md border border-border bg-panel text-text focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="student">Student (browse courses, access materials, ask RAG assistant)</option>
              <option value="teacher">Professor / Teacher (create courses, upload PDFs, manage students)</option>
            </select>
          </div>

          <FormField
            label="Full name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            autoComplete="name"
            placeholder={role === "teacher" ? "e.g. Prof. David Miller" : "e.g. Aarav Sharma"}
            required
          />

          <FormField
            label="University email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            autoComplete="email"
            placeholder={role === "teacher" ? "prof.miller@university.edu" : "student@university.edu"}
            required
          />

          <FormField
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            autoComplete="new-password"
            hint="Minimum 8 characters"
            required
          />

          {error && (
            <div className="rounded border border-danger/20 bg-danger-bg p-3 text-xs text-danger">
              {error}
            </div>
          )}

          <Button type="submit" variant="primary" className="w-full" disabled={loading}>
            {loading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
                Creating account...
              </span>
            ) : role === "teacher" ? (
              "Sign up as Professor"
            ) : (
              "Sign up as Student"
            )}
          </Button>
        </form>

        {/* Footer Link to Login */}
        <div className="text-center text-xs text-text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-primary hover:underline font-medium">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
