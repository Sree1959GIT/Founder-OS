import { useEffect, useState } from "react";

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

export function useRoute(): Route {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return parseHash(hash);
}
