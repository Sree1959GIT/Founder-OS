/* eslint-disable react-refresh/only-export-components -- the hook and its provider belong together */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type Dispatch,
  type ReactNode,
} from "react";

import {
  answerAmendment,
  answerQueue,
  fetchRun,
  postTurn,
  setQuiet,
  streamRun,
  type AgentEvent,
  type AgentInstance,
  type Artifact,
  type ChatResult,
  type DecisionFrame,
  type TurnOutcome,
} from "@/lib/api";
import { load, save, unfinished } from "@/lib/persist";
import { runTitle } from "@/lib/format";

export interface AgentView extends AgentInstance {
  status: string;
  step: string;
  startedAt: string | null;
  endedAt: string | null;
  elapsedMs: number | null;
  verified: boolean | null;
  tokens: number | null;
  costUsd: number | null;
  provided: string;
  artifactIds: string[];
  checks: number;
}

export interface RunView {
  id: string;
  message: string;
  startedAt: string;
  status: "running" | "done" | "rejected" | "failed" | "cancelled";
  intent: string | null;
  decisionType: string | null;
  reversibility: string | null;
  needsApproval: boolean;
  awaitingApproval: boolean;
  proposedTeam: AgentInstance[];
  questions: string[];
  frame: DecisionFrame | null;
  agents: Record<string, AgentView>;
  order: string[];
  artifacts: Artifact[];
  answer: string;
  result: ChatResult | null;
  verified: boolean | null;
  lastSeq: number;
}

export type Turn =
  | { id: string; role: "you"; text: string }
  | { id: string; role: "advisor"; runId: string }
  | { id: string; role: "lane"; text: string; kind: "narration" | "recap" | "reply" }
  | { id: string; role: "amendment"; amendmentId: string; text: string; status: "offered" | "accepted" | "declined" }
  | { id: string; role: "queued"; queueId: string; text: string; status: "queued" | "offered" | "accepted" | "declined" };

/** The agents of a run, in the order they were spawned. */
export const teamOf = (run: RunView | null): AgentView[] =>
  run ? run.order.flatMap((id) => run.agents[id] ?? []) : [];

export interface WorkspaceState {
  sessionId: string | null;
  quiet: boolean;
  turns: Turn[];
  runs: Record<string, RunView>;
  currentRunId: string | null;
  sending: boolean;
  error: string | null;
  /** Events that arrived before this window knew their run or session: the POST returns after the run has started. */
  held: AgentEvent[];
}

type Action =
  | { type: "session"; id: string }
  | { type: "quiet"; quiet: boolean }
  | { type: "sending"; sending: boolean }
  | { type: "error"; error: string | null }
  | { type: "turn"; turn: Turn }
  | { type: "run"; runId: string; message: string }
  | { type: "event"; event: AgentEvent }
  | { type: "delta"; runId: string; text: string }
  | { type: "result"; runId: string; result: ChatResult }
  | { type: "run-ended"; runId: string; status: RunView["status"] }
  | { type: "amendment"; id: string; status: "accepted" | "declined" }
  | { type: "queue"; id: string; status: "accepted" | "declined" };

export const initialState: WorkspaceState = {
  sessionId: null,
  quiet: false,
  turns: [],
  runs: {},
  currentRunId: null,
  sending: false,
  error: null,
  held: [],
};

const MAX_HELD = 2000;
const RECOVER_WAIT_MS = 3000;
const RECOVER_ATTEMPTS = 400; // 20 minutes: longer than any run

const LANE_EVENTS = new Set(["narration", "recap", "amendment.offered", "queue.added", "queue.offered"]);

function emptyRun(id: string, message: string, at: string): RunView {
  return {
    id,
    message,
    startedAt: at,
    status: "running",
    intent: null,
    decisionType: null,
    reversibility: null,
    needsApproval: false,
    awaitingApproval: false,
    proposedTeam: [],
    questions: [],
    frame: null,
    agents: {},
    order: [],
    artifacts: [],
    answer: "",
    result: null,
    verified: null,
    lastSeq: 0,
  };
}

function agentFrom(instance: AgentInstance, at: string): AgentView {
  return {
    ...instance,
    status: "queued",
    step: "",
    startedAt: at,
    endedAt: null,
    elapsedMs: null,
    verified: null,
    tokens: null,
    costUsd: null,
    provided: instance.provider,
    artifactIds: [],
    checks: 0,
  };
}

function withRunEvent(run: RunView, event: AgentEvent): RunView {
  if (event.seq && event.seq <= run.lastSeq) return run;
  const next: RunView = { ...run, lastSeq: event.seq || run.lastSeq };
  const data = event.data;
  const agentId = event.agent_id ?? "";
  const agent = next.agents[agentId];
  switch (event.type) {
    case "run.started":
      next.message = (data.message as string) || next.message;
      next.startedAt = event.at;
      break;
    case "team.proposed":
      next.intent = (data.intent as string) ?? null;
      next.decisionType = (data.decision_type as string) ?? null;
      next.reversibility = (data.reversibility as string) ?? null;
      next.proposedTeam = (data.team as AgentInstance[]) ?? [];
      next.needsApproval = Boolean(data.needs_approval);
      next.awaitingApproval = Boolean(data.needs_approval);
      next.questions = (data.questions as string[]) ?? [];
      next.frame = (data.decision_frame as DecisionFrame | null) ?? null;
      break;
    case "team.approved":
    case "team.rejected":
      next.awaitingApproval = false;
      break;
    case "agent.spawned": {
      const instance = data as unknown as AgentInstance;
      next.agents = { ...next.agents, [instance.id]: agentFrom(instance, event.at) };
      next.order = next.order.includes(instance.id) ? next.order : [...next.order, instance.id];
      break;
    }
    case "agent.status":
      if (agent) {
        const status = data.status as string;
        const ended = status === "cancelled" || status === "failed";
        next.agents = {
          ...next.agents,
          [agentId]: {
            ...agent,
            status,
            startedAt: status === "queued" ? agent.startedAt : (agent.startedAt ?? event.at),
            endedAt: ended ? event.at : agent.endedAt,
          },
        };
      }
      break;
    case "agent.step":
      if (agent) next.agents = { ...next.agents, [agentId]: { ...agent, step: data.step as string } };
      break;
    case "agent.rerun":
      if (agent) {
        next.agents = {
          ...next.agents,
          [agentId]: { ...agent, brief: data.brief as string, status: "queued", endedAt: null, elapsedMs: null },
        };
      }
      break;
    case "agent.artifact": {
      const artifact = data.artifact as Artifact;
      next.artifacts = [...next.artifacts.filter((a) => a.id !== artifact.id), artifact];
      if (agent) {
        next.agents = { ...next.agents, [agentId]: { ...agent, artifactIds: [...agent.artifactIds, artifact.id] } };
      }
      break;
    }
    case "agent.done":
      if (agent) {
        const tokens = data.tokens as { input_tokens?: number; output_tokens?: number } | undefined;
        next.agents = {
          ...next.agents,
          [agentId]: {
            ...agent,
            status: (data.status as string) ?? "done",
            endedAt: event.at,
            elapsedMs: (data.elapsed_ms as number) ?? null,
            verified: (data.verified as boolean | null) ?? null,
            provided: (data.provider as string) || agent.provider,
            tokens: tokens ? (tokens.input_tokens ?? 0) + (tokens.output_tokens ?? 0) : null,
            costUsd: (data.est_cost_usd as number | null) ?? null,
            checks: ((data.issues as unknown[]) ?? []).length,
          },
        };
      }
      break;
    case "run.finished": {
      const status = data.status as RunView["status"];
      next.status = status === "done" || status === "rejected" || status === "cancelled" ? status : "failed";
      next.verified = (data.verified as boolean | undefined) ?? next.verified;
      next.awaitingApproval = false;
      break;
    }
    default:
      break;
  }
  return next;
}

function laneTurn(state: WorkspaceState, event: AgentEvent): WorkspaceState {
  const data = event.data;
  const id = `lane-${event.seq}`;
  if (state.turns.some((t) => t.id === id)) return state;
  const sessionId = data.session_id as string | undefined;
  if (state.sessionId && sessionId && sessionId !== state.sessionId) return state;
  if (!state.sessionId) return state; // another window's conversation
  if (event.type === "narration" || event.type === "recap") {
    const turn: Turn = { id, role: "lane", text: data.text as string, kind: event.type };
    return { ...state, turns: [...state.turns, turn] };
  }
  if (event.type === "amendment.offered") {
    const turn: Turn = {
      id,
      role: "amendment",
      amendmentId: data.amendment_id as string,
      text: data.text as string,
      status: "offered",
    };
    return { ...state, turns: [...state.turns, turn] };
  }
  const queueId = data.queue_id as string;
  if (event.type === "queue.added") {
    const turn: Turn = { id, role: "queued", queueId, text: data.text as string, status: "queued" };
    return { ...state, turns: [...state.turns, turn] };
  }
  if (event.type === "queue.offered") {
    const known = state.turns.some((t) => t.role === "queued" && t.queueId === queueId);
    if (!known) {
      const turn: Turn = { id, role: "queued", queueId, text: data.text as string, status: "offered" };
      return { ...state, turns: [...state.turns, turn] };
    }
    // The offer comes after the answer, so it moves below it: an offer scrolled out of sight is one never seen.
    const offered: Turn[] = state.turns.flatMap((t) =>
      t.role === "queued" && t.queueId === queueId ? [{ ...t, status: "offered" as const }] : [],
    );
    return {
      ...state,
      turns: [...state.turns.filter((t) => !(t.role === "queued" && t.queueId === queueId)), ...offered],
    };
  }
  return state;
}

/** The answer reads after the team's narration, so its card moves down when its first words arrive. */
function advisorLast(turns: Turn[], runId: string): Turn[] {
  const id = `advisor-${runId}`;
  const card = turns.find((t) => t.id === id);
  return card ? [...turns.filter((t) => t.id !== id), card] : turns;
}

export function reducer(state: WorkspaceState, action: Action): WorkspaceState {
  switch (action.type) {
    case "session": {
      let next: WorkspaceState = { ...state, sessionId: action.id };
      for (const event of state.held) {
        if (LANE_EVENTS.has(event.type)) next = laneTurn(next, event);
      }
      return next;
    }
    case "quiet":
      return { ...state, quiet: action.quiet };
    case "sending":
      return { ...state, sending: action.sending };
    case "error":
      return { ...state, error: action.error };
    case "turn":
      return { ...state, turns: [...state.turns, action.turn] };
    case "run": {
      const existing = state.runs[action.runId];
      let run = existing ?? emptyRun(action.runId, action.message, new Date().toISOString());
      for (const event of state.held) {
        if (event.run_id === action.runId) run = withRunEvent(run, event);
      }
      return {
        ...state,
        currentRunId: action.runId,
        runs: { ...state.runs, [action.runId]: run },
        held: state.held.filter((e) => e.run_id !== action.runId),
      };
    }
    case "event": {
      const { event } = action;
      let next = state;
      if (LANE_EVENTS.has(event.type)) next = laneTurn(next, event);
      const known = next.runs[event.run_id];
      if (!known) {
        // Only this window's runs fill the canvas: replayed history from earlier sessions just ages out of here.
        return { ...next, held: [...next.held, event].slice(-MAX_HELD) };
      }
      return { ...next, runs: { ...next.runs, [event.run_id]: withRunEvent(known, event) } };
    }
    case "delta": {
      const run = state.runs[action.runId];
      if (!run) return state;
      return {
        ...state,
        turns: run.answer ? state.turns : advisorLast(state.turns, action.runId),
        runs: { ...state.runs, [action.runId]: { ...run, answer: run.answer + action.text } },
      };
    }
    case "result": {
      const run = state.runs[action.runId] ?? emptyRun(action.runId, action.result.message, new Date().toISOString());
      const { result } = action;
      const status: RunView["status"] = result.status === "rejected" ? "rejected" : "done";
      const updated: RunView = {
        ...run,
        answer: result.answer,
        result,
        status,
        verified: result.verified,
        frame: result.decision_frame ?? run.frame,
        reversibility: result.reversibility ?? run.reversibility,
        decisionType: result.decision_type ?? run.decisionType,
        intent: result.intent,
        awaitingApproval: false,
        artifacts: result.artifacts.length ? result.artifacts : run.artifacts,
      };
      return {
        ...state,
        turns: run.answer ? state.turns : advisorLast(state.turns, action.runId),
        runs: { ...state.runs, [action.runId]: updated },
      };
    }
    case "run-ended": {
      const run = state.runs[action.runId];
      if (!run || run.status !== "running") return state;
      return { ...state, runs: { ...state.runs, [action.runId]: { ...run, status: action.status } } };
    }
    case "amendment":
      return {
        ...state,
        turns: state.turns.map((t) =>
          t.role === "amendment" && t.amendmentId === action.id ? { ...t, status: action.status } : t,
        ),
      };
    case "queue":
      return {
        ...state,
        turns: state.turns.map((t) =>
          t.role === "queued" && t.queueId === action.id ? { ...t, status: action.status } : t,
        ),
      };
  }
}

interface WorkspaceApi {
  state: WorkspaceState;
  dispatch: Dispatch<Action>;
  send: (text: string) => Promise<void>;
  follow: (runId: string, message: string) => void;
  toggleQuiet: () => Promise<void>;
  amendment: (id: string, accept: boolean) => Promise<void>;
  queued: (id: string, accept: boolean) => Promise<void>;
  /** A turn the founder spoke: the voice socket already sent it to the lane, so only its outcome is shown. */
  spoken: (text: string, outcome: TurnOutcome) => void;
  currentRun: RunView | null;
  /** The latest decision stays open on the canvas when a small question follows it. */
  decisionRun: RunView | null;
}

const Context = createContext<WorkspaceApi | null>(null);

const EVENT_TYPES = [
  "run.started",
  "team.proposed",
  "team.approved",
  "team.rejected",
  "agent.spawned",
  "agent.status",
  "agent.step",
  "agent.tool_call",
  "agent.artifact",
  "agent.done",
  "agent.rerun",
  "run.finished",
  "narration",
  "recap",
  "amendment.offered",
  "queue.added",
  "queue.offered",
  "turn.classified",
];

async function recover(runId: string, send: Dispatch<Action>, giveUpAfterMisses = RECOVER_ATTEMPTS) {
  let misses = 0;
  for (let attempt = 0; attempt < RECOVER_ATTEMPTS; attempt += 1) {
    try {
      const found = await fetchRun(runId);
      if (found.result) {
        send({ type: "result", runId, result: found.result });
        return;
      }
      if (found.status !== "running") break;
    } catch {
      // the backend may be back in a moment; a run it no longer knows (it restarted) is given up on soon
      misses += 1;
      if (misses >= giveUpAfterMisses) break;
    }
    await new Promise((resolve) => setTimeout(resolve, RECOVER_WAIT_MS));
  }
  send({ type: "run-ended", runId, status: "failed" });
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState, load);
  const stateRef = useRef(state);
  stateRef.current = state;
  // Runs this window already follows. A turn sent while the first is still being planned arrives before React has
  // rendered that run, so the state alone cannot say whether it is new (founder re-test RW6).
  const followed = useRef(new Set<string>());

  // A reload keeps the conversation and the open decision (founder review 17). Streaming text saves at most twice a second.
  useEffect(() => {
    const timer = setTimeout(() => save(state), 500);
    return () => clearTimeout(timer);
  }, [state]);

  // Live agent events for the whole window. A reconnect replays history; each run drops what it has already seen.
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/events");
    const onEvent = (raw: Event) => {
      try {
        dispatch({ type: "event", event: JSON.parse((raw as MessageEvent<string>).data) as AgentEvent });
      } catch {
        // a malformed frame must not take the panel down
      }
    };
    EVENT_TYPES.forEach((t) => source.addEventListener(t, onEvent));
    return () => source.close();
  }, []);

  const follow = useCallback((runId: string, message: string) => {
    followed.current.add(runId);
    dispatch({ type: "run", runId, message });
    dispatch({ type: "turn", turn: { id: `advisor-${runId}`, role: "advisor", runId } });
    void (async () => {
      try {
        const result = await streamRun(runId, (text) => dispatch({ type: "delta", runId, text }));
        if (result) {
          dispatch({ type: "result", runId, result });
          return;
        }
        dispatch({ type: "run-ended", runId, status: "cancelled" });
      } catch {
        // The stream broke (a dropped connection, a sleeping PC): the run goes on, and its result stays on the backend.
        await recover(runId, dispatch);
      }
    })();
  }, []);

  // After a reload, a run that was still working is followed through the backend until it has a result.
  useEffect(() => {
    unfinished(stateRef.current).forEach((runId) => void recover(runId, dispatch, 3));
  }, []);

  // Turns are accepted at once, even while the first is still being planned, and sent in order: the second turn of a
  // new conversation must reach the session the first one opened.
  const chain = useRef<Promise<void>>(Promise.resolve());
  // What the lane decided about a turn, typed or spoken (M5: the voice socket sends the same outcome).
  const adopt = useCallback(
    async (clean: string, outcome: TurnOutcome) => {
        const isNewSession = stateRef.current.sessionId === null;
        // Set at once, not on the next render: a turn chained right behind this one must join the same session,
        // not open a second one (and a second run) of its own.
        stateRef.current = { ...stateRef.current, sessionId: outcome.session_id };
        dispatch({ type: "session", id: outcome.session_id });
        if (isNewSession && stateRef.current.quiet) {
          await setQuiet(outcome.session_id, true).catch(() => dispatch({ type: "quiet", quiet: false }));
        }
        const startedRun =
          outcome.run_id !== null &&
          outcome.run_id !== stateRef.current.currentRunId &&
          !stateRef.current.runs[outcome.run_id] &&
          !followed.current.has(outcome.run_id);
        // An amendment or a queued question shows its own card, with the same words.
        // A question already queued gets no second card, so its reply ("already queued") is shown instead.
        const queuedBefore =
          outcome.queue_id !== null &&
          stateRef.current.turns.some((t) => t.role === "queued" && t.queueId === outcome.queue_id);
        if (outcome.reply && !outcome.amendment_id && (!outcome.queue_id || queuedBefore)) {
          dispatch({
            type: "turn",
            turn: { id: `reply-${Date.now()}`, role: "lane", text: outcome.reply, kind: "reply" },
          });
        }
        // An offer answered in words, typed or spoken (M5 re-test R8): its card shows the answer, and a restarted
        // run is followed under the title its button would have given it, so the canvas shows the new figures.
        const answered = outcome.answered ?? null;
        let title = clean;
        if (answered) {
          const status = answered.accept ? "accepted" : "declined";
          const turns = stateRef.current.turns;
          if (answered.what === "amendment") {
            dispatch({ type: "amendment", id: answered.id, status });
            const offered = turns.find((t) => t.role === "amendment" && t.amendmentId === answered.id);
            const change = offered && offered.role === "amendment" ? offered.text : "";
            const before = stateRef.current.currentRunId
              ? stateRef.current.runs[stateRef.current.currentRunId]?.message
              : undefined;
            const root = before ? runTitle(before).split(" · changed: ")[0] : "";
            title = root && change ? `${root} · changed: ${change}` : change || clean;
          } else {
            dispatch({ type: "queue", id: answered.id, status });
            const offered = turns.find((t) => t.role === "queued" && t.queueId === answered.id);
            title = offered && offered.role === "queued" ? offered.text : clean;
          }
        }
        if (startedRun && outcome.run_id) follow(outcome.run_id, title);
    },
    [follow],
  );

  const post = useCallback(
    async (clean: string) => {
      dispatch({ type: "sending", sending: true });
      dispatch({ type: "error", error: null });
      try {
        await adopt(clean, await postTurn(clean, stateRef.current.sessionId));
      } catch (err) {
        dispatch({ type: "error", error: err instanceof Error ? err.message : "Backend not reachable" });
      } finally {
        dispatch({ type: "sending", sending: false });
      }
    },
    [adopt],
  );

  const spoken = useCallback(
    (text: string, outcome: TurnOutcome) => {
      dispatch({ type: "turn", turn: { id: `you-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, role: "you", text } });
      void adopt(text, outcome);
    },
    [adopt],
  );

  const send = useCallback(
    (text: string) => {
      const clean = text.trim();
      if (!clean) return Promise.resolve();
      dispatch({ type: "turn", turn: { id: `you-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, role: "you", text: clean } });
      const next = chain.current.then(() => post(clean));
      chain.current = next.catch(() => undefined);
      return next;
    },
    [post],
  );

  const toggleQuiet = useCallback(async () => {
    const { sessionId, quiet } = stateRef.current;
    dispatch({ type: "quiet", quiet: !quiet });
    if (sessionId) await setQuiet(sessionId, !quiet).catch(() => dispatch({ type: "quiet", quiet }));
  }, []);

  const amendment = useCallback(
    async (id: string, accept: boolean) => {
      const { sessionId, turns } = stateRef.current;
      if (!sessionId) return;
      try {
        const answer = await answerAmendment(sessionId, id, accept);
        dispatch({ type: "amendment", id, status: accept ? "accepted" : "declined" });
        if (accept && answer.run_id) {
          const offered = turns.find((t) => t.role === "amendment" && t.amendmentId === id);
          const change = offered && offered.role === "amendment" ? offered.text : "";
          const before = answer.replaces ? stateRef.current.runs[answer.replaces]?.message : undefined;
          const root = before ? runTitle(before).split(" · changed: ")[0] : "";
          follow(answer.run_id, root ? `${root} · changed: ${change}` : change);
        }
      } catch (err) {
        dispatch({ type: "error", error: err instanceof Error ? err.message : "That offer has closed" });
      }
    },
    [follow],
  );

  const queued = useCallback(
    async (id: string, accept: boolean) => {
      const { sessionId, turns } = stateRef.current;
      if (!sessionId) return;
      try {
        const answer = await answerQueue(sessionId, id, accept);
        dispatch({ type: "queue", id, status: accept ? "accepted" : "declined" });
        if (accept && answer.run_id) {
          const offered = turns.find((t) => t.role === "queued" && t.queueId === id);
          follow(answer.run_id, offered && offered.role === "queued" ? offered.text : "");
        }
      } catch (err) {
        dispatch({ type: "error", error: err instanceof Error ? err.message : "That question is not on offer" });
      }
    },
    [follow],
  );

  const value = useMemo<WorkspaceApi>(
    () => ({
      state,
      dispatch,
      send,
      follow,
      toggleQuiet,
      amendment,
      queued,
      spoken,
      currentRun: state.currentRunId ? (state.runs[state.currentRunId] ?? null) : null,
      decisionRun:
        Object.values(state.runs)
          .filter((run) => run.frame || run.decisionType)
          .sort((a, b) => b.startedAt.localeCompare(a.startedAt))[0] ?? null,
    }),
    [state, send, follow, toggleQuiet, amendment, queued, spoken],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useWorkspace(): WorkspaceApi {
  const value = useContext(Context);
  if (!value) throw new Error("useWorkspace outside WorkspaceProvider");
  return value;
}
