import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AIModelTestResult, AIModelView } from "@/lib/api";

const presets = [
  {
    id: "qwen_local",
    label: "Qwen",
    title: "Qwen on our server (free, private, slower)",
    needs_key: false,
    custom_base_url: false,
    base_url: "",
    default_model: "qwen3:8b",
    key_hint: "",
  },
  {
    id: "claude",
    label: "Claude",
    title: "Claude (Anthropic API key)",
    needs_key: true,
    custom_base_url: false,
    base_url: "https://api.anthropic.com",
    default_model: "claude-sonnet-5-5",
    key_hint: "console.anthropic.com",
  },
  {
    id: "gemini",
    label: "Gemini",
    title: "Gemini (Google AI Studio key)",
    needs_key: true,
    custom_base_url: false,
    base_url: "https://generativelanguage.googleapis.com",
    default_model: "gemini-3.8-flash",
    key_hint: "aistudio.google.com",
  },
  {
    id: "custom",
    label: "Custom",
    title: "Custom (any OpenAI-compatible server)",
    needs_key: true,
    custom_base_url: true,
    base_url: "",
    default_model: "",
    key_hint: "your provider's dashboard",
  },
];
const local: AIModelView = {
  in_use: {
    preset: "qwen_local",
    label: "Qwen",
    model: "qwen3:8b",
    verified: false,
    local: true,
  },
  saved: null,
  cloud_paused: false,
  secret_ready: true,
  secret_problem: null,
  test_timeout_s: 15,
  key_shapes: [
    { prefix: "sk-ant-", preset: "claude" },
    { prefix: "sk-or-", preset: "openrouter" },
    { prefix: "gsk_", preset: "groq" },
    { prefix: "AIza", preset: "gemini" },
    { prefix: "sk-proj-", preset: "openai" },
    { prefix: "sk-", preset: "openai" },
  ],
  presets,
};
const verified: AIModelView = {
  ...local,
  in_use: {
    preset: "claude",
    label: "Claude",
    model: "claude-sonnet-5-5",
    verified: true,
    local: false,
  },
  saved: {
    preset: "claude",
    label: "Claude",
    model: "claude-sonnet-5-5",
    base_url: "",
    key_masked: "••••9f3c",
    verified_at: "2026-11-22T16:00:00Z",
    unreadable: false,
    models: [
      { id: "claude-sonnet-5-5", label: "Claude Sonnet 5.5" },
      { id: "claude-haiku-5-5", label: "Claude Haiku 5.5" },
    ],
  },
};

const testAIModel = vi.fn<(body: unknown) => Promise<AIModelTestResult>>();
const removeAIModelKey = vi.fn(async () => local);
const switchToLocalAIModel = vi.fn(async () => ({
  ...verified,
  in_use: local.in_use,
}));
let initial: AIModelView = local;
vi.mock("@/lib/api", () => ({
  fetchAIModel: vi.fn(async () => initial),
  testAIModel: (body: unknown) => testAIModel(body),
  removeAIModelKey: () => removeAIModelKey(),
  switchToLocalAIModel: () => switchToLocalAIModel(),
}));

const { AIModelCard } = await import("@/components/panels/AIModelCard");

describe("AI model card (M7a, key-only setup F2/F3)", () => {
  beforeEach(() => {
    initial = local;
    testAIModel.mockReset();
    removeAIModelKey.mockClear();
  });

  it("starts grey on Qwen and offers only API-key presets", async () => {
    render(<AIModelCard />);
    expect(await screen.findByTestId("ai-model-local")).toHaveTextContent(
      "In use: Qwen on our server · qwen3:8b",
    );
    expect(screen.getByTestId("ai-model-card")).toHaveAttribute(
      "data-state",
      "grey",
    );
    expect(screen.queryByTestId("ai-model-verified")).not.toBeInTheDocument();
    const options = Array.from(
      (screen.getByLabelText("Model provider") as HTMLSelectElement).options,
    ).map((o) => o.text);
    expect(options[0]).toBe("Qwen on our server (free, private, slower)");
    expect(options.join(" ")).not.toMatch(/sign in|oauth|pro\/max/i);
  });

  it("stays grey on a failed test and shows the plain-English reason", async () => {
    testAIModel.mockResolvedValue({
      ok: false,
      code: "wrong_key",
      message: "Wrong key: Claude did not accept it.",
      preset: "claude",
      view: local,
    });
    const onChanged = vi.fn();
    render(<AIModelCard onChanged={onChanged} />);
    fireEvent.change(await screen.findByLabelText(/API key/), {
      target: { value: "sk-ant-xyz" },
    });
    expect(screen.queryByLabelText("Model")).not.toBeInTheDocument(); // F3: no free-text model box
    expect(screen.queryByLabelText("Server address")).not.toBeInTheDocument(); // F3: Advanced is Custom only
    fireEvent.click(screen.getByRole("button", { name: "Test key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Wrong key: Claude did not accept it.",
    );
    expect(testAIModel).toHaveBeenCalledWith({
      preset: "claude",
      model: "",
      base_url: "",
      api_key: "sk-ant-xyz",
    });
    expect(screen.getByTestId("ai-model-card")).toHaveAttribute(
      "data-state",
      "grey",
    );
  });

  it("F3: the provider is found from the key's shape; the list still overrides it", async () => {
    render(<AIModelCard />);
    const key = await screen.findByLabelText(/API key/);
    const provider = screen.getByLabelText(
      "Model provider",
    ) as HTMLSelectElement;
    fireEvent.change(key, { target: { value: "AIzaSyFAKE000" } });
    expect(provider.value).toBe("gemini");
    expect(screen.getByTestId("ai-key-hint")).toHaveTextContent(
      "Looks like a Gemini key",
    );
    fireEvent.change(key, { target: { value: "sk-ant-api03-FAKE" } });
    expect(provider.value).toBe("claude");
    fireEvent.change(provider, { target: { value: "custom" } }); // manual override
    fireEvent.change(key, { target: { value: "AIzaSyOTHER" } });
    expect(provider.value).toBe("custom");
    expect(screen.getByLabelText("Server address")).not.toBeDisabled();
  });

  it("F3: an unknown key shape on Qwen asks the backend, which says to pick the provider", async () => {
    testAIModel.mockResolvedValue({
      ok: false,
      code: "unknown_provider",
      message: "FounderOS can't tell which provider this key is for.",
      view: local,
    });
    render(<AIModelCard />);
    fireEvent.change(await screen.findByLabelText(/API key/), {
      target: { value: "0123.ollama" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "can't tell which provider",
    );
    expect(testAIModel).toHaveBeenCalledWith({
      preset: "",
      model: "",
      base_url: "",
      api_key: "0123.ollama",
    });
  });

  it("F2: the key box is masked but is not a password field, outside any form", async () => {
    const { container } = render(<AIModelCard />);
    const key = (await screen.findByLabelText(/API key/)) as HTMLInputElement;
    expect(key.type).toBe("text");
    expect(key).toHaveClass("secret-field");
    expect(key).toHaveAttribute("autocomplete", "off");
    expect(key).toHaveAttribute("data-lpignore", "true");
    expect(key).toHaveAttribute("data-1p-ignore", "true");
    expect(key.name).not.toMatch(/pass/i);
    expect(container.querySelector("form")).toBeNull();
    expect(container.querySelector('input[type="password"]')).toBeNull();
    fireEvent.change(key, { target: { value: "sk-ant-api03-FAKE" } });
    expect(key.type).toBe("text"); // still not a password field once it holds a key
    for (const button of screen.getAllByRole("button"))
      expect(button).toHaveAttribute("type", "button");
  });

  it("F3: Change model offers the key's models and re-tests with the saved key", async () => {
    initial = verified;
    testAIModel.mockResolvedValue({
      ok: true,
      code: "ok",
      message: "Claude · claude-haiku-5-5 · key verified",
      preset: "claude",
      view: {
        ...verified,
        in_use: { ...verified.in_use, model: "claude-haiku-5-5" },
      },
    });
    render(<AIModelCard />);
    const change = (await screen.findByLabelText(
      "Change model (optional)",
    )) as HTMLSelectElement;
    expect(Array.from(change.options).map((o) => o.value)).toEqual([
      "claude-sonnet-5-5",
      "claude-haiku-5-5",
    ]);
    fireEvent.change(change, { target: { value: "claude-haiku-5-5" } });
    expect(await screen.findByTestId("ai-model-verified")).toHaveTextContent(
      "Claude · claude-haiku-5-5 · key verified",
    );
    expect(testAIModel).toHaveBeenCalledWith({
      preset: "claude",
      model: "claude-haiku-5-5",
      base_url: "",
      api_key: "",
    });
  });

  it("Remove key goes back to Qwen", async () => {
    initial = verified;
    render(<AIModelCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove key" }));
    await waitFor(() => expect(removeAIModelKey).toHaveBeenCalled());
    expect(await screen.findByTestId("ai-model-local")).toBeInTheDocument();
    expect(screen.queryByText(/••••/)).not.toBeInTheDocument();
  });

  it("Custom shows Advanced with the server address and an optional model name", async () => {
    testAIModel.mockResolvedValue({
      ok: false,
      code: "bad_url",
      message: "Enter the server's full address",
      view: local,
    });
    render(<AIModelCard />);
    fireEvent.change(await screen.findByLabelText("Model provider"), {
      target: { value: "custom" },
    });
    expect(screen.getByText("Advanced")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Server address"), {
      target: { value: "https://llm.example.com/v1" },
    });
    fireEvent.change(screen.getByLabelText(/API key/), {
      target: { value: "abc123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test key" }));
    await waitFor(() =>
      expect(testAIModel).toHaveBeenCalledWith({
        preset: "custom",
        model: "",
        base_url: "https://llm.example.com/v1",
        api_key: "abc123",
      }),
    );
  });
});
