import { describe, expect, it } from "vitest";

import { decisionTitle, itemValue, money, periodLabel, runTitle, syncTitle, withPeriod } from "@/lib/format";

const memo = "---\ntitle: Dubai office\nstatus: proposed\n---\n# Dubai office\n\nBody.\n";

describe("memo titles", () => {
  it("copies an edited frontmatter title to the heading", () => {
    const edited = memo.replace("title: Dubai office", "title: Dubai pilot");
    const out = syncTitle(memo, edited);
    expect(out).toContain("title: Dubai pilot");
    expect(out).toContain("# Dubai pilot\n");
    expect(out).not.toContain("# Dubai office");
  });

  it("copies an edited heading to the frontmatter title", () => {
    const out = syncTitle(memo, memo.replace("# Dubai office", "# Dubai: travel-led pilot"));
    expect(out).toContain('title: "Dubai: travel-led pilot"');
    expect(out).toContain("# Dubai: travel-led pilot");
  });

  it("leaves a note alone when no title changed", () => {
    const edited = memo.replace("Body.", "New body.");
    expect(syncTitle(memo, edited)).toBe(edited);
  });
});

describe("decision titles", () => {
  it("is neutral about which option is proposed", () => {
    expect(decisionTitle("A full Dubai office", "Should we?")).toBe("Dubai office");
    expect(decisionTitle("", "Should we open a Dubai office?")).toBe("Should we open a Dubai office?");
  });
});

describe("lineage chip labels", () => {
  it("lists every row range of a file once", async () => {
    const { lineageLabel } = await import("@/lib/format");
    const rows = [
      { file: "pnl.csv", rows: "2-121" },
      { file: "pnl.csv", rows: "242-361" },
      { file: "bank_balance.csv", rows: "2-13" },
    ];
    expect(lineageLabel(rows, "gross_margin")).toBe("pnl.csv · rows 2–121, 242–361; bank_balance.csv · rows 2–13");
    expect(lineageLabel([], "runway")).toBe("runway");
  });
});

describe("runTitle", () => {
  it("keeps the question and the last change, never the stacked amendments (founder review 41)", () => {
    expect(runTitle("Should we open Dubai?\nThe founder then added: also make it a two person team")).toBe(
      "Should we open Dubai? · changed: also make it a two person team",
    );
    expect(runTitle("Should we open Dubai? · changed: a\nThe founder then added: b")).toBe("Should we open Dubai? · changed: b");
    expect(runTitle("What is our runway?")).toBe("What is our runway?");
    expect(runTitle("x".repeat(200)).length).toBe(90);
  });
});

describe("itemValue", () => {
  it("shows each cost-model row in its own unit (founder re-test 44)", () => {
    expect(itemValue(10, { cadence: "percent", unit: "%" }, "USD")).toBe("+10 %");
    expect(itemValue(0.5, { cadence: "points", unit: "pts" }, "USD")).toBe("+0.5 pts");
    expect(itemValue(0, { cadence: "points" }, "USD")).toBe("0 pts");
    expect(itemValue(2, { cadence: "count", unit: "people" }, "USD")).toBe("2");
    expect(itemValue(3000, { cadence: "monthly", unit: "USD" }, "USD")).toBe(money(3000, "USD", 0));
  });
});

describe("periodLabel", () => {
  it("names the month or the window a figure is for (founder re-test 45)", () => {
    expect(periodLabel("2026-10")).toBe("Oct 2026");
    expect(periodLabel("2026-08..2026-10")).toBe("Aug–Oct 2026");
    expect(periodLabel("2025-11..2026-10")).toBe("Nov 2025–Oct 2026");
    expect(withPeriod("pnl.csv · rows 2–31", "2026-08..2026-10")).toBe("pnl.csv · rows 2–31 · Aug–Oct 2026");
  });
});
