// How numbers and agent text are shown. Figures are only ever formatted here, never computed.

const SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", GBP: "£", INR: "₹" };

export function money(value: number, currency = "USD", decimals = 2): string {
  const symbol = SYMBOLS[currency];
  const written = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  const sign = value < 0 ? "-" : "";
  return symbol ? `${sign}${symbol}${written}` : `${sign}${written} ${currency}`;
}

/** $1.84M for chart axes, where the exact value is one click away in the lineage. */
export function moneyShort(value: number, currency = "USD"): string {
  const symbol = SYMBOLS[currency] ?? "";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}${symbol}${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}${symbol}${(abs / 1_000).toFixed(0)}K`;
  return `${sign}${symbol}${abs.toFixed(0)}`;
}

export function metricValue(value: number | null, unit: string, metric = ""): string {
  if (value === null) return "n/a";
  if (unit === "months") return `${value.toFixed(2)} mo`;
  if (unit === "ratio") return metric === "ltv_cac" ? `${value.toFixed(2)}x` : `${(value * 100).toFixed(2)}%`;
  if (unit === "percent") return `${value.toFixed(2)}%`;
  if (unit === "count") return value.toLocaleString("en-US");
  if (/^[A-Z]{3}$/.test(unit)) return money(value, unit);
  return `${value} ${unit}`;
}

export function signedMonths(value: number | null): string {
  if (value === null) return "does not run out in the model";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)} mo`;
}

export function monthLabel(iso: string | null | undefined): string {
  if (!iso) return "";
  const match = /^(\d{4})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(match[2]) - 1] ?? ""} ${(match[1] ?? "").slice(2)}`;
}

export function seconds(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  return ms < 10_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 1000)} s`;
}

const FIGURE =
  /[$€£₹]\s?\d[\d,.]*(?:\s?(?:thousand|million|billion|trillion|crore|lakh|bn|tn|k|m|b)\b)?|\d[\d,.]*\s?(?:%|percent\b|(?:thousand|million|billion|trillion|crore|lakh|bn|tn|k|m|b)\b)/gi;
const PATH = /[\w./-]+\.(?:markdown|md|pdf|csv|xlsx|txt)\b/gi;

/**
 * `agent.step` is the audit trail: it can name a figure or a path the source check removed, and a tool call's
 * arguments are the model's own words. On screen it says what the agent is doing, with neither in it.
 */
export function safeStep(step: string): string {
  const tool = /^running (\w+)\(/.exec(step);
  if (tool) return `running ${tool[1]}()`;
  if (step.startsWith("sent back by the Verifier")) return "sent back by the Verifier";
  return step.replace(FIGURE, "a figure").replace(PATH, "a source");
}

export const STATUS_WORDS: Record<string, string> = {
  queued: "Queued",
  thinking: "Thinking",
  querying_data: "Querying data",
  searching_vault: "Searching vault",
  searching_web: "Searching web",
  waiting_cloud: "Waiting for cloud",
  verifying: "Verifying",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** How far along the steps of an agent's work it is. A position in its steps, not a measure of time left. */
export const STATUS_PROGRESS: Record<string, number> = {
  queued: 5,
  thinking: 35,
  querying_data: 55,
  searching_vault: 55,
  searching_web: 55,
  waiting_cloud: 45,
  verifying: 85,
  done: 100,
  failed: 100,
  cancelled: 0,
};

const CODES: Record<string, string> = {
  financial_analyst: "FA",
  librarian: "LB",
  market_scout: "MS",
  devils_advocate: "DA",
  revenue_customer: "RC",
  people_ops: "PO",
  regulatory_tax: "RT",
  prioritiser: "PR",
  memo_writer: "MW",
  perspective_lens: "PL",
};
export const agentCode = (type: string): string => CODES[type] ?? type.slice(0, 2).toUpperCase();

const CORE = new Set(["financial_analyst", "librarian", "planner", "advisor", "verifier"]);
export const agentKind = (type: string): string =>
  type === "financial_analyst" ? "Core · only agent with math" : CORE.has(type) ? "Core" : "Specialist";

export const stripFrontmatter = (content: string): string =>
  content.replace(/^\s*---\r?\n[\s\S]*?\r?\n---\r?\n?/, "");

/** `[[Note|alias]]` as plain words for the memo sheet. */
export const withoutWikilinks = (text: string): string =>
  text.replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2").replace(/\[\[([^\]]+)\]\]/g, "$1");
