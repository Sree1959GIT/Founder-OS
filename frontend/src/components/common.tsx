import { CheckCircle2, CircleAlert, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import type { Citation, Lineage, VerificationView } from "@/lib/api";
import { prefillAsk } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tone = "amber" | "ok" | "info" | "neutral" | "danger";

const TONES: Record<Tone, string> = {
  amber: "border-[#4A3A1C] bg-[#2B2213] text-signal-soft",
  ok: "border-[#1F5A45] bg-[#10261E] text-ok",
  info: "border-[#2E4A6E] bg-[#141E2C] text-info",
  neutral: "border-border-strong bg-card text-muted-foreground",
  danger: "border-[#5A2A2A] bg-[#2A1616] text-danger",
};

export function Pill({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONES[tone],
      )}
    >
      {children}
    </span>
  );
}

/** The word "Verified" appears only where the backend said so. Anything else says so in words, never a green tick. */
export function VerifiedBadge({ verified, checks = 0 }: { verified: boolean | null | undefined; checks?: number }) {
  if (verified === true) {
    return (
      <Pill tone="ok">
        <CheckCircle2 aria-hidden="true" className="h-3 w-3" />
        Verified
      </Pill>
    );
  }
  if (verified === false) {
    return (
      <Pill tone="amber" title="The check did not pass on everything. Read these figures with care.">
        <CircleAlert aria-hidden="true" className="h-3 w-3" />
        Not verified{checks > 0 ? <span className="num">· {checks}</span> : null}
      </Pill>
    );
  }
  return null;
}

/**
 * The answer's badge, in the backend's three states. Each opens what it rests on: sources (green), the assumptions
 * to confirm (amber), or the reasons it failed (red). The word "Verified" alone appears only for the green state.
 */
export function VerificationBadge({ verification }: { verification: VerificationView }) {
  const { open, setOpen, ref } = usePopover();
  const id = useId();
  const { state, reasons, assumptions, sources, removed_claims: removed } = verification;
  const n = assumptions.length;
  const tone: Tone = state === "verified" ? "ok" : state === "assumptions" ? "amber" : "danger";
  const label =
    state === "verified"
      ? "Verified"
      : state === "assumptions"
        ? `Figures verified · ${n} ${n === 1 ? "assumption" : "assumptions"} to confirm`
        : "Not verified";
  const Icon = state === "verified" ? CheckCircle2 : CircleAlert;
  return (
    <span ref={ref} className="relative inline-flex items-center gap-1.5">
      {removed > 0 ? (
        <span data-testid="removed-chip">
          <Pill tone="neutral" title="Sentences the source check took out because nothing backed them">
            <span className="num">{removed}</span> {removed === 1 ? "claim" : "claims"} removed
          </Pill>
        </span>
      ) : null}
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        data-testid="verification-badge"
        data-state={state}
        className={cn(
          "inline-flex min-h-6 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium",
          TONES[tone],
        )}
      >
        <Icon aria-hidden="true" className="h-3 w-3" />
        {label}
      </button>
      {open ? (
        <span
          id={id}
          role="dialog"
          aria-label="What the check found"
          className="absolute right-0 top-full z-40 mt-1.5 block w-[min(380px,80vw)] rounded-xl border border-border-strong bg-panel p-3.5 text-left text-xs shadow-xl"
        >
          {state === "verified" ? (
            <>
              <span className="mb-1.5 block font-semibold text-foreground">Every figure traced to a source</span>
              {sources.length ? (
                <span className="flex flex-col gap-0.5">
                  {sources.map((s) => (
                    <span key={s} className="num break-all text-info">
                      {s}
                    </span>
                  ))}
                </span>
              ) : (
                <span className="text-muted-foreground">This answer quotes no figures.</span>
              )}
            </>
          ) : null}
          {state === "assumptions" ? (
            <>
              <span className="mb-1.5 block font-semibold text-foreground">
                The figures check out. These inputs are placeholders until you confirm them:
              </span>
              <span className="flex flex-col gap-1">
                {assumptions.map((a) => (
                  <span key={a} className="text-foreground">
                    {a}
                  </span>
                ))}
              </span>
              <button
                type="button"
                className="mt-2.5 inline-flex h-8 items-center rounded-lg bg-signal px-3 text-xs font-semibold text-[#1A1206]"
                onClick={() => {
                  setOpen(false);
                  prefillAsk("My figures: ");
                }}
              >
                Enter your figures
              </button>
            </>
          ) : null}
          {state === "not_verified" ? (
            <>
              <span className="mb-1.5 block font-semibold text-foreground">Read this answer with care</span>
              <span className="flex flex-col gap-1">
                {(reasons.length ? reasons : ["A check did not pass."]).map((r) => (
                  <span key={r} className="text-foreground">
                    {r}
                  </span>
                ))}
              </span>
              {n ? (
                <span className="mt-1.5 block text-muted-foreground">
                  It also rests on <span className="num">{n}</span> {n === 1 ? "assumption" : "assumptions"} to confirm.
                </span>
              ) : null}
            </>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}

export const ASSUMPTION_LABEL = "assumption, confirm";

export function AssumptionTag({ label = ASSUMPTION_LABEL }: { label?: string }) {
  return (
    <span className="inline-flex items-center whitespace-nowrap rounded border border-dashed border-[#4A3A1C] px-1.5 py-0.5 text-[11px] font-medium text-signal-soft">
      {label}
    </span>
  );
}

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, ref };
}

const chipClass =
  "num inline-flex max-w-full cursor-pointer items-center gap-1 truncate rounded border border-dashed border-[#2E4A6E] bg-transparent px-1.5 py-0.5 text-[11px] text-info hover:bg-[#141E2C]";

/** Dashed blue chip that opens where a number came from: formula, rows, file. */
export function LineageChip({ lineage, label, align = "left" }: { lineage: Lineage; label?: string; align?: "left" | "right" }) {
  const { open, setOpen, ref } = usePopover();
  const id = useId();
  const first = lineage.source_rows[0];
  const text = label ?? (first ? `${first.file}${first.rows ? ` · rows ${first.rows}` : ""}` : lineage.metric);
  return (
    <span ref={ref} className="relative inline-flex max-w-full">
      <button
        type="button"
        className={chipClass}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <span className="truncate">{text}</span>
      </button>
      {open ? (
        <span
          id={id}
          role="dialog"
          aria-label={`Lineage of ${lineage.metric}`}
          className={cn(
            "absolute top-full z-40 mt-1.5 block w-[min(420px,80vw)] rounded-xl border border-border-strong bg-panel p-3.5 text-left text-xs shadow-xl",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          <span className="mb-2 flex items-center justify-between gap-2">
            <span className="font-semibold text-foreground">Where this number comes from</span>
            <button type="button" aria-label="Close lineage" className="h-6 w-6 text-muted-foreground" onClick={() => setOpen(false)}>
              <X aria-hidden="true" className="mx-auto h-3.5 w-3.5" />
            </button>
          </span>
          <LineageRow label="Formula">
            <span className="num break-words text-foreground">{lineage.formula || "n/a"}</span>
          </LineageRow>
          {lineage.period ? (
            <LineageRow label="Period">
              <span className="num text-foreground">{lineage.period}</span>
            </LineageRow>
          ) : null}
          <LineageRow label="Rows">
            {lineage.source_rows.length ? (
              <span className="flex flex-col gap-0.5">
                {lineage.source_rows.map((r) => (
                  <span key={`${r.table}-${r.rows}`} className="num break-words text-foreground">
                    {r.file}
                    {r.sheet ? ` [${r.sheet}]` : ""} · rows {r.rows} ({r.row_count})
                  </span>
                ))}
              </span>
            ) : (
              <span className="text-muted-foreground">no rows recorded</span>
            )}
          </LineageRow>
          <LineageRow label="File">
            <span className="num break-words text-foreground">{lineage.source_files.join(", ") || "n/a"}</span>
          </LineageRow>
          {Object.keys(lineage.inputs).length ? (
            <LineageRow label="Inputs">
              <span className="num flex flex-col gap-0.5 text-foreground">
                {Object.entries(lineage.inputs)
                  .slice(0, 8)
                  .map(([k, v]) => (
                    <span key={k} className="break-words">
                      {k} = {v === null ? "n/a" : v.toLocaleString("en-US")}
                    </span>
                  ))}
              </span>
            </LineageRow>
          ) : null}
          {lineage.sql.length ? (
            <details className="mt-1.5">
              <summary className="cursor-pointer text-muted-foreground">SQL</summary>
              <pre className="num mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-background p-2 text-[11px] text-foreground">
                {lineage.sql.join("\n\n")}
              </pre>
            </details>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}

function LineageRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="mb-1.5 grid grid-cols-[64px_1fr] gap-2">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </span>
  );
}

/** Citation chips come only from the `citations` the backend checked, never from the text of an answer. */
export function CitationChips({ citations }: { citations: Citation[] }) {
  const seen = new Set<string>();
  const unique = citations.filter((c) => {
    if (seen.has(c.path)) return false;
    seen.add(c.path);
    return true;
  });
  if (!unique.length) return null;
  return (
    <ul aria-label="Sources" className="flex flex-wrap gap-1.5">
      {unique.map((c) => (
        <li key={c.path} className="max-w-full">
          <a
            href={`#/vault?path=${encodeURIComponent(c.path)}`}
            className="num inline-flex max-w-full truncate rounded border border-border-strong bg-background px-1.5 py-0.5 text-[11px] text-info"
            title={c.heading ? `${c.path} · ${c.heading}` : c.path}
          >
            <span className="truncate">{c.path}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export function Section({
  title,
  aside,
  children,
  className,
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-2xl border border-border bg-card p-4", className)}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-lg border border-[#5A2A2A] bg-[#2A1616] px-3 py-2 text-xs text-danger">
      <CircleAlert aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-dashed border-border-strong px-4 py-6 text-center text-muted-foreground">{children}</p>;
}
