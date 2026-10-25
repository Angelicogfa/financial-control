import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  actions,
}: Readonly<{ title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }>) {
  return (
    <div className="app-page-header">
      <div>
        <h1 className="app-page-title">{title}</h1>
        {subtitle && <p className="app-page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="app-button-row">{actions}</div>}
    </div>
  );
}
