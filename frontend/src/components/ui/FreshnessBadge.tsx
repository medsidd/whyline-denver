"use client";

interface FreshnessBadgeProps {
  label: string;
  value: string;
  /** "success" | "accent" | "warning" — maps to CSS modifier classes */
  variant: "success" | "accent" | "warning";
}

/** Single freshness status badge — mirrors .status-badge in branding.py */
export function FreshnessBadge({ label, value, variant }: FreshnessBadgeProps) {
  return (
    <div className={`status-badge status-badge--${variant}`}>
      <span className="status-badge__label">{label}</span>
      <span className="status-badge__value">{value}</span>
    </div>
  );
}
