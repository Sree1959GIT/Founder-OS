import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AIModelTestResult, AIModelView, SettingsView } from "@/lib/api";
import { browserCurrency, moneyText } from "@/lib/currency";

/** M7a gate fix round 2 (founder F4–F7, F12): the AI model card and Settings. Fakes only. */

const presets = [
  { id: "qwen_local", label: "Qwen", title: "Qwen on our server (free, private, slower)", needs_key: false },
  { id: "claude", label: "Claude", title: "Claude (Anthropic API key)", needs_key: true },
  { id: "gemini", label: "Gemini", title: "Gemini (Google AI Studio key)", needs_key: true },
].map((p) => ({ custom_base_url: false, base_url: "", default_model: "", key_hint: "the dashboard", ...p }));

const local: AIModelView = {
  in_use: { preset: "qwen_local", label: "Qwen", model: "qwen3:8b", verified: false, local: true },
  saved: null,
  cloud_paused: false,
  secret_ready: true,
  secret_problem: null,
  test_timeout_s: 15,
  key_shapes: [
    { prefix: "sk-ant-", preset: "claude" },
    { prefix: "AQ.", preset: "gemini" },
    { prefix: "AIza", preset: "gemini" },
  ],
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
const settings: SettingsView = {
  cloud_allowed: false,
  deep_provider: "ollama",
  agent_models: {},
  cloud_monthly_cap_usd: 10,
  team_approval: "cloud_only",
  max_local_agents: 2,
  max_cloud_agents: 4,
  providers: [
    { name: "ollama", configured: true },
    { name: "gemini", configured: false },
  ],
  agents: [{ type: "market_scout", title: "Market Scout", privacy: "cloud_allowed", job: "Market" }],
  spend: { spent_usd: 0.5 },
  privacy_note: "Local first.",
  ai_model: null,
  cloud_usable: false,
  member_currency: "INR",
  fx: { asked: "INR", currency: "INR", symbol: "₹", rate: 84, as_of: "2026-11-26", source: "open.er-api.com" },
};

const testAIModel = vi.fn<(body: unknown) => Promise<AIModelTestResult>>();
let card: AIModelView = local;
let current: SettingsView = settings;
const fetchSettings = vi.fn(async () => current);
const putSettings = vi.fn(async (update: Partial<SettingsView>) => ({ ...current, ...update }));
vi.mock("@/lib/api", () => ({
  fetchAIModel: vi.fn(async () => card),
  testAIModel: (body: unknown) => testAIModel(body),
  removeAIModelKey: vi.fn(async () => local),
  switchToLocalAIModel: vi.fn(async () => local),
  fetchSettings: () => fetchSettings(),
  putSettings: (update: Partial<SettingsView>) => putSettings(update),
}));

const { AIModelCard, UNKNOWN_KEY } = await import("@/components/panels/AIModelCard");
const { SettingsPanel } = await import("@/components/panels/SettingsPanel");

describe("AI model card, fix round 2", () => {
  beforeEach(() => {
    card = local;
    current = settings;
    testAIModel.mockReset();
    fetchSettings.mockClear();
    putSettings.mockClear();
  });

  it("F4: a failed test leaves the page alone (no refresh, so no cloud tick and no unsaved bar)", async () => {
    testAIModel.mockResolvedValue({ ok: false, code: "wrong_key", message: "Wrong key: Claude did not accept it.", view: local });
    const onChanged = vi.fn();
    render(<AIModelCard onChanged={onChanged} />);
    fireEvent.change(await screen.findByLabelText(/API key/), { target: { value: "sk-ant-wrong-000" } });
    fireEvent.click(screen.getByRole("button", { name: "Test key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong key");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("F4: in Settings, cloud cannot be ticked without a passing key, and a failed test changes nothing", async () => {
    testAIModel.mockResolvedValue({ ok: false, code: "wrong_key", message: "Wrong key: Claude did not accept it.", view: local });
    render(<SettingsPanel />);
    const cloud = (await screen.findByTestId("cloud-allowed")) as HTMLInputElement;
    expect(cloud).toBeDisabled();
    expect(screen.getByTestId("cloud-needs-key")).toHaveTextContent("Test and save a key");
    fireEvent.change(await screen.findByLabelText(/API key/), { target: { value: "sk-ant-wrong-000" } });
    fireEvent.click(screen.getByRole("button", { name: "Test key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong key");
    expect(cloud.checked).toBe(false);
    expect(screen.queryByTestId("unsaved")).not.toBeInTheDocument();
    expect(fetchSettings).toHaveBeenCalledTimes(1); // only the first load
  });

  it("F5: an AQ. key is Gemini; an unknown start says so and points to the provider list", async () => {
    render(<AIModelCard />);
    const key = await screen.findByLabelText(/API key/);
    const provider = screen.getByLabelText("Model provider") as HTMLSelectElement;
    fireEvent.change(key, { target: { value: "AQ.Ab8RN6Lfake" } });
    expect(provider.value).toBe("gemini");
    fireEvent.change(provider, { target: { value: "qwen_local" } }); // picking Qwen re-detects from the key
    expect(provider.value).toBe("gemini");
    fireEvent.change(key, { target: { value: "zz-unknown-key" } });
    fireEvent.change(provider, { target: { value: "qwen_local" } });
    expect(provider.value).toBe("qwen_local");
    expect(screen.getByTestId("ai-key-hint")).toHaveTextContent(UNKNOWN_KEY);
    expect(provider).toHaveAttribute("data-attention", "true");
    expect(provider).toHaveAttribute("aria-describedby", "ai-key-hint");
  });

  it("F5: Discard on the page makes the card read the key's shape again", async () => {
    render(<SettingsPanel />);
    const key = await screen.findByLabelText(/API key/);
    const provider = screen.getByLabelText("Model provider") as HTMLSelectElement;
    fireEvent.change(provider, { target: { value: "claude" } }); // a manual pick
    fireEvent.change(key, { target: { value: "AQ.Ab8RN6Lfake" } });
    expect(provider.value).toBe("claude");
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USD" } });
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(provider.value).toBe("gemini"));
  });

  it("F7: busy is a yellow notice, not a red error, and the green chip stays", async () => {
    card = verified;
    testAIModel.mockResolvedValue({
      ok: false,
      code: "busy",
      message: "Gemini is busy right now (Google error 503). Your key is fine. Try again in a minute.",
      view: verified,
    });
    render(<AIModelCard />);
    fireEvent.change(await screen.findByLabelText("Change model (optional)"), { target: { value: "gemini-3.8-flash" } });
    expect(await screen.findByTestId("ai-model-notice")).toHaveTextContent("Your key is fine");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByTestId("ai-model-verified")).toHaveTextContent("Gemini · gemini-3.8-flash · key verified");
  });
});

describe("Settings, fix round 2", () => {
  beforeEach(() => {
    card = verified;
    putSettings.mockClear();
  });

  it("F6: the Cloud section and Default name the verified AI model", async () => {
    current = {
      ...settings,
      cloud_allowed: true,
      cloud_usable: true,
      ai_model: { preset: "gemini", label: "Gemini", model: "gemini-3.8-flash", text: "Gemini · gemini-3.8-flash (from AI model)" },
    };
    render(<SettingsPanel />);
    expect(await screen.findByTestId("cloud-in-use")).toHaveTextContent("Gemini · gemini-3.8-flash (from AI model)");
    expect(screen.getByText("gemini: no .env key")).toBeInTheDocument();
    expect(screen.queryByText("gemini: no key")).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Default: Gemini · gemini-3.8-flash (from AI model)" })).toBeInTheDocument();
  });

  it("F12: the cap is entered and shown in the member's currency and saved in USD; the month in rupees", async () => {
    current = settings;
    render(<SettingsPanel />);
    const cap = (await screen.findByLabelText("Monthly cost cap (INR)")) as HTMLInputElement;
    expect(cap.value).toBe("840");
    expect(screen.getByTestId("month-spend")).toHaveTextContent("about ₹42 ($0.50)");
    fireEvent.change(cap, { target: { value: "1680" } });
    fireEvent.blur(cap);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ cloud_monthly_cap_usd: 20 }));
  });

  it("F12: the browser's region gives the default currency, and amounts read as estimates", () => {
    expect(browserCurrency(["en-IN"])).toBe("INR");
    expect(browserCurrency(["de-DE", "en"])).toBe("EUR");
    expect(browserCurrency(["en"])).toBe("USD");
    expect(moneyText(0.012, "₹", 84)).toBe("about ₹1");
    expect(moneyText(0.0001, "₹", 84)).toBe("less than ₹0.01");
  });
});
