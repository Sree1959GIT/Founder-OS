import { ArrowLeft, Download, FileText, History, MessageSquare, Pencil, Printer, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { EmptyNote, ErrorNote, LineageChip, Pill } from "@/components/common";
import { PriorityMatrix } from "@/components/memo/PriorityMatrix";
import { Button } from "@/components/ui/button";
import { fetchMemoVersion, fetchMemoVersions, fetchNote, fetchNotes, saveNote, type MemoVersion, type VaultNote, type VaultNoteInfo } from "@/lib/api";
import { memoWhen, metricValue, prefillAsk, stripFrontmatter, syncTitle, withoutWikilinks } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

/** Markdown exactly as it is stored, frontmatter included, so it opens the same in Obsidian. */
function downloadText(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Founder F18: "Ask the team about this" opens the Boardroom with the question started in the Advisor's box. */
function askTeam(title: string): void {
  window.location.hash = "#/";
  window.setTimeout(() => prefillAsk(`About the memo "${title}": `), 80);
}

function closeMemo(): void {
  if (window.history.length > 1) window.history.back();
  else window.location.hash = "#/";
}

export function MemoView({ path: wanted }: { path?: string }) {
  const { currentRun: run, send, state } = useWorkspace();
  const [versions, setVersions] = useState<MemoVersion[]>([]);
  const [earlier, setEarlier] = useState<{ id: string; frontmatter: Record<string, unknown>; body: string } | null>(null);
  const runMemo = run?.result?.memo ?? null;
  const [notes, setNotes] = useState<VaultNoteInfo[]>([]);
  const [path, setPath] = useState<string | null>(wanted ?? runMemo?.path ?? null);
  const [note, setNote] = useState<VaultNote | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchNotes("decisions")
      .then((list) => {
        if (!Array.isArray(list.notes)) return;
        setNotes(list.notes);
        setPath((current) => current ?? list.notes[list.notes.length - 1]?.path ?? null);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (runMemo?.path) setPath(runMemo.path);
  }, [runMemo?.path]);

  // F18: a regenerated memo keeps its path (one memo per decision), so a new result reloads it.
  useEffect(() => {
    if (runMemo?.path && runMemo.path === path) {
      fetchNote(runMemo.path).then(setNote).catch(() => undefined);
      fetchMemoVersions(runMemo.path).then((v) => setVersions(v.versions)).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new result, not a path change, reloads here
  }, [runMemo]);

  const load = useCallback((p: string) => {
    fetchNote(p)
      .then((n) => {
        setNote(n);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "The memo could not be read"));
  }, []);

  useEffect(() => {
    if (!path) return;
    setEditing(false); // a draft belongs to the memo it was opened on: Save must never write it over another
    setEarlier(null);
    load(path);
    fetchMemoVersions(path)
      .then((v) => setVersions(Array.isArray(v.versions) ? v.versions : []))
      .catch(() => setVersions([]));
  }, [path, load]);

  const openVersion = (id: string) => {
    if (!path) return;
    fetchMemoVersion(path, id)
      .then(setEarlier)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "That version could not be read"));
  };

  const save = async () => {
    if (!path) return;
    try {
      await saveNote(path, syncTitle(note?.content ?? "", draft));
      setEditing(false);
      load(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The memo could not be saved");
    }
  };

  const front = earlier?.frontmatter ?? note?.frontmatter ?? {};
  const body = earlier
    ? withoutWikilinks(earlier.body)
    : note
      ? withoutWikilinks(stripFrontmatter(note.body ?? note.content ?? ""))
      : "";
  const title = (note?.frontmatter?.title as string | undefined) ?? note?.title ?? "this decision";
  const latestWhen = memoWhen((note?.frontmatter?.written_at as string | undefined) ?? note?.modified ?? "");
  const isRunMemo = runMemo?.path === path;
  const status = (front.status as string | undefined) ?? (isRunMemo ? runMemo?.status : undefined);
  const review = (front.review_date as string | undefined) ?? (isRunMemo ? runMemo?.review_date : undefined);
  const keyNumbers = isRunMemo ? (run?.result?.metrics ?? []).slice(0, 4) : [];

  return (
    <main className="grid min-w-0 flex-1 grid-cols-1 gap-4 px-6 py-5 xl:grid-cols-[minmax(380px,460px)_1fr]">
      <div className="print-hide min-w-0">
        <PriorityMatrix />
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        <div className="print-hide flex items-center justify-between gap-2">
          <a href="#/" className="inline-flex min-h-[44px] items-center gap-1.5 text-sm">
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
            Back to the decision
          </a>
          <Button variant="ghost" size="icon" aria-label="Close the memo" title="Close the memo" className="h-11 w-11" onClick={closeMemo}>
            <X aria-hidden="true" />
          </Button>
        </div>
        <div className="print-hide flex flex-wrap items-center gap-2">
          <FileText aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
          <label htmlFor="memo-picker" className="sr-only">
            Decision memo
          </label>
          <select
            id="memo-picker"
            value={path ?? ""}
            onChange={(e) => {
              setEditing(false);
              setPath(e.target.value);
            }}
            className="h-10 min-w-0 max-w-[320px] rounded-lg border border-border-strong bg-card px-2 text-sm"
          >
            {path && !notes.some((n) => n.path === path) ? <option value={path}>{path}</option> : null}
            {notes.map((n) => (
              <option key={n.path} value={n.path}>
                {n.title}
              </option>
            ))}
          </select>
          <span className="flex-1" />
          {note ? (
            <>
              <Button
                variant="outline"
                disabled={state.sending}
                onClick={() => void send(`Write the memo again for "${title}", with what we know now.`)}
                title="The team writes this memo again; the version you see now is kept under Earlier versions"
              >
                <RefreshCw aria-hidden="true" />
                Regenerate memo
              </Button>
              <Button variant="outline" onClick={() => askTeam(title)}>
                <MessageSquare aria-hidden="true" />
                Ask the team about this
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setDraft(note.content ?? "");
                  setEditing(!editing);
                }}
              >
                <Pencil aria-hidden="true" />
                Edit
              </Button>
              <Button
                variant="outline"
                onClick={() => downloadText((path ?? "memo.md").split("/").pop() ?? "memo.md", note.content ?? "")}
              >
                <Download aria-hidden="true" />
                Export .md
              </Button>
              <Button onClick={() => window.print()} className="bg-ink text-paper hover:bg-ink/90">
                <Printer aria-hidden="true" />
                Export PDF
              </Button>
            </>
          ) : null}
        </div>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        {!path && !error ? (
          <EmptyNote>No decision memo yet. Ask the advisor about a decision and the Memo Writer drafts one here.</EmptyNote>
        ) : null}
        {editing ? (
          <div className="flex flex-col gap-2">
            <label htmlFor="memo-edit" className="sr-only">
              Memo text
            </label>
            <textarea
              id="memo-edit"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={28}
              className="num rounded-xl border border-border-strong bg-background p-3 text-[12.5px]"
            />
            <div className="flex gap-2">
              <Button onClick={() => void save()}>Save to the vault</Button>
              <Button variant="ghost" onClick={() => setEditing(false)}>
                Discard
              </Button>
            </div>
          </div>
        ) : note ? (
          <article className="memo-sheet rounded-xl bg-paper px-5 py-6 text-ink sm:px-9 sm:py-8" data-testid="memo-sheet">
            <div className="memo-chips mb-3 flex flex-wrap gap-2">
              {earlier ? (
                <Pill tone="amber">
                  <History aria-hidden="true" className="h-3 w-3" />
                  Earlier version · {memoWhen(earlier.id)}
                </Pill>
              ) : (
                <span
                  className="inline-flex items-center gap-1.5 rounded-full bg-signal px-2.5 py-0.5 text-xs font-semibold text-on-signal"
                  data-testid="memo-latest"
                >
                  Latest{latestWhen ? ` · ${latestWhen}` : ""}
                </span>
              )}
              {status ? <Pill>{status === "draft" ? "Draft · Memo Writer" : status}</Pill> : null}
              {review ? (
                <Pill>
                  Review <span className="num">{review}</span>
                </Pill>
              ) : null}
            </div>
            {keyNumbers.length ? (
              <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4">
                {keyNumbers.map((m, i) => (
                  <div key={`${m.metric}-${i}`} className="min-w-0 rounded-lg border border-[#D9D5C8] p-2.5">
                    <p className="font-sans text-xs text-[#6A6E76]">{m.label}</p>
                    <p className="num text-[15px] font-semibold">{metricValue(m.value, m.unit, m.metric)}</p>
                    <span className="print-hide">
                      <LineageChip lineage={m.lineage} label="lineage" />
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="memo-prose font-sans text-[15px] leading-relaxed">
              <Markdown remarkPlugins={[remarkGfm]}>{body}</Markdown>
            </div>
          </article>
        ) : null}
        {note && (versions.length || earlier) ? (
          <section className="print-hide rounded-xl border border-border bg-card p-4" aria-labelledby="memo-versions" data-testid="memo-versions">
            <h2 id="memo-versions" className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Earlier versions of this memo
            </h2>
            <ul className="flex flex-col gap-1">
              <li>
                <button
                  type="button"
                  aria-current={earlier ? undefined : "true"}
                  onClick={() => setEarlier(null)}
                  className="flex min-h-[44px] w-full items-center gap-2 rounded-lg px-2 text-left text-[13px] hover:bg-accent aria-[current=true]:bg-accent"
                >
                  <span className="font-semibold">Latest</span>
                  <span className="num text-muted-foreground">{latestWhen}</span>
                  <span className="truncate text-muted-foreground">{(note.frontmatter?.proposed_option as string | undefined) ?? ""}</span>
                </button>
              </li>
              {versions.map((v) => (
                <li key={v.id}>
                  <button
                    type="button"
                    aria-current={earlier?.id === v.id ? "true" : undefined}
                    onClick={() => openVersion(v.id)}
                    className="flex min-h-[44px] w-full items-center gap-2 rounded-lg px-2 text-left text-[13px] hover:bg-accent aria-[current=true]:bg-accent"
                  >
                    <span className="num text-muted-foreground">{memoWhen(v.written_at || v.id)}</span>
                    <span className="truncate">{v.proposed_option || v.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </main>
  );
}
