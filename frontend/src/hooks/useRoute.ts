import { useEffect, useRef, useState } from "react";

export type View = "workspace" | "activity" | "memo" | "data" | "vault" | "settings";

export interface Route {
  view: View;
  path?: string;
}

const VIEWS = new Set<View>(["activity", "memo", "data", "vault", "settings"]);

export function parseHash(hash: string): Route {
  const [location, query] = hash.replace(/^#\/?/, "").split("?");
  const view: View = VIEWS.has(location as View) ? (location as View) : "workspace";
  const path = new URLSearchParams(query ?? "").get("path") ?? undefined;
  return { view, path };
}

/**
 * A page with unsaved changes can hold navigation inside the app: it returns false to stay, and navigates itself
 * later (`leaveTo`) once the founder has chosen Save or Discard. Only one page holds it at a time.
 */
type Guard = (targetHash: string) => boolean;
let guard: Guard | null = null;

export function setNavigationGuard(next: Guard | null): void {
  guard = next;
}

export function leaveTo(targetHash: string): void {
  guard = null;
  window.location.hash = targetHash;
}

export function useRoute(): Route {
  const [hash, setHash] = useState(() => window.location.hash);
  const current = useRef(hash);
  useEffect(() => {
    const onChange = () => {
      const next = window.location.hash;
      if (guard && next !== current.current && !guard(next)) {
        // Stay: put the address back without another hashchange.
        window.history.replaceState(null, "", current.current || "#/");
        return;
      }
      current.current = next;
      setHash(next);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return parseHash(hash);
}
