import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { ErrorNote, Section } from "@/components/common";
import { Button } from "@/components/ui/button";
import { fetchPriorities, putPriorities, type Criterion, type OptionScore, type ScoredOption } from "@/lib/api";
import { moneyShort } from "@/lib/format";

const QUADRANTS = [
  { name: "Plan carefully", className: "left-3 top-2 text-signal-soft" },
  { name: "Do now", className: "right-3 top-2 text-ok" },
  { name: "Drop", className: "bottom-2 left-3 text-muted-foreground" },
  { name: "Quick wins", className: "bottom-2 right-3 text-info" },
];

const MIN = 1;
const MAX = 5;

/** A position on an axis (0..1) as the 1-5 score that gives it, for every criterion on that axis. */
function withAxis(option: ScoredOption, criteria: Criterion[], axis: "value" | "feasibility", position: number): ScoredOption {
  const scores = { ...option.scores };
  const clamped = Math.min(1, Math.max(0, position));
  for (const criterion of criteria) {
    if (criterion.axis !== axis) continue;
    const share = criterion.direction === "cost" ? 1 - clamped : clamped;
    scores[criterion.name] = Math.round((MIN + share * (MAX - MIN)) * 10) / 10;
  }
  return { ...option, scores };
}

export function PriorityMatrix() {
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [options, setOptions] = useState<ScoredOption[]>([]);
  const [scores, setScores] = useState<OptionScore[]>([]);
  const [shares, setShares] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const board = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<{ name: string; x: number; y: number } | null>(null);

  useEffect(() => {
    fetchPriorities()
      .then((view) => {
        if (!Array.isArray(view.criteria)) return;
        setCriteria(view.criteria);
        setOptions(view.options);
        setScores(view.scoring?.options ?? []);
        setShares(view.scoring?.weights ?? {});
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Priorities could not be read"));
  }, []);

  const save = async (nextCriteria: Criterion[], nextOptions: ScoredOption[]) => {
    setCriteria(nextCriteria);
    setOptions(nextOptions);
    if (!nextOptions.length) {
      setScores([]);
      return;
    }
    try {
      const view = await putPriorities(nextCriteria, nextOptions);
      setScores(view.scoring?.options ?? []);
      setShares(view.scoring?.weights ?? {});
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Priorities could not be saved");
    }
  };

  const placed = (who: string, x: number, y: number) => {
    const next = options.map((o) =>
      o.name === who ? withAxis(withAxis(o, criteria, "feasibility", x), criteria, "value", y) : o,
    );
    void save(criteria, next);
  };

  const pointerPosition = (e: PointerEvent) => {
    const box = board.current?.getBoundingClientRect();
    if (!box) return { x: 0, y: 0 };
    return {
      x: Math.min(1, Math.max(0, (e.clientX - box.left) / box.width)),
      y: Math.min(1, Math.max(0, 1 - (e.clientY - box.top) / box.height)),
    };
  };

  const onKey = (e: KeyboardEvent, who: string, x: number, y: number) => {
    const step = 0.05;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, step],
      ArrowDown: [0, -step],
    };
    const move = moves[e.key];
    if (!move) return;
    e.preventDefault();
    placed(who, x + move[0], y + move[1]);
  };

  const addOption = () => {
    const clean = name.trim();
    if (!clean || options.some((o) => o.name === clean)) return;
    const mid = (MIN + MAX) / 2;
    void save(criteria, [...options, { name: clean, cost: null, scores: Object.fromEntries(criteria.map((c) => [c.name, mid])) }]);
    setName("");
  };

  const biggest = Math.max(1, ...scores.map((s) => s.cost ?? 0));
  const ranked = [...scores].sort((a, b) => a.rank - b.rank);

  return (
    <Section title="Prioritisation Matrix" className="min-w-0">
      <div className="flex flex-col gap-3" data-testid="priority-matrix">
        <p className="text-xs text-muted-foreground">
          Scores are yours; the ranking is computed in code. Drag a bubble, or focus it and use the arrow keys.
        </p>
        <div className="flex gap-2">
          <span className="flex items-center text-xs text-muted-foreground [writing-mode:vertical-rl] [transform:rotate(180deg)]">
            Bottom-line value
          </span>
          <div className="min-w-0 flex-1">
            <div ref={board} className="relative h-[420px] touch-none overflow-hidden rounded-xl border border-border bg-background">
              <span aria-hidden="true" className="absolute left-1/2 top-0 h-full w-px bg-border-strong" />
              <span aria-hidden="true" className="absolute left-0 top-1/2 h-px w-full bg-border-strong" />
              {QUADRANTS.map((q) => (
                <span key={q.name} className={`absolute text-xs font-semibold ${q.className}`}>
                  {q.name}
                </span>
              ))}
              {scores.map((s) => {
                const held = dragging?.name === s.name ? dragging : null;
                const x = held ? held.x : (s.feasibility ?? 0.5);
                const y = held ? held.y : (s.value ?? 0.5);
                const size = 28 + 44 * Math.sqrt((s.cost ?? biggest * 0.25) / biggest);
                return (
                  <button
                    key={s.name}
                    type="button"
                    aria-label={`${s.name}: ${s.quadrant ?? "unplaced"}, rank ${s.rank}. Arrow keys move it.`}
                    title={`${s.name}${s.cost ? ` · ${moneyShort(s.cost)}` : ""}`}
                    className="absolute flex cursor-grab items-center justify-center rounded-full border border-signal bg-signal/20 text-[11px] font-semibold text-foreground"
                    style={{
                      width: size,
                      height: size,
                      left: `calc(${x * 100}% - ${size / 2}px)`,
                      top: `calc(${(1 - y) * 100}% - ${size / 2}px)`,
                    }}
                    onKeyDown={(e) => onKey(e, s.name, x, y)}
                    onPointerDown={(e) => {
                      e.currentTarget.setPointerCapture(e.pointerId);
                      setDragging({ name: s.name, ...pointerPosition(e) });
                    }}
                    onPointerMove={(e) => {
                      if (dragging?.name === s.name) setDragging({ name: s.name, ...pointerPosition(e) });
                    }}
                    onPointerUp={(e) => {
                      if (dragging?.name !== s.name) return;
                      const at = pointerPosition(e);
                      setDragging(null);
                      placed(s.name, at.x, at.y);
                    }}
                  >
                    <span className="num">{s.rank}</span>
                  </button>
                );
              })}
            </div>
            <p className="mt-1 text-center text-xs text-muted-foreground">Execution feasibility</p>
          </div>
        </div>

        <ol className="flex flex-col gap-1 text-[13px]" aria-label="Ranking">
          {ranked.map((s) => (
            <li key={s.name} className="flex items-baseline gap-2">
              <span className="num w-5 text-muted-foreground">{s.rank}</span>
              <span className="min-w-0 flex-1 truncate">{s.name}</span>
              <span className="text-xs text-muted-foreground">{s.quadrant}</span>
              <span className="num text-xs">{s.total.toFixed(2)}</span>
            </li>
          ))}
        </ol>

        <div className="flex gap-2">
          <label htmlFor="new-initiative" className="sr-only">
            New initiative
          </label>
          <input
            id="new-initiative"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") addOption();
            }}
            placeholder="Add an initiative"
            className="h-10 min-w-0 flex-1 rounded-lg border border-border-strong bg-background px-3 text-sm"
          />
          <Button variant="outline" disabled={!name.trim()} onClick={addOption}>
            Add
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {criteria.map((c) => (
            <div key={c.name} className="rounded-lg border border-border bg-background p-2">
              <label htmlFor={`weight-${c.name}`} className="block truncate text-xs text-muted-foreground">
                {c.name}
              </label>
              <input
                id={`weight-${c.name}`}
                type="number"
                min={0.05}
                max={1}
                step={0.05}
                value={c.weight}
                onChange={(e) => {
                  const weight = Number(e.target.value);
                  if (weight > 0) void save(criteria.map((x) => (x.name === c.name ? { ...x, weight } : x)), options);
                }}
                className="num h-8 w-full bg-transparent text-[15px] font-semibold"
              />
              {typeof shares[c.name] === "number" ? (
                <span className="num block text-[11px] text-muted-foreground">counts as {((shares[c.name] ?? 0) * 100).toFixed(0)}%</span>
              ) : null}
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Weights are rescaled to add up to 1, so only how they compare matters. A new initiative starts in the middle,
          not scored yet: drag it to score it.
        </p>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
      </div>
    </Section>
  );
}
