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

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Backend not reachable");
  }
  if (!response.ok) {
    throw new ApiError(`Backend answered ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return getJson<HealthResponse>("/api/health", signal);
}
