import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AIModelTestResult, AIModelView, DecisionFrame, SettingsView } from "@/lib/api";
import { currencyMissing } from "@/lib/currency";
import { proposedFrame } from "@/lib/proposal";
import type { RunView } from "@/lib/workspace";

/** M7a fix round 3 (founder F4b, F7b, F12b, F13). Fakes only. */

const presets = [
  { id: "qwen_local", label: "Qwen", title: "Qwen on our server (free, private, slower)", needs_key: false },
  { id: "gemini", label: "Gemini", title: "Gemini (Google AI Studio key)", needs_key: true },
].map((p) => ({ custom_base_url: false, base_url: "", default_model: "", key_hint: "the dashboard", ...p }));

const local: AIModelView = {
  in_use: { preset: "qwen_local", label: "Qwen", model: "qwen3:8b", verified: false, local: true },
  saved: null,
  cloud_paused: false,
  secret_ready: true,
  secret_problem: null,
  test_timeout_s: 15,
  key_shapes: [{ prefix: "AQ.", preset: "gemini" }],
  presets,
};
const verified: AIModelView = {
  ...local,
  in_use: { preset: "gemini", label: "Gemini", model: "gemini-3.8-flash", verified: true, local: false },
  saved: {
    preset: "gemini",
    label: "Gemini",
    model: "gemini-3.8-flash",
    base_url: "",
    key_masked: "••••abcd",
    verified_at: "2026-11-26T05:00:00Z",
    unreadable: false,
    models: [{ id: "gemini-3.8-flash", label: "" }],
  },
};
const cloudOn: SettingsView = {
  cloud_allowed: true,
  deep_provider: "ollama",
  agent_models: {},
  cloud_monthly_cap_usd: 10,
  team_approval: "cloud_only",
  max_local_agents: 2,
  max_cloud_agents: 4,
  providers: [{ name: "ollama", configured: true }],
  agents: [{ type: "market_scout", title: "Market Scout", privacy: "cloud_allowed", job: "Market" }],
  spend: { spent_usd: 0.5 },
  privacy_note: "Local first.",
  ai_model: { preset: "gemini", label: "Gemini", model: "gemini-3.8-flash", text: "Gemini · gemini-3.8-flash (from AI model)" },
  cloud_usable: true,
  member_currency: "INR",
  fx: { asked: "INR", currency: "INR", symbol: "₹", rate: 84, as_of: "2026-11-26", source: "open.er-api.com" },
};

const testAIModel = vi.fn<(body: unknown) => Promise<AIModelTestResult>>();
let card: AIModelView = verified;
let current: SettingsView = cloudOn;
const fetchSettings = vi.fn(async () => current);
vi.mock("@/lib/api", () => ({
  fetchAIModel: vi.fn(async () => card),
  testAIModel: (body: unknown) => testAIModel(body),
  removeAIModelKey: vi.fn(async () => {
    // What the backend now does on Remove key: the key goes, and cloud is turned off and saved (founder F4b).
    current = { ...current, cloud_allowed: false, cloud_usable: false, ai_model: null };
    card = local;
    return local;
  }),
  switchToLocalAIModel: vi.fn(async () => local),
  fetchSettings: () => fetchSettings(),
  putSettings: vi.fn(async (update: Partial<SettingsView>) => ({ ...current, ...update })),
}));

const { AIModelCard } = await import("@/components/panels/AIModelCard");
const { SettingsPanel } = await import("@/components/panels/SettingsPanel");

describe("fix round 3", () => {
  beforeEach(() => {
    card = verified;
    current = cloudOn;
    testAIModel.mockReset();
    fetchSettings.mockClear();
  });

  it("F4b: Remove key unticks and greys out Allow cloud agents, with the note", async () => {
    render(<SettingsPanel />);
    const cloud = (await screen.findByTestId("cloud-allowed")) as HTMLInputElement;
    expect(cloud.checked).toBe(true);
    fireEvent.click(await screen.findByRole("button", { name: "Remove key" }));
    await waitFor(() => expect(cloud.checked).toBe(false));
    expect(cloud).toBeDisabled();
    expect(screen.getByTestId("cloud-needs-key")).toHaveTextContent("Test and save a key");
    expect(screen.queryByTestId("unsaved")).not.toBeInTheDocument(); // saved on the server, not a page edit
  });

  it("F7b: a used-up Gemini free quota is a yellow notice and the green chip stays", async () => {
    const line = "Your Gemini key has reached its free limit for now. Try again later, or add billing in Google AI Studio.";
    testAIModel.mockResolvedValue({ ok: false, code: "free_limit", message: line, view: verified });
    render(<AIModelCard />);
    fireEvent.change(await screen.findByLabelText("Change model (optional)"), { target: { value: "gemini-3.8-flash" } });
    expect(await screen.findByTestId("ai-model-notice")).toHaveTextContent(line);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByTestId("ai-model-verified")).toHaveTextContent("Gemini · gemini-3.8-flash · key verified");
  });

  it("F12b: a currency the backend sends as null is still saved from the browser's region", () => {
    expect(currencyMissing(null)).toBe(true);
    expect(currencyMissing(undefined)).toBe(true);
    expect(currencyMissing("")).toBe(true);
    expect(currencyMissing("INR")).toBe(false);
  });

  it("F13: a later answer's memo moves the Proposed mark on the open decision's frame", () => {
    const frame = {
      subject: "Dubai office",
      options: [{ name: "Travel-led pilot" }, { name: "Partner or distributor" }],
      default_option: "Travel-led pilot",
    } as unknown as DecisionFrame;
    const later = { frame: null, result: { memo: { chosen: "Partner or distributor" } } } as unknown as RunView;
    expect(proposedFrame(frame, later).default_option).toBe("Partner or distributor");
    expect(proposedFrame(frame, null)).toBe(frame);
    const own = { ...later, frame } as unknown as RunView; // a run with its own frame: the backend already aligned it
    expect(proposedFrame(frame, own)).toBe(frame);
    const stranger = { frame: null, result: { memo: { chosen: "Something else" } } } as unknown as RunView;
    expect(proposedFrame(frame, stranger)).toBe(frame);
  });
});
