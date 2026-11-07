import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SettingsView } from "@/lib/api";

const base: SettingsView = {
  cloud_allowed: false,
  deep_provider: "anthropic",
  agent_models: {},
  cloud_monthly_cap_usd: 20,
  team_approval: "cloud_only",
  max_local_agents: 2,
  max_cloud_agents: 4,
  providers: [
    { name: "ollama", configured: true },
    { name: "anthropic", configured: false },
  ],
  agents: [],
  spend: { spent_usd: 0 },
  privacy_note: "Local first.",
};

const putSettings = vi.fn(async (update: Partial<SettingsView>) => ({ ...base, ...update }));
vi.mock("@/lib/api", () => ({
  fetchSettings: vi.fn(async () => base),
  putSettings: (update: Partial<SettingsView>) => putSettings(update),
}));

const { SettingsPanel } = await import("@/components/panels/SettingsPanel");
const { useRoute } = await import("@/hooks/useRoute");

function Shell() {
  const route = useRoute();
  return route.view === "settings" ? <SettingsPanel /> : <p>Elsewhere</p>;
}

describe("settings save only on Save (founder review 36)", () => {
  beforeEach(() => {
    putSettings.mockClear();
    window.location.hash = "#/settings";
  });

  it("changes nothing, cloud included, until Save; Discard puts it back", async () => {
    render(<SettingsPanel />);
    const cloud = await screen.findByLabelText("Allow cloud agents");
    expect(screen.queryByText("Cloud agents at once")).not.toBeInTheDocument(); // review 4: hidden with cloud off
    expect(screen.getByText("ollama: local")).toBeInTheDocument(); // review 34
    fireEvent.click(cloud);
    expect(putSettings).not.toHaveBeenCalled();
    expect(screen.getByTestId("unsaved").textContent).toContain("You have unsaved changes");
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect((screen.getByLabelText("Allow cloud agents") as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByTestId("unsaved")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Allow cloud agents"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ cloud_allowed: true }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("asks before leaving for another page: Stay keeps the changes, Discard leaves without saving", async () => {
    render(<Shell />);
    fireEvent.click(await screen.findByLabelText("Allow cloud agents"));
    const goToData = async () => {
      await act(async () => {
        window.location.hash = "#/data";
        await new Promise((resolve) => setTimeout(resolve, 20));
      });
      return screen.findByRole("alertdialog", { name: "Save your changes?" });
    };
    let dialog = await goToData();
    fireEvent.click(within(dialog).getByRole("button", { name: "Stay" }));
    expect(screen.queryByText("Elsewhere")).not.toBeInTheDocument();
    expect(screen.getByTestId("unsaved")).toBeInTheDocument();
    dialog = await goToData();
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));
    expect(await screen.findByText("Elsewhere")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/data");
    expect(putSettings).not.toHaveBeenCalled();
  });
});
