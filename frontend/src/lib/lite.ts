/**
 * M7b "Lite" mode: no blur and no motion. Automatic on prefers-reduced-motion or a slow device (few cores, little
 * memory, Data Saver), or set in Settings ("on" / "off" / "auto"). Applied as `data-lite="1"` on <html>.
 */
import { useCallback, useEffect, useState } from "react";

export type LiteChoice = "auto" | "on" | "off";
const KEY = "founderos.lite";

interface DeviceHints {
  reducedMotion: boolean;
  cores?: number;
  memoryGb?: number;
  saveData?: boolean;
}

export function slowDevice(h: DeviceHints): boolean {
  return h.reducedMotion || (h.cores !== undefined && h.cores <= 2) || (h.memoryGb !== undefined && h.memoryGb <= 2) || Boolean(h.saveData);
}

export function liteOn(choice: LiteChoice, hints: DeviceHints): boolean {
  if (choice === "on") return true;
  if (choice === "off") return false;
  return slowDevice(hints);
}

function hints(): DeviceHints {
  const nav = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } };
  return {
    reducedMotion: typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    cores: nav.hardwareConcurrency || undefined,
    memoryGb: nav.deviceMemory,
    saveData: nav.connection?.saveData,
  };
}

export function readLite(): LiteChoice {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "on" || v === "off" ? v : "auto";
  } catch {
    return "auto";
  }
}

export function applyLite(choice: LiteChoice = readLite()): boolean {
  const on = liteOn(choice, hints());
  if (on) document.documentElement.dataset.lite = "1";
  else delete document.documentElement.dataset.lite;
  return on;
}

/** The Settings toggle. */
export function useLite(): { choice: LiteChoice; active: boolean; setChoice: (c: LiteChoice) => void } {
  const [choice, setChoiceState] = useState<LiteChoice>(readLite);
  const [active, setActive] = useState(() => applyLite(choice));
  useEffect(() => setActive(applyLite(choice)), [choice]);
  const setChoice = useCallback((c: LiteChoice) => {
    try {
      window.localStorage.setItem(KEY, c);
    } catch {
      // private mode: the choice lasts for this page only
    }
    setChoiceState(c);
  }, []);
  return { choice, active, setChoice };
}
