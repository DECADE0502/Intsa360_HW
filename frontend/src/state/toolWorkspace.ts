import { type Dispatch, type SetStateAction, useCallback, useEffect, useMemo, useState } from "react";

const PREFIX = "insta360_hw_tool_workspace:";

function readWorkspace<T>(key: string, initial: T): T {
  if (typeof window === "undefined") return initial;
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw ? ({ ...initial, ...JSON.parse(raw) } as T) : initial;
  } catch {
    return initial;
  }
}

export function useToolWorkspace<T extends Record<string, unknown>>(
  key: string,
  initial: T,
): [T, Dispatch<SetStateAction<T>>, () => void] {
  const stableInitial = useMemo(() => initial, []);
  const [workspace, setWorkspace] = useState<T>(() => readWorkspace(key, stableInitial));

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(PREFIX + key, JSON.stringify(workspace));
    } catch {
      // localStorage may be blocked or full; the live React state still protects this session.
    }
  }, [key, workspace]);

  const reset = useCallback(() => {
    if (typeof window !== "undefined") window.localStorage.removeItem(PREFIX + key);
    setWorkspace(stableInitial);
  }, [key, stableInitial]);

  return [workspace, setWorkspace, reset];
}
