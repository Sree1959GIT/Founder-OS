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

describe("AI model card (M7a)", () => {
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
      view: local,
    });
    const onChanged = vi.fn();
    render(<AIModelCard onChanged={onChanged} />);
    fireEvent.change(await screen.findByLabelText("Model provider"), {
      target: { value: "claude" },
    });
    expect((screen.getByLabelText("Model") as HTMLInputElement).value).toBe(
      "claude-sonnet-5-5",
    );
    expect(screen.getByLabelText("Server address")).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/API key/), {
      target: { value: "sk-ant-xyz" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Wrong key: Claude did not accept it.",
    );
    expect(testAIModel).toHaveBeenCalledWith({
      preset: "claude",
      model: "claude-sonnet-5-5",
      base_url: "https://api.anthropic.com",
      api_key: "sk-ant-xyz",
    });
    expect(screen.getByTestId("ai-model-card")).toHaveAttribute(
      "data-state",
      "grey",
    );
  });

  it("turns green with the chip when the test passes, and clears the key box", async () => {
    testAIModel.mockResolvedValue({
      ok: true,
      code: "ok",
      message: "Claude · claude-sonnet-5-5 · key verified",
      view: verified,
    });
    const onChanged = vi.fn();
    render(<AIModelCard onChanged={onChanged} />);
    fireEvent.change(await screen.findByLabelText("Model provider"), {
      target: { value: "claude" },
    });
    fireEvent.change(screen.getByLabelText(/API key/), {
      target: { value: "sk-ant-xyz" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test key" }));
    expect(await screen.findByTestId("ai-model-verified")).toHaveTextContent(
      "Claude · claude-sonnet-5-5 · key verified",
    );
    expect(screen.getByTestId("ai-model-card")).toHaveAttribute(
      "data-state",
      "verified",
    );
    expect((screen.getByLabelText(/API key/) as HTMLInputElement).value).toBe(
      "",
    );
    expect(screen.getByTestId("ai-model-saved")).toHaveTextContent("••••9f3c");
    expect(onChanged).toHaveBeenCalled();
  });

  it("Remove key goes back to Qwen", async () => {
    initial = verified;
    render(<AIModelCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove key" }));
    await waitFor(() => expect(removeAIModelKey).toHaveBeenCalled());
    expect(await screen.findByTestId("ai-model-local")).toBeInTheDocument();
    expect(screen.queryByText(/••••/)).not.toBeInTheDocument();
  });

  it("Custom lets the member type the server address", async () => {
    render(<AIModelCard />);
    fireEvent.change(await screen.findByLabelText("Model provider"), {
      target: { value: "custom" },
    });
    expect(screen.getByLabelText("Server address")).not.toBeDisabled();
  });
});
