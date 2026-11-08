// Typed client for the FounderOS backend. All calls go through the Vite proxy (/api -> :8000).

export type DependencyState = "ok" | "degraded" | "unavailable" | "not_configured";

export interface DependencyStatus {
  name: string;
  state: DependencyState;
  detail: string;
  required: boolean;
  info: Record<string, unknown>;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  workspace_id: string;
  currency: string;
  checked_at: string;
  dependencies: DependencyStatus[];
}

export interface SourceRef {
  table: string;
  file: string;
  sheet: string | null;
  rows: string;
  row_count: number;
}

export interface Lineage {
  metric: string;
  sql: string[];
  source_files: string[];
  source_rows: SourceRef[];
  formula: string;
  inputs: Record<string, number | null>;
  period: string | null;
  computed_at: string;
}

export interface MetricResult {
  metric: string;
  label: string;
  value: number | null;
  unit: string;
  as_of: string;
  note: string | null;
  detail: Record<string, unknown> | null;
  lineage: Lineage;
}

export interface Citation {
  path: string;
  heading: string;
  chunk_id: string;
}

export interface AgentInstance {
  id: string;
  type: string;
  name: string;
  brief: string;
  provider: string;
  model: string;
  is_cloud: boolean;
}

export interface Artifact {
  id: string;
  kind: string;
  title: string;
  agent_id: string;
  data: Record<string, unknown>;
  lineage: Lineage[];
  citations: Citation[];
}

export interface CostItem {
  key: string;
  name: string;
  cadence: "one_off" | "monthly" | "count";
  low: number;
  base: number;
  high: number;
  basis: "assumption" | "founder" | "data";
}

export interface CostCase {
  name: "low" | "base" | "high";
  one_off: number;
  monthly: number;
  base_runway_months: number | null;
  scenario_runway_months: number | null;
  runway_change_months: number | null;
}

export interface CostModel {
  subject: string;
  items: CostItem[];
  cases: CostCase[];
  cost_per_person_monthly: number | null;
  currency: string;
  as_of: string;
  formula: string;
  sources: string[];
  scope_note: string;
}

export interface OptionCost {
  name: string;
  note: string;
  one_off: number;
  monthly: number;
  runway_change_months: number | null;
  modelled: boolean;
  is_full: boolean;
  trade_off: string;
  basis: string;
}

export interface GoalCheck {
  goal: string;
  status: string;
  sentence: string;
}

export interface DecisionFrame {
  type: string;
  subject: string;
  message: string;
  cost_model: CostModel | null;
  options: OptionCost[];
  default_option: string;
  goals: GoalCheck[];
  questions: string[];
  currency: string;
  as_of: string;
}

export interface VerificationView {
  state: "verified" | "assumptions" | "not_verified";
  reasons: string[];
  assumptions: string[];
  removed_claims: number;
  sources: string[];
}

export interface MemoRef {
  path: string;
  title: string;
  status: string;
  review_date: string;
  chosen: string;
  decision_type: string;
  predictions: string[];
  kill_criteria: string[];
  open_numbers: string[];
  assumptions_to_confirm: number;
  verified: boolean;
}

export interface AgentResult {
  agent_id: string;
  type: string;
  name: string;
  brief: string;
  text: string;
  status: "done" | "failed" | "cancelled";
  error: string | null;
  verified: boolean | null;
  removed: string[];
  citations: Citation[];
  artifacts: Artifact[];
  provider: string;
  model: string;
  elapsed_ms: number;
  est_cost_usd: number | null;
}

export interface MetricOut {
  metric: string;
  label: string;
  value: number | null;
  unit: string;
  as_of: string;
  agent_id: string;
  lineage: Lineage;
}

export interface ChatResult {
  run_id: string;
  message: string;
  answer: string;
  intent: string;
  decision_type: string | null;
  reversibility: "one_way" | "two_way" | null;
  planner: string;
  team: AgentInstance[];
  approved: boolean;
  agents: AgentResult[];
  metrics: MetricOut[];
  artifacts: Artifact[];
  citations: Citation[];
  decision_frame: DecisionFrame | null;
  assumptions_to_confirm: number;
  memo: MemoRef | null;
  est_cost_usd: number | null;
  verified: boolean;
  /** The badge's state, with reasons that never name a removed figure. Absent from older runs. */
  verification?: VerificationView;
  /** Audit trail only: may name a removed figure, so the UI shows how many, never the text. */
  issues: string[];
  advisor_provider: string;
  advisor_model: string;
  timings_ms: Record<string, number>;
  elapsed_ms: number;
  status: string;
}

export interface AgentEvent {
  seq: number;
  type: string;
  run_id: string;
  agent_id: string | null;
  at: string;
  data: Record<string, unknown>;
}

export interface TurnOutcome {
  session_id: string;
  kind: string | null;
  classified_by: string | null;
  reply: string;
  run_id: string | null;
  amendment_id: string | null;
  queue_id: string | null;
}

export interface TeamEdit {
  briefs?: Record<string, string>;
  remove?: string[];
  add?: { type: string; brief: string }[];
  local_only?: boolean;
}

export interface ScenarioAdjustments {
  price_change_pct: number;
  churn_change_pts: number;
  cac_change_pct: number;
  new_hires: number;
  spend_change_monthly: number;
  one_off_cost: number;
}

export interface Assumption {
  name: string;
  value: number;
  unit: string;
  basis?: string;
  label?: string;
}

export interface ScenarioResult {
  as_of: string;
  currency: string;
  points: { month: string; base_cash: number; scenario_cash: number }[];
  growth_assumption: string;
  base_zero_cash_month: string | null;
  scenario_zero_cash_month: string | null;
  base_runway_months: number | null;
  scenario_runway_months: number | null;
  labels: Record<string, string>;
  drivers: Record<string, number>;
  elapsed_ms: number;
  lineage: Lineage;
}

export interface MonteCarloResult {
  runs: number;
  points: { month: string; p10: number; p50: number; p90: number }[];
  runway_label: string;
  runway_p10: number | null;
  runway_p50: number | null;
  runway_p90: number | null;
  probability_cash_out_within_12_months: number;
  growth_assumption: string;
  elapsed_ms: number;
  lineage: Lineage;
}

export interface VaultNoteInfo {
  path: string;
  title: string;
  folder: string;
  kind: string;
  tags: string[];
  size: number;
  modified: string;
  backlinks: number;
}

export interface VaultNote {
  path: string;
  kind: string;
  title?: string;
  content?: string;
  body?: string;
  frontmatter?: Record<string, unknown>;
  backlinks: string[];
  links?: unknown[];
}

export interface SearchHit {
  citation?: Citation;
  path?: string;
  heading?: string;
  text?: string;
  snippet?: string;
  score?: number;
}

export interface LoadedTable {
  table: string;
  source_file: string;
  sheet: string | null;
  rows: number;
  columns: Record<string, string>;
  ingested_at: string;
}

export interface SettingsView {
  cloud_allowed: boolean;
  deep_provider: string;
  agent_models: Record<string, string>;
  cloud_monthly_cap_usd: number;
  team_approval: "always" | "cloud_only" | "never";
  max_local_agents: number;
  max_cloud_agents: number;
  providers: { name: string; configured: boolean }[];
  agents: { type: string; title: string; privacy: "local" | "cloud_allowed" | "cloud"; job: string }[];
  spend: { month?: string; spent_usd?: number; cap_usd?: number; remaining_usd?: number; over_cap?: boolean };
  privacy_note: string;
}

export interface Criterion {
  name: string;
  weight: number;
  direction: "benefit" | "cost";
  axis: "value" | "feasibility" | null;
}

export interface ScoredOption {
  name: string;
  scores: Record<string, number>;
  cost: number | null;
}

export interface OptionScore {
  name: string;
  total: number;
  rank: number;
  value: number | null;
  feasibility: number | null;
  quadrant: string | null;
  cost: number | null;
}

export interface PrioritiesView {
  criteria: Criterion[];
  options: ScoredOption[];
  scoring: { weights: Record<string, number>; options: OptionScore[]; formula: string } | null;
  path: string;
  warning?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers: { Accept: "application/json", ...init?.headers } });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Backend not reachable");
  }
  if (!response.ok) {
    let detail = `Backend answered ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the status line
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const fetchHealth = (signal?: AbortSignal) => request<HealthResponse>("/api/health", { signal });

export const fetchSummary = (signal?: AbortSignal) =>
  request<{ metrics: MetricResult[]; unavailable: Record<string, string> }>("/api/metrics/summary", { signal });
export const fetchMetric = (name: string, signal?: AbortSignal) =>
  request<MetricResult>(`/api/metrics/${name}`, { signal });

export const postTurn = (text: string, sessionId: string | null) =>
  send<TurnOutcome>("/api/conversation/turn", "POST", { text, session_id: sessionId });
export const setQuiet = (sessionId: string, quiet: boolean) =>
  send<{ quiet: boolean }>(`/api/conversation/${sessionId}/quiet`, "POST", { quiet });
export const answerAmendment = (sessionId: string, id: string, accept: boolean) =>
  send<{ accepted: boolean; run_id: string | null; replaces?: string }>(`/api/conversation/${sessionId}/amendments/${id}`, "POST", {
    accept,
  });
export const answerQueue = (sessionId: string, id: string, accept: boolean) =>
  send<{ accepted: boolean; run_id: string | null }>(`/api/conversation/${sessionId}/queue/${id}`, "POST", { accept });

export const fetchRun = (runId: string) =>
  request<{ run_id: string; status: string; result: ChatResult | null; message: string }>(`/api/runs/${runId}`);
export const approveRun = (runId: string, approved: boolean, edit?: TeamEdit) =>
  send<unknown>(`/api/runs/${runId}/approve`, "POST", { approved, edit: edit ?? null });
export const cancelRun = (runId: string) => send<unknown>(`/api/runs/${runId}/cancel`, "POST");
export const cancelAgent = (runId: string, agentId: string) =>
  send<unknown>(`/api/runs/${runId}/agents/${agentId}/cancel`, "POST");
export const rerunAgent = (runId: string, agentId: string, brief?: string) =>
  send<{ restarted: boolean; run_id: string }>(`/api/runs/${runId}/agents/${agentId}/rerun`, "POST", {
    brief: brief ?? null,
  });

export const postScenario = (adjustments: Partial<ScenarioAdjustments>, signal?: AbortSignal) =>
  request<ScenarioResult>("/api/scenario", {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(adjustments),
  });
export const postMonteCarlo = (adjustments: Partial<ScenarioAdjustments>, signal?: AbortSignal) =>
  request<MonteCarloResult>("/api/scenario/montecarlo", {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ adjustments, runs: 1000 }),
  });

export const fetchNotes = (folder?: string) =>
  request<{ notes: VaultNoteInfo[]; count: number }>(
    `/api/vault/notes${folder ? `?folder=${encodeURIComponent(folder)}` : ""}`,
  );
const notePath = (path: string) => path.split("/").map(encodeURIComponent).join("/");
export const fetchNote = (path: string) => request<VaultNote>(`/api/vault/notes/${notePath(path)}`);
export const saveNote = (path: string, content: string) =>
  send<VaultNote>(`/api/vault/notes/${notePath(path)}`, "PUT", { content });
export const searchVault = (q: string) =>
  request<{ results?: SearchHit[]; note?: string }>(`/api/search?q=${encodeURIComponent(q)}&k=8`);
export const fetchVaultStatus = () => request<Record<string, unknown>>("/api/vault/status");

async function upload<T>(path: string, file: File, extra?: Record<string, string>): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  Object.entries(extra ?? {}).forEach(([k, v]) => form.append(k, v));
  return request<T>(path, { method: "POST", body: form });
}
export const uploadVaultFile = (file: File) => upload<{ path: string; error?: string | null }>("/api/vault/upload", file);
export interface UploadConflict {
  table: string;
  existing_rows: number;
  existing_source: string | null;
  incoming_rows: number;
  incoming_source: string;
}
export interface BackupInfo {
  id: string;
  table: string;
  rows: number;
  source_file: string | null;
  saved_at: string;
  made_by: "upload" | "append" | "mapping" | "sample" | "restore";
  /** What replaced this version, e.g. "before uploading one_row.csv". */
  label: string;
  clean_sample: boolean;
}
export type UploadMode = "check" | "replace" | "append";
export interface UploadOutcome {
  tables: { table: string; rows: number; source_file: string }[];
  conflicts: UploadConflict[];
  backups: BackupInfo[];
}
/** "check" writes nothing when a table already holds rows: it returns the conflicts for the founder to choose. */
export const uploadDataFile = (file: File, table?: string, mode: UploadMode = "check", via: "upload" | "mapping" = "upload") =>
  upload<UploadOutcome>("/api/data/upload", file, { ...(table ? { table } : {}), mode, via });
export const fetchBackups = () => request<BackupInfo[]>("/api/data/backups");
export const undoUpload = (table: string, versionId?: string) =>
  send<{ restored: BackupInfo }>("/api/data/undo", "POST", { table, ...(versionId ? { version_id: versionId } : {}) });

export interface CanonicalTable {
  table: string;
  description: string;
  columns: { name: string; type: string; required: boolean }[];
}
export interface SheetMapping {
  table: string;
  columns: Record<string, string>;
}
export const fetchTables = () => request<{ loaded: LoadedTable[]; canonical: CanonicalTable[] }>("/api/data/tables");
export const fetchMappings = () => request<Record<string, SheetMapping>>("/api/data/mappings");
export const putMapping = (key: string, mapping: SheetMapping) =>
  send<Record<string, SheetMapping>>("/api/data/mappings", "PUT", { key, ...mapping });
export const loadSample = () => send<{ tables: unknown[] }>("/api/data/load-sample", "POST");

export const fetchSettings = () => request<SettingsView>("/api/settings");
export const putSettings = (update: Partial<SettingsView>) => send<SettingsView>("/api/settings", "PUT", update);

export const fetchPriorities = () => request<PrioritiesView>("/api/priorities");
export const putPriorities = (criteria: Criterion[], options: ScoredOption[]) =>
  send<PrioritiesView>("/api/priorities", "PUT", { criteria, options });

/** Reads a run's Advisor text as it is written. Resolves with the final result (or null if the run ended without one). */
export async function streamRun(
  runId: string,
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<ChatResult | null> {
  const response = await fetch(`/api/runs/${runId}/stream`, { signal, headers: { Accept: "text/event-stream" } });
  if (!response.ok || !response.body) throw new ApiError(`Backend answered ${response.status}`, response.status);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatResult | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let end = buffer.indexOf("\n\n");
    while (end >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const frame = parseFrame(block);
      if (frame?.event === "delta") onDelta((frame.data as { text: string }).text);
      if (frame?.event === "done") result = frame.data as ChatResult;
      end = buffer.indexOf("\n\n");
    }
  }
  return result;
}

export function parseFrame(block: string): { event: string; data: unknown } | null {
  let event = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!event || !data) return null;
  try {
    return { event, data: JSON.parse(data) as unknown };
  } catch {
    return null;
  }
}
