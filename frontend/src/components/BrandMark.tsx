type BrandMarkProps = {
  subtitle?: string;
  size?: "sm" | "md" | "lg";
};

export function BrandMark({ subtitle, size = "md" }: BrandMarkProps) {
  const titleSizes = {
    sm: "text-base",
    md: "text-xl",
    lg: "text-3xl",
  };

  return (
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-panel">
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v18M3 12h18" />
          <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
        </svg>
      </div>
      <div>
        <p className={`font-bold tracking-tight text-slate-900 ${titleSizes[size]}`}>Sentellent</p>
        {subtitle ? <p className="text-xs font-medium text-brand-600">{subtitle}</p> : null}
      </div>
    </div>
  );
}
