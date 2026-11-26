import { describe, expect, it } from "vitest";

import { liteOn, slowDevice } from "@/lib/lite";

describe("Lite mode (M7b)", () => {
  it("turns on by itself for reduced motion or a slow device", () => {
    expect(slowDevice({ reducedMotion: true })).toBe(true);
    expect(slowDevice({ reducedMotion: false, cores: 2 })).toBe(true);
    expect(slowDevice({ reducedMotion: false, memoryGb: 2 })).toBe(true);
    expect(slowDevice({ reducedMotion: false, saveData: true })).toBe(true);
    expect(slowDevice({ reducedMotion: false, cores: 8, memoryGb: 8 })).toBe(false);
  });
  it("follows the Settings choice over the device", () => {
    expect(liteOn("on", { reducedMotion: false, cores: 16 })).toBe(true);
    expect(liteOn("off", { reducedMotion: true })).toBe(false);
    expect(liteOn("auto", { reducedMotion: true })).toBe(true);
  });
});
