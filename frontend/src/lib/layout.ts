/**
 * Founder decision F (M6): the left (Advisor) and right (Agents) panels can be made wider or narrower, and the left one
 * can be folded away. Each viewer's sizes are kept in this browser's storage; missing or blocked storage just means the
 * default sizes.
 */
import { useCallback, useEffect, useState } from "react";

export const LAYOUT_KEY = "founderos.layout.v1";

export const LEFT = { min: 280, max: 720, initial: 380 } as const;
export const RIGHT = { min: 240, max: 560, initial: 300 } as const;
/** The canvas between the panels never gets narrower than this when a panel is dragged wider. */
export const CANVAS_MIN = 420;
/** Width of the folded Advisor panel. */
export const FOLDED_WIDTH = 44;

export interface PanelLayout {
  left: number;
  right: number;
  leftCollapsed: boolean;
}

export const DEFAULT_LAYOUT: PanelLayout = { left: LEFT.initial, right: RIGHT.initial, leftCollapsed: false };

export function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.round(value)));
}

/**
 * The widest a panel may be: its own maximum, and no wider than leaves the canvas `CANVAS_MIN` beside the other panel.
 * `viewport` 0 (unknown, as in tests) means only the panel's own limits apply.
 */
export function maxWidth(side: "left" | "right", layout: PanelLayout, viewport: number): number {
  const limits = side === "left" ? LEFT : RIGHT;
  if (viewport <= 0) return limits.max;
  const other =
    side === "left" ? (railShown(viewport) ? layout.right : 0) : layout.leftCollapsed ? FOLDED_WIDTH : layout.left;
  return Math.max(limits.min, Math.min(limits.max, viewport - other - CANVAS_MIN));
}

/** The right (Agents) panel shows from Tailwind's `xl` breakpoint. */
export const XL = 1280;
export function railShown(viewport: number): boolean {
  return viewport <= 0 || viewport >= XL;
}

/**
 * The widths to draw now. A width saved on a bigger screen is drawn narrower so the canvas keeps its room, but the
 * saved value is kept, so it comes back on the bigger screen.
 */
export function shownWidths(layout: PanelLayout, viewport: number): { left: number; right: number } {
  const right = railShown(viewport) ? clamp(layout.right, RIGHT.min, maxWidth("right", layout, viewport)) : layout.right;
  const left = clamp(layout.left, LEFT.min, maxWidth("left", { ...layout, right }, viewport));
  return { left, right };
}

export function resize(layout: PanelLayout, side: "left" | "right", width: number, viewport: number): PanelLayout {
  const limits = side === "left" ? LEFT : RIGHT;
  const value = clamp(width, limits.min, maxWidth(side, layout, viewport));
  return side === "left" ? { ...layout, left: value, leftCollapsed: false } : { ...layout, right: value };
}

/** Anything stored that is not a sensible layout falls back to the defaults, field by field. */
export function parseLayout(raw: string | null): PanelLayout {
  if (!raw) return DEFAULT_LAYOUT;
  try {
    const saved = JSON.parse(raw) as Partial<PanelLayout> | null;
    if (!saved || typeof saved !== "object") return DEFAULT_LAYOUT;
    return {
      left: typeof saved.left === "number" ? clamp(saved.left, LEFT.min, LEFT.max) : LEFT.initial,
      right: typeof saved.right === "number" ? clamp(saved.right, RIGHT.min, RIGHT.max) : RIGHT.initial,
      leftCollapsed: saved.leftCollapsed === true,
    };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // blocked or full: the sizes are simply not remembered
  }
}

export function loadLayout(): PanelLayout {
  return parseLayout(readStored(LAYOUT_KEY));
}

export function saveLayout(layout: PanelLayout): void {
  writeStored(LAYOUT_KEY, JSON.stringify(layout));
}

export function viewportWidth(): number {
  return typeof window !== "undefined" ? window.innerWidth : 0;
}

/** The window's width, kept current on resize. */
export function useViewportWidth(): number {
  const [width, setWidth] = useState(viewportWidth);
  useEffect(() => {
    const onResize = () => setWidth(viewportWidth());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return width;
}

export interface PanelLayoutApi {
  layout: PanelLayout;
  setWidth: (side: "left" | "right", width: number) => void;
  reset: (side: "left" | "right") => void;
  toggleLeft: () => void;
}

export function usePanelLayout(): PanelLayoutApi {
  const [layout, setLayout] = useState<PanelLayout>(loadLayout);
  useEffect(() => saveLayout(layout), [layout]);
  const setWidth = useCallback(
    (side: "left" | "right", width: number) => setLayout((l) => resize(l, side, width, viewportWidth())),
    [],
  );
  const reset = useCallback(
    (side: "left" | "right") =>
      setLayout((l) => resize(l, side, side === "left" ? LEFT.initial : RIGHT.initial, viewportWidth())),
    [],
  );
  const toggleLeft = useCallback(() => setLayout((l) => ({ ...l, leftCollapsed: !l.leftCollapsed })), []);
  return { layout, setWidth, reset, toggleLeft };
}

/** A small stored value per viewer (the agent window's place and whether it is open). */
export function readJson<T>(key: string, fallback: T, valid: (v: unknown) => v is T): T {
  const raw = readStored(key);
  if (!raw) return fallback;
  try {
    const value: unknown = JSON.parse(raw);
    return valid(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function writeJson(key: string, value: unknown): void {
  writeStored(key, JSON.stringify(value));
}
