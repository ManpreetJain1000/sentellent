import type { ReactNode } from "react";

type BadgeProps = {
  children: ReactNode;
  variant?: "default" | "success" | "muted";
};

export function Badge({ children, variant = "default" }: BadgeProps) {
  const styles = {
    default: "bg-brand-50 text-brand-700 ring-brand-200",
    success: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    muted: "bg-slate-100 text-slate-600 ring-slate-200",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${styles[variant]}`}
    >
      {children}
    </span>
  );
}
