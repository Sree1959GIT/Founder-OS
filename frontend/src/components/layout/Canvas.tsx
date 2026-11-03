import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const PLACEHOLDERS = [
  { title: "Runway", note: "Deterministic metrics with lineage arrive in M1." },
  { title: "Scenario simulator", note: "Base vs scenario cash with live sliders (M1 engine, M4 UI)." },
  { title: "Knowledge vault", note: "Notes, decisions and cited search arrive in M2." },
];

export function Canvas() {
  return (
    <main className="flex min-w-0 flex-[999_1_560px] flex-col gap-4 px-6 py-5">
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">Open decision</span>
        <h1 className="text-[22px] font-bold tracking-tight">No decision open yet</h1>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {PLACEHOLDERS.map((p) => (
          <Card key={p.title} className="border-dashed">
            <CardHeader>
              <CardTitle>{p.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground">{p.note}</CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
