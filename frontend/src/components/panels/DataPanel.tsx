import { Upload } from "lucide-react";
import { useCallback, useEffect, useState, type ChangeEvent } from "react";

import { EmptyNote, ErrorNote, Section } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  fetchBackups,
  fetchMappings,
  fetchTables,
  loadSample,
  putMapping,
  undoUpload,
  uploadDataFile,
  type BackupInfo,
  type CanonicalTable,
  type LoadedTable,
  type SheetMapping,
  type UploadConflict,
  type UploadMode,
} from "@/lib/api";
import { csvHeaders } from "@/lib/format";

const selectClass = "h-10 min-w-0 rounded-lg border border-border-strong bg-background px-2 text-sm";

function MappingEditor({
  fileKey,
  headers,
  initial,
  canonical,
  onSave,
  saveLabel,
}: {
  fileKey: string;
  headers: string[];
  initial: SheetMapping;
  canonical: CanonicalTable[];
  onSave: (mapping: SheetMapping) => void;
  saveLabel: string;
}) {
  const [table, setTable] = useState(initial.table);
  const [columns, setColumns] = useState<Record<string, string>>(initial.columns);
  const spec = canonical.find((t) => t.table === table);
  const chosen = Object.values(columns);
  const missing = (spec?.columns ?? []).filter((c) => c.required && !chosen.includes(c.name));
  const twice = chosen.filter((c, i) => c && chosen.indexOf(c) !== i);
  return (
    <div className="flex flex-col gap-2" data-testid="mapping-editor">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={`table-${fileKey}`} className="text-[13px]">
          This file holds
        </label>
        <select
          id={`table-${fileKey}`}
          className={selectClass}
          value={table}
          onChange={(e) => {
            setTable(e.target.value);
            setColumns({});
          }}
        >
          <option value="">Choose a table</option>
          {canonical.map((t) => (
            <option key={t.table} value={t.table}>
              {t.table}: {t.description}
            </option>
          ))}
        </select>
      </div>
      {spec ? (
        <ul className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
          {headers.map((header) => (
            <li key={header} className="flex items-center gap-2">
              <label htmlFor={`col-${fileKey}-${header}`} className="num min-w-0 flex-1 truncate text-xs" title={header}>
                {header}
              </label>
              <select
                id={`col-${fileKey}-${header}`}
                className={`${selectClass} w-44`}
                value={columns[header] ?? ""}
                onChange={(e) => {
                  const others = Object.entries(columns).filter(([key]) => key !== header);
                  setColumns(Object.fromEntries(e.target.value ? [...others, [header, e.target.value]] : others));
                }}
              >
                <option value="">Not used</option>
                {spec.columns.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                    {c.required ? " (required)" : ""}
                  </option>
                ))}
              </select>
            </li>
          ))}
        </ul>
      ) : null}
      {missing.length ? (
        <p className="text-xs text-signal-soft">Still needed: {missing.map((c) => c.name).join(", ")}</p>
      ) : null}
      {twice.length ? <p className="text-xs text-signal-soft">Used twice: {[...new Set(twice)].join(", ")}</p> : null}
      <div>
        <Button
          size="sm"
          disabled={!spec || missing.length > 0 || twice.length > 0}
          onClick={() => onSave({ table, columns })}
        >
          {saveLabel}
        </Button>
      </div>
    </div>
  );
}

export function DataPanel() {
  const [tables, setTables] = useState<LoadedTable[] | null>(null);
  const [canonical, setCanonical] = useState<CanonicalTable[]>([]);
  const [mappings, setMappings] = useState<Record<string, SheetMapping>>({});
  const [failed, setFailed] = useState<{ file: File; headers: string[]; reason: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{
    file: File;
    table?: string;
    conflicts: UploadConflict[];
    via: "upload" | "mapping";
  } | null>(null);
  const [backups, setBackups] = useState<BackupInfo[]>([]);

  const refresh = useCallback(() => {
    fetchBackups()
      .then((b) => setBackups(Array.isArray(b) ? b : []))
      .catch(() => undefined);
    fetchTables()
      .then((t) => {
        setTables(Array.isArray(t.loaded) ? t.loaded : []);
        setCanonical(Array.isArray(t.canonical) ? t.canonical : []);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Data could not be read"));
    fetchMappings()
      .then(setMappings)
      .catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await work();
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work");
    } finally {
      setBusy(false);
    }
  };

  const tryUpload = async (file: File, table?: string, mode: UploadMode = "check", via: "upload" | "mapping" = "upload") => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const outcome = await uploadDataFile(file, table, mode, via);
      setFailed(null);
      if (outcome.conflicts?.length) {
        // Nothing was written: the founder chooses replace or append, with both row counts in view.
        setPending({ file, table, conflicts: outcome.conflicts, via });
        return;
      }
      setPending(null);
      const loaded = outcome.tables?.map((t) => `${t.table} now has ${t.rows.toLocaleString("en-US")} rows`) ?? [];
      const verb = mode === "append" ? "added" : "loaded";
      setNote(`${file.name} is ${verb}${loaded.length ? `: ${loaded.join("; ")}` : ""}.`);
      refresh();
    } catch (err) {
      const reason = err instanceof Error ? err.message : "The upload did not work";
      if (file.name.toLowerCase().endsWith(".csv")) {
        setFailed({ file, headers: csvHeaders(await file.text()), reason });
      } else {
        setFailed(null);
        setError(reason);
      }
    } finally {
      setBusy(false);
    }
  };

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void tryUpload(file);
  };

  const saveAndRetry = async (mapping: SheetMapping) => {
    if (!failed) return;
    try {
      await putMapping(failed.file.name, mapping);
      await tryUpload(failed.file, mapping.table, "check", "mapping");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The mapping was not saved");
    }
  };

  const saveExisting = (key: string, mapping: SheetMapping) => {
    void run(async () => {
      await putMapping(key, mapping);
      setNote(`Saved. It applies the next time ${key.split("#")[0] ?? key} is uploaded.`);
    });
  };

  return (
    <main className="flex min-w-0 flex-1 flex-col gap-4 px-6 py-5">
      <h1 className="text-[22px] font-bold tracking-tight">Data</h1>
      <Section
        title="Loaded tables"
        aside={
          <span className="flex flex-wrap gap-2">
            <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md border border-border-strong bg-card px-4 text-sm font-medium hover:bg-accent">
              <Upload aria-hidden="true" className="h-4 w-4" />
              Upload CSV or Excel
              <input type="file" accept=".csv,.xlsx" className="sr-only" disabled={busy} onChange={onFile} />
            </label>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                // A reset: whatever upload was waiting for a choice is dropped (founder re-test 46).
                setPending(null);
                setFailed(null);
                void run(loadSample);
              }}
            >
              Load sample data
            </Button>
          </span>
        }
      >
        {error ? (
          <div className="mb-3">
            <ErrorNote>{error}</ErrorNote>
          </div>
        ) : null}
        {note ? <p className="mb-3 text-[13px] text-ok">{note}</p> : null}
        {pending ? (
          <div
            role="alertdialog"
            aria-label="This upload changes data you already have"
            data-testid="upload-warning"
            className="mb-4 flex flex-col gap-3 rounded-xl border border-[#4A3A1C] bg-[#1A1610] p-3.5 text-[13px]"
          >
            <p className="font-semibold">{pending.file.name} would change data you already have. Nothing is written yet.</p>
            <ul className="flex flex-col gap-1">
              {pending.conflicts.map((c) => (
                <li key={c.table}>
                  <span className="num">{c.table}</span> has{" "}
                  <span className="num font-semibold">{c.existing_rows.toLocaleString("en-US")}</span> rows
                  {c.existing_source ? (
                    <>
                      {" "}
                      from <span className="num">{c.existing_source}</span>
                    </>
                  ) : null}
                  ; this file has <span className="num font-semibold">{c.incoming_rows.toLocaleString("en-US")}</span>.
                  {c.incoming_rows < c.existing_rows ? (
                    <span className="text-signal-soft">
                      {" "}
                      Replacing leaves {c.incoming_rows.toLocaleString("en-US")} of {c.existing_rows.toLocaleString("en-US")}.
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">Either way, the current version is kept as a backup you can undo.</p>
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => void tryUpload(pending.file, pending.table, "append", pending.via)}>
                Append the rows
              </Button>
              <Button variant="outline" disabled={busy} onClick={() => void tryUpload(pending.file, pending.table, "replace", pending.via)}>
                Replace the table
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => setPending(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
        {backups.length ? (
          <div className="mb-3 flex flex-col gap-1.5" data-testid="backups">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Earlier versions you can restore</p>
            <ul className="flex flex-col gap-1.5" aria-label="Earlier versions">
              {backups.map((b) => (
                <li key={b.id || b.table} className="flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground" data-testid="version">
                  <span>
                    <span className="num text-foreground">{b.table}</span>: <span className="num">{b.rows.toLocaleString("en-US")}</span> rows
                    {b.source_file ? <> from <span className="num">{b.source_file}</span></> : null}
                    {b.clean_sample ? <span className="text-ok"> (the sample data)</span> : null}, kept {b.label}
                    {b.saved_at ? <>, {new Date(`${b.saved_at}Z`).toLocaleString()}</> : null}.
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        const r = await undoUpload(b.table, b.id);
                        setNote(`Restored: ${r.restored.table} is back to ${r.restored.rows.toLocaleString("en-US")} rows.`);
                      })
                    }
                  >
                    Restore this {b.table}
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {failed ? (
          <div className="mb-4 flex flex-col gap-3 rounded-xl border border-[#4A3A1C] bg-[#1A1610] p-3.5">
            <p className="text-[13px]">
              <span className="font-semibold">{failed.file.name}</span> did not load: {failed.reason}. Say what its columns are, and it loads with that mapping from now on.
            </p>
            <MappingEditor
              fileKey={failed.file.name}
              headers={failed.headers}
              initial={{ table: "", columns: {} }}
              canonical={canonical}
              onSave={(m) => void saveAndRetry(m)}
              saveLabel="Save the mapping and load the file"
            />
          </div>
        ) : null}
        {tables && tables.length === 0 ? <EmptyNote>No data is loaded yet.</EmptyNote> : null}
        {tables && tables.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-[13px]" data-testid="data-tables">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b border-border">
                  <th scope="col" className="py-1.5 pr-3 font-medium">Table</th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">File</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Rows</th>
                  <th scope="col" className="py-1.5 font-medium">Loaded</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((t) => (
                  <tr key={t.table} className="border-b border-border/60">
                    <td className="num py-1.5 pr-3">{t.table}</td>
                    <td className="num py-1.5 pr-3 text-muted-foreground">
                      {t.source_file}
                      {t.sheet ? ` [${t.sheet}]` : ""}
                    </td>
                    <td className="num py-1.5 pr-3 text-right">{t.rows.toLocaleString("en-US")}</td>
                    <td className="num py-1.5 text-muted-foreground">{t.ingested_at.slice(0, 16).replace("T", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Section>

      {Object.keys(mappings).length ? (
        <Section title="Column mappings">
          <ul className="flex flex-col gap-2" data-testid="mappings">
            {Object.entries(mappings).map(([key, mapping]) => (
              <li key={key} className="rounded-lg border border-border bg-background p-2.5">
                <details>
                  <summary className="cursor-pointer text-[13px]">
                    <span className="num">{key}</span> <span className="text-muted-foreground">to {mapping.table}</span>
                  </summary>
                  <div className="mt-2">
                    <MappingEditor
                      fileKey={key}
                      headers={Object.keys(mapping.columns)}
                      initial={mapping}
                      canonical={canonical}
                      onSave={(m) => saveExisting(key, m)}
                      saveLabel="Save the mapping"
                    />
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </main>
  );
}
