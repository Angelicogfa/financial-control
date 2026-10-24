/** KPI Card component displaying current value, historical evolution badge, and 12m forward projection. */

import React from "react";

interface EvolutionProjectionCardProps {
  title: string;
  mainValue: string;
  evolutionBadge: string;
  evolutionTone?: "positive" | "neutral" | "negative";
  subtitle: string;
  progressPct: number;
  projectionLabel: string;
  projectionValue: string;
  highlight?: boolean;
}

export const EvolutionProjectionCard: React.FC<EvolutionProjectionCardProps> = ({
  title,
  mainValue,
  evolutionBadge,
  evolutionTone = "positive",
  subtitle,
  progressPct,
  projectionLabel,
  projectionValue,
  highlight = false,
}) => {
  const clampedProgress = Math.max(0, Math.min(100, progressPct));

  return (
    <article className={`kpi-card ${highlight ? "highlight" : ""}`}>
      <div className="kpi-top">
        <span className="kpi-label">{title}</span>
        <span className={`evolution-pill ${evolutionTone} mono`}>{evolutionBadge}</span>
      </div>
      <div className="kpi-value mono">{mainValue}</div>
      <div className="kpi-subtext">{subtitle}</div>
      <div className="kpi-progress-track" aria-hidden="true">
        <div className="kpi-progress-fill" style={{ width: `${clampedProgress}%` }} />
      </div>
      <div className="kpi-projection-box">
        <span className="kpi-projection-label">{projectionLabel}</span>
        <span className="kpi-projection-val mono">{projectionValue}</span>
      </div>
    </article>
  );
};
