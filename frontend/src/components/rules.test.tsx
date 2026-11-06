import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerCard, DecisionLead } from "@/components/chat/AnswerCard";
import { CitationChips, LineageChip, VerifiedBadge } from "@/components/common";
import { parseFrame, type ChatResult, type DecisionFrame, type Lineage } from "@/lib/api";
import { csvHeaders, metricValue, safeStep, stripFrontmatter, withoutWikilinks } from "@/lib/format";
import type { RunView } from "@/lib/workspace";
import { parseHash } from "@/hooks/useRoute";

const frame: DecisionFrame = {
  type: "new_office",
  subject: "Dubai office",
  message: "Should we?",
  currency: "USD",
  as_of: "2026-10",
  default_option: "Travel-led pilot",
  goals: [],
  questions: [],
  options: [
    { name: "Full office", note: "", one_off: 30000, monthly: 32000, runway_change_months: -2.07, modelled: true, is_full: true, trade_off: "", basis: "assumption" },
    { name: "Travel-led pilot", note: "", one_off: 0, monthly: 3000, runway_change_months: -0.21, modelled: true, is_full: false, trade_off: "", basis: "assumption" },
  ],
  cost_model: {
    subject: "Dubai office",
    items: [],
    cases: [{ name: "base", one_off: 30000, monthly: 32000, base_runway_months: 10, scenario_runway_months: 8, runway_change_months: -2.07 }],
    cost_per_person_monthly: null,
    currency: "USD",
    as_of: "2026-10",
    formula: "",
    sources: [],
    scope_note: "",
  },
};

const run = (over: Partial<RunView>): RunView => ({
  id: "r",
  message: "m",
  startedAt: "2026-11-06T12:00:00Z",
  status: "done",
  intent: null,
  decisionType: null,
  reversibility: null,
  needsApproval: false,
  awaitingApproval: false,
  proposedTeam: [],
  questions: [],
  frame: null,
  agents: {},
  order: [],
  artifacts: [],
  answer: "",
  result: null,
  verified: null,
  lastSeq: 0,
  ...over,
});

const result = (over: Partial<ChatResult>): ChatResult =>
  ({ agents: [], metrics: [], citations: [], issues: [], memo: null, elapsed_ms: 1000, advisor_provider: "ollama", verified: true, ...over }) as ChatResult;

describe("what may be shown", () => {
  it("says Verified only when the backend said true", () => {
    const { rerender, container } = render(<VerifiedBadge verified={true} />);
    expect(screen.getByText("Verified")).toBeInTheDocument();
    rerender(<VerifiedBadge verified={false} />);
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    rerender(<VerifiedBadge verified={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not show a Verified badge while the answer is still being written", () => {
    render(<AnswerCard run={run({ status: "running", answer: "Runway is", result: null })} />);
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
  });

  it("counts the issues and removed claims and never prints their text", () => {
    const issues = ["Market Scout: number without lineage: $160 billion"];
    const agents = [{ removed: ["(removed: unsupported figure)"] }] as unknown as ChatResult["agents"];
    render(<AnswerCard run={run({ answer: "Clean text.", result: result({ verified: false, issues, agents }) })} />);
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("160 billion");
    expect(document.body.textContent).toContain("taken out by the source check");
  });

  it("leads a decision with the proposed option, then the full model, labelled as an assumption", () => {
    render(<DecisionLead frame={frame} />);
    const text = screen.getByTestId("decision-lead").textContent ?? "";
    expect(text.indexOf("Travel-led pilot")).toBeLessThan(text.indexOf("Full model"));
    expect(text).toContain("assumption, confirm");
  });

  it("makes source chips only from the citations it is given, once each", () => {
    const citation = { path: "notes/real.md", heading: "H", chunk_id: "1" };
    render(<CitationChips citations={[citation, citation]} />);
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("opens lineage with the formula, the rows and the file", async () => {
    const lineage: Lineage = {
      metric: "runway",
      sql: [],
      source_files: ["bank.csv"],
      source_rows: [{ table: "bank", file: "bank.csv", sheet: null, rows: "2-9", row_count: 8 }],
      formula: "cash / burn",
      inputs: {},
      period: "2026-10",
      computed_at: "",
    };
    render(<LineageChip lineage={lineage} />);
    screen.getByRole("button").click();
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("cash / burn");
    expect(dialog).toHaveTextContent("rows 2-9");
    expect(dialog).toHaveTextContent("bank.csv");
  });
});

describe("safeStep", () => {
  it("keeps the words of a tool call out", () => {
    expect(safeStep('running web_search({"query": "market worth $160 billion"})')).toBe("running web_search()");
  });
  it("keeps what the Verifier found out", () => {
    expect(safeStep("sent back by the Verifier: number without lineage: $160 billion")).toBe("sent back by the Verifier");
  });
  it("masks a figure or a path in any other step", () => {
    const shown = safeStep("found $160 billion and 40% in notes/economic-overview.md");
    expect(shown).toBe("found a figure and a figure in a source");
  });
  it("leaves plain words alone", () => {
    expect(safeStep("reading the vault")).toBe("reading the vault");
  });
});

describe("helpers", () => {
  it("formats by unit", () => {
    expect(metricValue(10.65, "months")).toBe("10.65 mo");
    expect(metricValue(255344.27, "USD")).toBe("$255,344.27");
    expect(metricValue(0.71, "ratio", "gross_margin")).toBe("71.00%");
    expect(metricValue(3.2, "ratio", "ltv_cac")).toBe("3.20x");
    expect(metricValue(null, "USD")).toBe("n/a");
  });
  it("reads a CSV header line", () => {
    expect(csvHeaders('Kol A,"Kol, B", Kol C\r\n1,2,3')).toEqual(["Kol A", "Kol, B", "Kol C"]);
  });
  it("strips frontmatter and wikilinks", () => {
    expect(stripFrontmatter("---\ntitle: x\n---\n# Body")).toBe("# Body");
    expect(withoutWikilinks("see [[notes/a|A note]] and [[b]]")).toBe("see A note and b");
  });
  it("reads a hash route and an SSE frame", () => {
    expect(parseHash("#/vault?path=notes%2Fa.md")).toEqual({ view: "vault", path: "notes/a.md" });
    expect(parseHash("#/nonsense").view).toBe("workspace");
    expect(parseFrame('event: delta\ndata: {"text":"hi"}')).toEqual({ event: "delta", data: { text: "hi" } });
    expect(parseFrame("event: delta\ndata: {broken")).toBeNull();
  });
});
