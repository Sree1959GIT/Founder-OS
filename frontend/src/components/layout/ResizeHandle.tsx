import { useRef, type KeyboardEvent, type PointerEvent } from "react";

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
 */
export function ResizeHandle({ side, label, width, min, max, onResize, onReset, className }: Props) {
  const drag = useRef<{ x: number; width: number } | null>(null);
  const grow = side === "left" ? 1 : -1;

  const down = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    drag.current = { x: e.clientX, width };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    onResize(drag.current.width + grow * (e.clientX - drag.current.x));
  };
  const up = (e: PointerEvent<HTMLDivElement>) => {
    drag.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
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
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onDoubleClick={onReset}
      onKeyDown={key}
      className={cn(
        "group relative z-10 hidden w-1.5 shrink-0 cursor-col-resize touch-none select-none md:block",
        "focus-visible:outline-none",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover:w-0.5 group-hover:bg-signal group-focus-visible:w-0.5 group-focus-visible:bg-signal"
      />
    </div>
  );
}
