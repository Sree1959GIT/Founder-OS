import { Upload } from "lucide-react";
import { useCallback, useEffect, useState, type ChangeEvent } from "react";

import { EmptyNote, ErrorNote, Section } from "@/components/common";
import { Button } from "@/components/ui/button";
import { fetchTables, loadSample, uploadDataFile, type LoadedTable } from "@/lib/api";

export function DataPanel() {
  const [tables, setTables] = useState<LoadedTable[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    fetchTables()
      .then((t) => setTables(Array.isArray(t.loaded) ? t.loaded : []))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Data could not be read"));
  }, []);
  useEffect(refresh, [refresh]);

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work");
    } finally {
      setBusy(false);
    }
  };

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void run(() => uploadDataFile(file));
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
              <input type="file" accept=".csv,.xlsx,.xls" className="sr-only" disabled={busy} onChange={onFile} />
            </label>
            <Button variant="outline" disabled={busy} onClick={() => void run(loadSample)}>
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
    </main>
  );
}
