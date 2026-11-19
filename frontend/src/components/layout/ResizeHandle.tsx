import { useEffect, useRef, type KeyboardEvent, type PointerEvent } from "react";

import { cn } from "@/lib/utils";

const STEP = 16;

interface Props {
  /** Which panel this handle sizes: the left one grows to the right, the right one grows to the left. */
  side: "left" | "right";
  label: string;
  width: number;
  min: number;
  max: number;
  onResize: (width: number) => void;
  onReset: () => void;
  className?: string;
}

/**
 * The edge of a panel (founder decision F). Drag it, or focus it and use the arrow keys; Home or a double-click goes
 * back to the default width. Shown from the `md` breakpoint, where the panels sit side by side.
 *
 * Founder M6 gate D6: on a 125 % screen the 6 px edge with a 1 px line could not be found or grabbed. The hit area is
 * now 12 px (it reaches over the panels' own borders), a grip is always drawn, and a drag follows the pointer on the
 * whole window, so it does not depend on pointer capture.
 */
export function ResizeHandle({ side, label, width, min, max, onResize, onReset, className }: Props) {
  const drag = useRef<{ x: number; width: number } | null>(null);
  const resizeRef = useRef(onResize);
  resizeRef.current = onResize;
  const stopRef = useRef<() => void>(() => undefined);
  const grow = side === "left" ? 1 : -1;

  useEffect(() => () => stopRef.current(), []);

  const down = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    stopRef.current();
    drag.current = { x: e.clientX, width };
    const move = (ev: globalThis.PointerEvent) => {
      if (!drag.current) return;
      resizeRef.current(drag.current.width + grow * (ev.clientX - drag.current.x));
    };
    const stop = () => {
      drag.current = null;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      document.body.style.removeProperty("cursor");
      document.body.style.removeProperty("user-select");
      stopRef.current = () => undefined;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    stopRef.current = stop;
  };
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowLeft") onResize(width - grow * STEP);
    else if (e.key === "ArrowRight") onResize(width + grow * STEP);
    else if (e.key === "Home") onReset();
    else return;
    e.preventDefault();
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      title={`${label}: drag, or use the arrow keys. Double-click for the default width.`}
      data-testid={`resize-${side}`}
      onPointerDown={down}
      onDoubleClick={(e) => {
        e.preventDefault();
        stopRef.current();
        onReset();
      }}
      onKeyDown={key}
      className={cn(
        "group relative z-20 -mx-1 hidden w-3 shrink-0 cursor-col-resize touch-none select-none md:block",
        "focus-visible:outline-none",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover:w-0.5 group-hover:bg-signal group-focus-visible:w-0.5 group-focus-visible:bg-signal"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/2 h-10 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-muted-foreground/40 transition-colors group-hover:bg-signal group-focus-visible:bg-signal"
      />
    </div>
  );
}
