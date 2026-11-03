export function Logo() {
  return (
    <div className="flex items-center gap-2.5 text-signal">
      <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
        <rect x="1" y="1" width="24" height="24" rx="7" fill="none" stroke="currentColor" strokeWidth="2" />
        <path
          d="M8 17 L12 9 L15 14 L18 11"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="text-base font-bold tracking-tight text-foreground">FounderOS</span>
    </div>
  );
}
