/* eslint-disable react-refresh/only-export-components -- the roster and the faces belong together */
/**
 * M7b: one ORIGINAL face family for every agent type, the Advisor (the host) included. Each has its own shape and
 * colour, two eyes and a small mouth; the Devil's Advocate has small horns. Inline SVG, decorative (the name is text).
 */
import { cn } from "@/lib/utils";

type Shape = "circle" | "square" | "hex" | "tall" | "squircle" | "pill" | "shield" | "diamond" | "drop";

interface Member {
  name: string;
  /** One plain line on what this advisor does. */
  role: string;
  color: string;
  shape: Shape;
  horns?: boolean;
}

export const TEAM: Record<string, Member> = {
  advisor: { name: "Advisor", role: "Your host. Runs the meeting and gives you the answer.", color: "#F4EFE6", shape: "circle" },
  financial_analyst: { name: "Financial Analyst", role: "Checks every number against your own books.", color: "#6EE0B0", shape: "square" },
  market_scout: { name: "Market Scout", role: "Looks at the market, prices and competitors.", color: "#8FB4FF", shape: "hex" },
  librarian: { name: "Librarian", role: "Finds what you wrote and decided before.", color: "#C9A7FF", shape: "tall" },
  people_ops: { name: "People & Ops", role: "Hiring, the team and what people cost.", color: "#FFC857", shape: "squircle" },
  revenue_customer: { name: "Revenue & Customer", role: "Customers, pricing and where revenue comes from.", color: "#5ED6E0", shape: "pill" },
  regulatory_tax: { name: "Regulatory & Tax", role: "Rules, licences and tax, in plain words.", color: "#B9C2DD", shape: "shield" },
  prioritiser: { name: "Prioritiser", role: "Weighs the options against your goals.", color: "#FF9DBB", shape: "diamond" },
  perspective_lens: { name: "Perspective Lens", role: "Looks at it from another angle.", color: "#B5E655", shape: "drop" },
  devils_advocate: { name: "Devil's Advocate", role: "Argues against it, to find the risks.", color: "#FF7A6B", shape: "circle", horns: true },
  memo_writer: { name: "Memo Writer", role: "Writes it up as a clear decision memo.", color: "#F2D3A2", shape: "square" },
  planner: { name: "Planner", role: "Picks who joins the meeting.", color: "#A9B0D0", shape: "pill" },
  verifier: { name: "Verifier", role: "Checks each claim against a source.", color: "#7FDCB8", shape: "shield" },
};

/** The six advisors on the Welcome screen, after the host. */
export const WELCOME_TEAM = ["financial_analyst", "market_scout", "librarian", "people_ops", "devils_advocate", "memo_writer"];

export const memberOf = (type: string): Member =>
  TEAM[type] ?? { name: type.replace(/_/g, " "), role: "", color: "#A9B0D0", shape: "circle" };

function Body({ shape, color }: { shape: Shape; color: string }) {
  const common = { fill: color };
  switch (shape) {
    case "square":
      return <rect x="8" y="10" width="48" height="46" rx="12" {...common} />;
    case "hex":
      return <path d="M32 7 L55 20 L55 45 L32 58 L9 45 L9 20 Z" strokeLinejoin="round" stroke={color} strokeWidth="6" {...common} />;
    case "tall":
      return <rect x="13" y="6" width="38" height="52" rx="19" {...common} />;
    case "squircle":
      return <path d="M32 8 C52 8 56 12 56 32 C56 52 52 56 32 56 C12 56 8 52 8 32 C8 12 12 8 32 8 Z" {...common} />;
    case "pill":
      return <rect x="6" y="14" width="52" height="40" rx="20" {...common} />;
    case "shield":
      return <path d="M32 7 L54 14 C54 38 46 51 32 58 C18 51 10 38 10 14 Z" strokeLinejoin="round" stroke={color} strokeWidth="4" {...common} />;
    case "diamond":
      return <rect x="14" y="14" width="36" height="36" rx="10" transform="rotate(45 32 32)" {...common} />;
    case "drop":
      return <path d="M32 6 C44 20 56 30 56 40 C56 52 45 58 32 58 C19 58 8 52 8 40 C8 30 20 20 32 6 Z" {...common} />;
    default:
      return <circle cx="32" cy="33" r="25" {...common} />;
  }
}

export function Face({
  type,
  size = 56,
  speaking = false,
  dim = false,
  className,
}: {
  type: string;
  size?: number;
  speaking?: boolean;
  dim?: boolean;
  className?: string;
}) {
  const m = memberOf(type);
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full transition-[opacity,box-shadow]",
        speaking && "face-speaking",
        dim && "opacity-55",
        className,
      )}
      style={{ width: size, height: size }}
      data-speaking={speaking ? "true" : undefined}
    >
      <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden="true" focusable="false">
        {m.horns ? (
          <g fill="#C93A2B">
            <path d="M15 16 L11 2 L24 11 Z" />
            <path d="M49 16 L53 2 L40 11 Z" />
          </g>
        ) : null}
        <Body shape={m.shape} color={m.color} />
        <g className="face-eye">
          <ellipse cx="24" cy="30" rx="4.2" ry="5.2" fill="#141414" />
          <ellipse cx="40" cy="30" rx="4.2" ry="5.2" fill="#141414" />
          <circle cx="25.4" cy="28.2" r="1.4" fill="#FFFFFF" />
          <circle cx="41.4" cy="28.2" r="1.4" fill="#FFFFFF" />
        </g>
        {speaking ? (
          <ellipse cx="32" cy="43" rx="5" ry="3.6" fill="#141414" />
        ) : (
          <path d="M26 42 Q32 46.5 38 42" fill="none" stroke="#141414" strokeWidth="2.6" strokeLinecap="round" />
        )}
        {type === "advisor" ? <circle cx="50" cy="15" r="5" fill="#FF5B2E" stroke="#141414" strokeWidth="1.5" /> : null}
      </svg>
    </span>
  );
}
