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
  __truncated?: true;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function pickLightFields<T extends Record<string, unknown>>(
  candidate: Record<string, unknown>,
  initial: T,
  heavyKeys: readonly string[],
): Partial<T> {
  const heavy = new Set(heavyKeys);
  const safe: Record<string, unknown> = {};
  Object.keys(initial).forEach((field) => {
    if (!heavy.has(field) && Object.prototype.hasOwnProperty.call(candidate, field)) {
      safe[field] = candidate[field];
    }
  });
  return safe as Partial<T>;
}

function readWorkspace<T extends Record<string, unknown>>(
  key: string,
  initial: T,
  heavyKeys: readonly string[],
): T {
  if (typeof window === "undefined") return initial;
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (!raw) return initial;
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) return initial;
    if (parsed.__v === WORKSPACE_VERSION && isRecord(parsed.data)) {
      return { ...initial, ...parsed.data } as T;
    }
    if (parsed.__v === undefined || parsed.__v === 1) {
      const legacy = parsed.__v === 1 && isRecord(parsed.data) ? parsed.data : parsed;
      const migrated = pickLightFields(legacy, initial, heavyKeys);
      window.localStorage.setItem(PREFIX + key, serializeEnvelope(migrated));
      return { ...initial, ...migrated } as T;
    }
    return initial;
  } catch {
    return initial;
  }
}

function withoutHeavyKeys<T extends Record<string, unknown>>(data: T, heavyKeys: readonly string[]): Partial<T> {
  const reduced: Record<string, unknown> = { ...data };
  heavyKeys.forEach((key) => delete reduced[key]);
  return reduced as Partial<T>;
}

function serializeEnvelope<T extends Record<string, unknown>>(
  data: T | Partial<T>,
  truncated = false,
): string {
  const envelope: WorkspaceEnvelope<T | Partial<T>> = {
    __v: WORKSPACE_VERSION,
    saved_at: Date.now(),
    data,
  };
  if (truncated) envelope.__truncated = true;
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
  const attempts: Array<{ data: T | Partial<T>; truncated: boolean }> = useFallback
    ? [{ data: inputOnly, truncated: true }]
    : [
        { data: workspace, truncated: false },
        { data: inputOnly, truncated: true },
      ];
  for (let index = 0; index < attempts.length; index += 1) {
    if (index > 0 && !heavyKeys.length) break;
    try {
      const attempt = attempts[index];
      window.localStorage.setItem(storageKey, serializeEnvelope(attempt.data, attempt.truncated));
      if (index > 0) console.warn("[Insta360_HW] 工作区存储空间不足，已降级为仅保存输入状态。", { storageKey });
      if (attempt.truncated) {
        const key = storageKey.startsWith(PREFIX) ? storageKey.slice(PREFIX.length) : storageKey;
        window.dispatchEvent(new CustomEvent("insta360_hw:workspace-truncated", { detail: { key } }));
      }
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
  const heavyKeySignature = (options.heavyKeys || []).map(String).join("\u0000");
  const heavyKeys = useMemo(() => heavyKeySignature ? heavyKeySignature.split("\u0000") : [], [heavyKeySignature]);
  const [workspace, setWorkspace] = useState<T>(() => readWorkspace(key, stableInitial, heavyKeys));
  const timerRef = useRef<number | null>(null);
  const suppressNextWriteRef = useRef(false);
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
