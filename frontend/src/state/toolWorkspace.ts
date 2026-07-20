import { type Dispatch, type SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from "react";

const PREFIX = "insta360_hw_tool_workspace:";
const WORKSPACE_VERSION = 2;
const DEFAULT_DEBOUNCE_MS = 500;
const DEFAULT_MAX_BYTES = 2 * 1024 * 1024;

type WorkspaceOptions<T> = {
  heavyKeys?: readonly (keyof T)[];
  debounceMs?: number;
  maxBytes?: number;
};

type WorkspaceEnvelope<T> = {
  __v: 2;
  saved_at: number;
  data: T;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readWorkspace<T extends Record<string, unknown>>(key: string, initial: T): T {
  if (typeof window === "undefined") return initial;
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (!raw) return initial;
    const parsed: unknown = JSON.parse(raw);
    // v1 workspaces intentionally expire once; accepting them would bypass the v2 validation contract.
    if (!isRecord(parsed) || parsed.__v !== WORKSPACE_VERSION || !isRecord(parsed.data)) return initial;
    return { ...initial, ...parsed.data } as T;
  } catch {
    return initial;
  }
}

function withoutHeavyKeys<T extends Record<string, unknown>>(data: T, heavyKeys: readonly string[]): Partial<T> {
  const reduced: Record<string, unknown> = { ...data };
  heavyKeys.forEach((key) => delete reduced[key]);
  return reduced as Partial<T>;
}

function serializeEnvelope<T extends Record<string, unknown>>(data: T | Partial<T>): string {
  const envelope: WorkspaceEnvelope<T | Partial<T>> = {
    __v: WORKSPACE_VERSION,
    saved_at: Date.now(),
    data,
  };
  return JSON.stringify(envelope);
}

function byteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function persistWorkspace<T extends Record<string, unknown>>(
  storageKey: string,
  workspace: T,
  heavyKeys: readonly string[],
  maxBytes: number,
) {
  const inputOnly = withoutHeavyKeys(workspace, heavyKeys);
  let fullPayload = "";
  try {
    fullPayload = serializeEnvelope(workspace);
  } catch (error) {
    console.warn("[Insta360_HW] 工作区完整状态无法序列化，改为保存输入状态。", error);
  }

  const useFallback = !fullPayload || byteLength(fullPayload) > maxBytes;
  if (useFallback) {
    console.warn("[Insta360_HW] 工作区结果过大，已剥离重结果后保存输入状态。", {
      storageKey,
      bytes: fullPayload ? byteLength(fullPayload) : null,
      maxBytes,
    });
  }
  const attempts: Array<T | Partial<T>> = useFallback ? [inputOnly] : [workspace, inputOnly];
  for (let index = 0; index < attempts.length; index += 1) {
    if (index > 0 && !heavyKeys.length) break;
    try {
      window.localStorage.setItem(storageKey, serializeEnvelope(attempts[index]));
      if (index > 0) console.warn("[Insta360_HW] 工作区存储空间不足，已降级为仅保存输入状态。", { storageKey });
      return;
    } catch (error) {
      console.warn("[Insta360_HW] 工作区写入失败。", error);
    }
  }
}

export function useToolWorkspace<T extends Record<string, unknown>>(
  key: string,
  initial: T,
  options: WorkspaceOptions<T> = {},
): [T, Dispatch<SetStateAction<T>>, () => void] {
  const stableInitial = useMemo(() => initial, []);
  const [workspace, setWorkspace] = useState<T>(() => readWorkspace(key, stableInitial));
  const timerRef = useRef<number | null>(null);
  const suppressNextWriteRef = useRef(false);
  const heavyKeySignature = (options.heavyKeys || []).map(String).join("\u0000");
  const heavyKeys = useMemo(() => heavyKeySignature ? heavyKeySignature.split("\u0000") : [], [heavyKeySignature]);
  const debounceMs = options.debounceMs ?? DEFAULT_DEBOUNCE_MS;
  const maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (suppressNextWriteRef.current) {
      suppressNextWriteRef.current = false;
      return;
    }
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      persistWorkspace(PREFIX + key, workspace, heavyKeys, maxBytes);
    }, debounceMs);
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [key, workspace, heavyKeys, debounceMs, maxBytes]);

  const reset = useCallback(() => {
    if (typeof window !== "undefined") {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      window.localStorage.removeItem(PREFIX + key);
      suppressNextWriteRef.current = true;
    }
    setWorkspace({ ...stableInitial });
  }, [key, stableInitial]);

  return [workspace, setWorkspace, reset];
}
