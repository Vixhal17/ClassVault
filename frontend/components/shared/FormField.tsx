import * as React from "react";
import { cn } from "@/lib/utils";

interface FormFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export const FormField = React.forwardRef<HTMLInputElement, FormFieldProps>(
  ({ label, error, hint, id, className, ...props }, ref) => {
    const generatedId = React.useId();
    const inputId = id || generatedId;
    return (
      <div className="flex flex-col gap-1.5 w-full text-left">
        <label
          htmlFor={inputId}
          className="text-xs font-medium text-text-muted select-none"
        >
          {label}
        </label>
        <input
          id={inputId}
          ref={ref}
          className={cn(
            "h-[36px] md:h-[36px] max-md:h-[44px] w-full rounded border border-border bg-bg px-3 text-sm max-md:text-base text-text transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
            "disabled:cursor-not-allowed disabled:bg-panel disabled:opacity-50",
            error && "border-danger focus-visible:ring-danger",
            className
          )}
          {...props}
        />
        {hint && !error && (
          <p className="text-xs text-text-muted">{hint}</p>
        )}
        {error && (
          <p className="text-xs text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }
);
FormField.displayName = "FormField";
