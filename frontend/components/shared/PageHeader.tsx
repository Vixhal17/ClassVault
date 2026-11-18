import React from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, description, action }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-1 pb-6 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 className="text-xl font-semibold text-text">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-text-muted">{description}</p>
        )}
      </div>
      {action && <div className="mt-3 md:mt-0 flex items-center">{action}</div>}
    </div>
  );
}
