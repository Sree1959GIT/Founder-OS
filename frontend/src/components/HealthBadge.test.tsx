import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import { HealthBadge } from "@/components/HealthBadge";
import type { HealthResponse } from "@/lib/api";

const healthy: HealthResponse = {
  status: "degraded",
  version: "0.1.0",
  workspace_id: "default",
  currency: "USD",
  checked_at: "2026-11-02T16:00:00Z",
  dependencies: [
    { name: "ollama", state: "ok", detail: "Ollama is running", required: true, info: {} },
    { name: "qdrant", state: "unavailable", detail: "Qdrant not reachable", required: false, info: {} },
    { name: "cloud", state: "not_configured", detail: "Cloud is disabled", required: false, info: { cloud_allowed: false } },
    {
      name: "gpu",
      state: "ok",
      detail: "RTX",
      required: false,
      info: { vram_used_gb: 7.9, vram_total_gb: 12 },
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

describe("HealthBadge", () => {
  it("labels every dependency with text, not colour alone", () => {
    render(<HealthBadge health={{ kind: "ready", data: healthy }} />);
    expect(screen.getByText("Ollama")).toBeInTheDocument();
    expect(screen.getByText("GPU 7.9/12 GB")).toBeInTheDocument();
    expect(screen.getByText("(down)")).toBeInTheDocument();
    expect(screen.getByText("(off)")).toBeInTheDocument();
    expect(screen.getByText("Qdrant").closest("li")).toHaveAttribute("title", "Qdrant not reachable");
  });

  it("shows backend offline", () => {
    render(<HealthBadge health={{ kind: "offline", message: "Backend not reachable" }} />);
    expect(screen.getByText("Backend offline")).toBeInTheDocument();
  });
});

describe("App", () => {
  it("fetches /api/health through the proxy and renders the status", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(healthy), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await waitFor(() => expect(screen.getByText("Ollama")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.anything());
    expect(screen.getByText("Local only")).toBeInTheDocument();
  });

  it("survives the backend being down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<App />);
    await waitFor(() => expect(screen.getByText("Backend offline")).toBeInTheDocument());
  });
});
