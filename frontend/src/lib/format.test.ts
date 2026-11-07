import { describe, expect, it } from "vitest";

import { decisionTitle, syncTitle } from "@/lib/format";

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
