import type { ReactNode } from "react";

type CardProps = {
  children: ReactNode;
  className?: string;
  padding?: "none" | "sm" | "md" | "lg";
};

export function Card({ children, className = "", padding = "md" }: CardProps) {
  const paddingStyles = {
    none: "",
    sm: "p-3",
    md: "p-4",
    lg: "p-6",
  };

  return (
    <div
      className={`rounded-2xl border border-slate-200/80 bg-white shadow-card ${paddingStyles[padding]} ${className}`}
    >
      {children}
    </div>
  );
}
