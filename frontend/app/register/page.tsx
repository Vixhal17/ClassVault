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
      await register(name, email, password);
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
          <h1 className="text-2xl font-semibold text-text">Create student account</h1>
        </div>

        {/* Registration Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <FormField
            label="Full name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            autoComplete="name"
            placeholder="e.g. Aarav Sharma"
            required
          />

          <FormField
            label="University email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            autoComplete="email"
            placeholder="name@university.edu"
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
            <p className="text-xs text-danger" role="alert">
              {error}
            </p>
          )}

          <Button
            type="submit"
            variant="primary"
            className="w-full gap-2"
            disabled={loading}
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />}
            {loading ? "Creating account" : "Create account"}
          </Button>
        </form>

        {/* Link to Login */}
        <div className="text-xs text-text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-accent hover:underline hover:text-accent-hover font-medium">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
