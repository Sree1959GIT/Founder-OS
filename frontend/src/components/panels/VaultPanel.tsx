import { Search, Upload } from "lucide-react";
import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { EmptyNote, ErrorNote, Section } from "@/components/common";
import { Button } from "@/components/ui/button";
import { fetchNote, fetchNotes, saveNote, searchVault, uploadVaultFile, type VaultNote, type VaultNoteInfo } from "@/lib/api";
import { stripFrontmatter, syncTitle, withoutWikilinks } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Hit {
  path: string;
  heading: string;
  snippet: string;
}

function hitsFrom(response: Record<string, unknown>): Hit[] {
  const list = (response.results ?? response.hits ?? []) as Record<string, unknown>[];
  if (!Array.isArray(list)) return [];
  return list.map((h) => {
    const citation = (h.citation ?? {}) as { path?: string; heading?: string };
    return {
      path: citation.path ?? (h.path as string) ?? "",
      heading: citation.heading ?? (h.heading as string) ?? "",
      snippet: ((h.text ?? h.snippet ?? "") as string).slice(0, 180),
    };
  });
}

export function VaultPanel({ path: wanted }: { path?: string }) {
  const [notes, setNotes] = useState<VaultNoteInfo[]>([]);
  const [path, setPath] = useState<string | null>(wanted ?? null);
  const [note, setNote] = useState<VaultNote | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetchNotes()
      .then((list) => setNotes(Array.isArray(list.notes) ? list.notes : []))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "The vault could not be read"));
  }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => {
    if (wanted) setPath(wanted);
  }, [wanted]);
  useEffect(() => {
    if (!path) return;
    setEditing(false); // a draft belongs to the note it was opened on: Save must never write it over another
    fetchNote(path)
      .then((n) => {
        setNote(n);
        setError(null);
      })
      .catch((err: unknown) => {
        setNote(null);
        setError(err instanceof Error ? err.message : "That note could not be read");
      });
  }, [path]);

  const search = (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) {
      setHits(null);
      return;
    }
    searchVault(query)
      .then((r) => setHits(hitsFrom(r as Record<string, unknown>)))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Search did not work"));
  };

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    uploadVaultFile(file)
      .then((r) => {
        refresh();
        setPath(r.path);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "The upload did not work"));
  };

  const save = async () => {
    if (!path) return;
    try {
      setNote(await saveNote(path, syncTitle(note?.content ?? "", draft)));
      setEditing(false);
      fetchNote(path).then(setNote).catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The note could not be saved");
    }
  };

  const isMarkdown = note?.kind === "md" || note?.kind === "note" || note?.content !== undefined;
  const folders = [...new Set(notes.map((n) => n.folder))].sort();

  return (
    <main className="grid min-w-0 flex-1 grid-cols-1 gap-4 px-6 py-5 lg:grid-cols-[320px_1fr]">
      <div className="flex min-w-0 flex-col gap-3">
        <h1 className="text-[22px] font-bold tracking-tight">Vault</h1>
        <form onSubmit={search} className="flex gap-2">
          <label htmlFor="vault-search" className="sr-only">
            Search the vault
          </label>
          <input
            id="vault-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search your notes"
            className="h-10 min-w-0 flex-1 rounded-lg border border-border-strong bg-background px-3 text-sm"
          />
          <Button type="submit" variant="outline" size="icon" aria-label="Search">
            <Search aria-hidden="true" />
          </Button>
        </form>
        <label className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-border-strong bg-card px-4 text-sm font-medium hover:bg-accent">
          <Upload aria-hidden="true" className="h-4 w-4" />
          Add a file to the vault
          <input type="file" className="sr-only" onChange={onFile} />
        </label>
        {hits ? (
          <Section title="Search results" aside={<button type="button" className="text-xs text-info" onClick={() => setHits(null)}>Clear</button>}>
            {hits.length === 0 ? <p className="text-muted-foreground">Nothing found.</p> : null}
            <ul className="flex flex-col gap-2">
              {hits.map((hit, i) => (
                <li key={`${hit.path}-${i}`}>
                  <button type="button" className="w-full text-left" onClick={() => setPath(hit.path)}>
                    <span className="num block truncate text-xs text-info">{hit.path}</span>
                    <span className="block text-xs text-muted-foreground">{hit.snippet}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        ) : (
          <nav aria-label="Notes" className="flex flex-col gap-3" data-testid="vault-notes">
            {notes.length === 0 ? <EmptyNote>The vault is empty.</EmptyNote> : null}
            {folders.map((folder) => (
              <div key={folder || "root"}>
                <h2 className="mb-1 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">{folder || "Vault"}</h2>
                <ul className="flex flex-col">
                  {notes
                    .filter((n) => n.folder === folder)
                    .map((n) => (
                      <li key={n.path}>
                        <button
                          type="button"
                          onClick={() => {
                            setEditing(false);
                            setPath(n.path);
                          }}
                          aria-current={n.path === path}
                          className={cn(
                            "min-h-10 w-full truncate rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-accent",
                            n.path === path ? "bg-accent text-foreground" : "text-muted-foreground",
                          )}
                        >
                          {n.title}
                        </button>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </nav>
        )}
      </div>

      <div className="flex min-w-0 flex-col gap-3">
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        {!path && !error ? <EmptyNote>Choose a note to read it.</EmptyNote> : null}
        {note ? (
          <Section
            title={<span className="num break-all text-[13px] font-medium">{note.path}</span>}
            aside={
              note.content !== undefined ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setDraft(note.content ?? "");
                    setEditing(!editing);
                  }}
                >
                  {editing ? "Read" : "Edit"}
                </Button>
              ) : undefined
            }
          >
            {editing ? (
              <div className="flex flex-col gap-2">
                <label htmlFor="note-edit" className="sr-only">
                  Note text
                </label>
                <textarea
                  id="note-edit"
                  rows={24}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  className="num rounded-xl border border-border-strong bg-background p-3 text-[12.5px]"
                />
                <div>
                  <Button onClick={() => void save()}>Save</Button>
                </div>
              </div>
            ) : isMarkdown ? (
              <div className="prose-chat text-[14px] leading-relaxed">
                <Markdown remarkPlugins={[remarkGfm]}>{withoutWikilinks(stripFrontmatter(note.body ?? note.content ?? ""))}</Markdown>
              </div>
            ) : (
              <p className="text-muted-foreground">This file type is stored in the vault and indexed for search.</p>
            )}
            {note.backlinks?.length ? (
              <div className="mt-4 border-t border-border pt-2">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">Linked from</h3>
                <ul className="flex flex-col gap-0.5">
                  {note.backlinks.map((b) => (
                    <li key={b}>
                      <button type="button" className="num text-xs text-info" onClick={() => setPath(b)}>
                        {b}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Section>
        ) : null}
      </div>
    </main>
  );
}
