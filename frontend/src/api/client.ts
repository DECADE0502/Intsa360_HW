import { ApiError } from "./errors";

export type ApiOpts = { signal?: AbortSignal; timeoutMs?: number };
const DEFAULT_TIMEOUT = 60_000;
const HEALTH_PROBE_TIMEOUT_MS = 3_000;
const UPDATE_STATUS_POLL_TIMEOUT_MS = 3_000;
const SESSION_TOKEN_TIMEOUT_MS = 3_000;
const SESSION_HEADER = "X-Insta360-Session";
const MUTATION_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let sessionTokenRequest: Promise<string> | null = null;

function isAbortError(error: unknown): boolean {
  return Boolean(
    error &&
      typeof error === "object" &&
      "name" in error &&
      (error as { name?: unknown }).name === "AbortError",
  );
}

function isMutation(init: RequestInit): boolean {
  return MUTATION_METHODS.has((init.method || "GET").toUpperCase());
}

async function fetchSessionToken(forceRefresh = false): Promise<string> {
  if (forceRefresh) sessionTokenRequest = null;
  if (!sessionTokenRequest) {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, SESSION_TOKEN_TIMEOUT_MS);
    let request: Promise<string>;
    request = fetch("/api/session", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || typeof payload.token !== "string" || !payload.token) {
          throw new Error(payload.error || "无法建立平台安全会话");
        }
        return payload.token as string;
      })
      .catch((error) => {
        if (sessionTokenRequest === request) sessionTokenRequest = null;
        if (timedOut && isAbortError(error)) {
          throw new ApiError(
            "SessionTimeout",
            "平台安全会话建立超时，请确认后端服务可用。",
            408,
            error,
          );
        }
        throw error;
      })
      .finally(() => {
        clearTimeout(timer);
      });
    sessionTokenRequest = request;
  }
  return sessionTokenRequest;
}

async function secureInit(init: RequestInit): Promise<RequestInit> {
  if (!isMutation(init)) return init;
  const headers = new Headers(init.headers || {});
  headers.set(SESSION_HEADER, await fetchSessionToken());
  return { ...init, headers };
}

export async function secureFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  let secured = await secureInit(init);
  let response = await fetch(input, secured);
  if (isMutation(init) && response.status === 403) {
    const payload = await response.clone().json().catch(() => ({}));
    if (payload?.error_kind === "session_required") {
      const headers = new Headers(init.headers || {});
      headers.set(SESSION_HEADER, await fetchSessionToken(true));
      secured = { ...init, headers };
      response = await fetch(input, secured);
    }
  }
  return response;
}

export async function apiCall<T = unknown>(
  path: RequestInfo | URL,
  init: RequestInit = {},
  opts: ApiOpts = {},
): Promise<T> {
  const internalCtrl = new AbortController();
  let timedOut = false;
  const abortOnTimeout = () => {
    timedOut = true;
    internalCtrl.abort();
  };
  const timer =
    opts.timeoutMs !== undefined
      ? setTimeout(abortOnTimeout, opts.timeoutMs)
      : opts.signal
      ? null
      : setTimeout(abortOnTimeout, DEFAULT_TIMEOUT);
  let combined = internalCtrl.signal;
  let releaseSignals = () => {};
  if (opts.signal && timer) {
    const merged = mergeSignals(opts.signal, internalCtrl.signal);
    combined = merged.signal;
    releaseSignals = merged.dispose;
  } else if (opts.signal) {
    combined = opts.signal;
  }
  try {
    const res = await secureFetch(path, { ...init, signal: combined });
    const payload: any = await res.json().catch(() => ({}));
    if (!res.ok || (payload && payload.status === "error")) {
      throw new ApiError(
        payload?.error_kind ?? "HttpError",
        payload?.user_message ?? payload?.error ?? res.statusText ?? "Request failed",
        res.status,
        payload,
      );
    }
    return payload as T;
  } catch (error) {
    if (timedOut && isAbortError(error)) {
      throw new ApiError("TimeoutError", "请求超时，请稍后重试。", 408, error);
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
    releaseSignals();
  }
}

function mergeSignals(a: AbortSignal, b: AbortSignal): { signal: AbortSignal; dispose: () => void } {
  if (a.aborted) return { signal: a, dispose: () => {} };
  if (b.aborted) return { signal: b, dispose: () => {} };
  const ctrl = new AbortController();
  const abort = () => ctrl.abort();
  a.addEventListener("abort", abort, { once: true });
  b.addEventListener("abort", abort, { once: true });
  return {
    signal: ctrl.signal,
    dispose: () => {
      a.removeEventListener("abort", abort);
      b.removeEventListener("abort", abort);
    },
  };
}

export type ToolInfo = {
  id: string;
  name: string;
  description: string;
  status: string;
  category: string;
};

export type Capability = ToolInfo & {
  type: "web_tool" | "cadence_tcl" | "system";
  command?: string;
  danger_level?: "low" | "medium" | "high";
  requires_confirmation?: boolean;
  can_enable?: boolean;
  module?: string;
  show_in_platform: boolean;
  show_in_cadence: boolean;
};

export type PluginInfo = {
  id: string;
  name: string;
  description?: string;
  category?: string;
  type: "cadence_tcl" | string;
  command?: string;
  module?: string;
  entry_script?: string;
  implementation_command?: string;
  activate_command?: string;
  deactivate_command?: string;
  activation?: "hot_reload" | "restart";
  compatible_capture_versions?: string[];
  script?: string;
  path?: string;
  source: "system" | "platform" | "user";
  readonly: boolean;
  manageable: boolean;
  menu: string;
  status: string;
  danger_level?: "low" | "medium" | "high";
  requires_confirmation?: boolean;
  can_enable?: boolean;
  show_in_platform: boolean;
  show_in_cadence: boolean;
};

export type PluginsPayload = {
  platform: { name: string; cadence_menu: string };
  plugins: PluginInfo[];
  groups: { system: PluginInfo[]; platform: PluginInfo[]; user: PluginInfo[] };
  summary: { total: number; system: number; platform: number; user: number; enabled: number };
};

export type HistoryRun = {
  id: string;
  time: string;
  tool: string;
  tool_name: string;
  inputs?: string[];
  outputs?: string[];
  summary?: Record<string, unknown> | unknown;
};

export type AssetItem = {
  id: string;
  kind: "processed_bom" | string;
  name: string;
  path: string;
  format?: string;
  run_id?: string;
  source_tool?: string;
  source_tool_name?: string;
  time?: string;
  summary?: Record<string, unknown> | unknown;
};

export type AssetsPayload = {
  status: string;
  error?: string;
  groups: { processed_bom: AssetItem[]; [key: string]: AssetItem[] };
  summary: Record<string, number>;
};

export type LifecycleCheck = {
  id: string;
  name: string;
  status: "ok" | "warn" | "fail";
  message: string;
};

export type LifecyclePayload = {
  status: string;
  error?: string;
  summary: { failed: number; warnings: number; ok: number; total: number };
  manifest: Record<string, unknown>;
  checks: LifecycleCheck[];
};

export const HISTORY_UPDATED_EVENT = "insta360_hw:history-updated";

async function requestJson<T = any>(input: RequestInfo | URL, init: RequestInit = {}, opts: ApiOpts = {}): Promise<T> {
  const { signal: initSignal, ...requestInit } = init;
  const signal = opts.signal ?? initSignal ?? undefined;
  try {
    return await apiCall<T>(
      input,
      requestInit,
      { ...opts, signal, timeoutMs: opts.timeoutMs ?? DEFAULT_TIMEOUT },
    );
  } catch (error) {
    const err = error as Error;
    if (err.name === "AbortError") {
      if (signal?.aborted) throw err;
      throw new Error("请求超时，请检查本地服务后重试。");
    }
    if (err.name === "TypeError" || /fetch/i.test(err.message || "")) {
      throw new Error("后端服务已断开，请重新启动平台或点击重新连接。");
    }
    throw err;
  }
}

export async function fetchTools(): Promise<ToolInfo[]> {
  const payload = await requestJson<{ tools?: ToolInfo[] }>("/api/tools");
  return payload.tools || [];
}

export async function installCadenceIntegration() {
  const payload = await requestJson<any>("/api/cadence/install", { method: "POST" });
  if (payload.status !== "ok") throw new Error(payload.error || "Cadence 集成安装失败");
  return payload as { status: "ok"; redeployed: boolean; message: string; hot_reload_command: string };
}

export async function fetchCapabilities(): Promise<{ platform: { name: string; cadence_menu: string }; capabilities: Capability[] }> {
  return await requestJson("/api/capabilities");
}

export async function fetchPlugins(): Promise<PluginsPayload> {
  const payload = await requestJson<any>("/api/plugins");
  return payload;
}

export async function fetchHistory(): Promise<HistoryRun[]> {
  const payload = await requestJson<{ runs?: HistoryRun[] }>("/api/history");
  return payload.runs || [];
}

export async function fetchAssets(): Promise<AssetsPayload> {
  const payload = await requestJson<AssetsPayload>("/api/assets");
  if (payload.status !== "ok") throw new Error(payload.error || "历史资产加载失败");
  return payload;
}

export async function fetchHistoryRun(id: string): Promise<Record<string, unknown>> {
  const payload = await requestJson<any>(`/api/history/${encodeURIComponent(id)}`);
  return payload;
}

export async function deleteHistoryRun(id: string) {
  const payload = await requestJson<any>(`/api/history/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (payload.status !== "ok") throw new Error(payload.error || "删除记录失败");
  return payload;
}

export async function clearHistory() {
  const payload = await requestJson<any>("/api/history", { method: "DELETE" });
  if (payload.status !== "ok") throw new Error(payload.error || "清空历史失败");
  return payload;
}

export async function fetchPlatformStatus(opts?: ApiOpts) {
  return apiCall<any>(
    "/api/platform/status",
    {},
    { ...opts, timeoutMs: opts?.timeoutMs ?? HEALTH_PROBE_TIMEOUT_MS },
  );
}

export async function fetchLifecycleCheck(): Promise<LifecyclePayload> {
  const payload = await requestJson<LifecyclePayload>("/api/lifecycle/check");
  if (payload.status !== "ok") throw new Error(payload.error || "安装自检加载失败");
  return payload;
}

export async function setCadenceMenuVisibility(id: string, showInCadence: boolean) {
  const payload = await requestJson<any>(`/api/capabilities/${encodeURIComponent(id)}/cadence-menu`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ show_in_cadence: showInCadence, redeploy: true }),
  });
  if (payload.status !== "ok") throw new Error(payload.error || "菜单状态更新失败");
  return payload.capability as Capability;
}

export async function setPluginCadenceMenuVisibility(id: string, showInCadence: boolean) {
  const payload = await requestJson<any>(`/api/plugins/${encodeURIComponent(id)}/cadence-menu`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ show_in_cadence: showInCadence, redeploy: true }),
  });
  if (payload.status !== "ok") throw new Error(payload.error || "插件菜单状态更新失败");
  return payload.plugin as PluginInfo;
}

export async function uploadFiles(files: File[]): Promise<{ files: Array<{ path: string; name: string }> }> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const payload = await requestJson<any>("/api/upload", { method: "POST", body: form }, { timeoutMs: 300_000 });
  if (payload.status !== "ok") throw new Error(payload.error || "上传失败");
  return payload;
}

export async function runTool(tool: string, params: Record<string, unknown>, opts?: ApiOpts) {
  // 5 minutes for long tool runs; caller can override
  const result = await apiCall<any>(
    `/api/tools/${tool}/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    },
    { timeoutMs: 300_000, ...opts },
  );
  if (typeof window !== "undefined") window.dispatchEvent(new Event(HISTORY_UPDATED_EVENT));
  return result;
}

export async function fetchVersion(opts?: ApiOpts): Promise<string> {
  const payload = await apiCall<any>(
    "/api/version",
    {},
    { ...opts, timeoutMs: opts?.timeoutMs ?? HEALTH_PROBE_TIMEOUT_MS },
  );
  if (payload.status !== "ok") throw new Error(payload.error || "版本获取失败");
  return payload.version;
}

export type LifecycleJobPhase =
  | "idle"
  | "checking"
  | "queued"
  | "downloading"
  | "verifying"
  | "staging"
  | "awaiting_elevation"
  | "committing"
  | "switching"
  | "integrating"
  | "verifying_runtime"
  | "completed"
  | "failed"
  | "cancelled";

export type UpdateStartResponse = {
  status: "ok" | "error";
  job_id: string;
  version: string;
  message: string;
  error: string;
};

export type UpdateCancelResponse = {
  status: "ok" | "error";
  job_id: string;
  phase: LifecycleJobPhase;
  cancellable: boolean;
  message: string;
  error: string;
};

export async function startUpdate(): Promise<UpdateStartResponse> {
  const payload = await requestJson<UpdateStartResponse>("/api/update/run", { method: "POST" });
  if (payload.status !== "ok") throw new Error(payload.error || "更新启动失败");
  return payload;
}

export async function cancelUpdate(jobId?: string): Promise<UpdateCancelResponse> {
  const payload = await requestJson<UpdateCancelResponse>("/api/update/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId || "" }),
  });
  if (payload.status !== "ok") throw new Error(payload.error || "取消更新失败");
  return payload;
}

export type UpdateCheck = {
  status: "ok";
  version: string;
  revision: string;
  remote_version: string;
  remote_revision: string;
  update_notice: UpdateNotice;
  notice_status: string;
  display_remote: string;
  has_update: boolean;
  can_update: boolean;
  installed_runtime: boolean;
  minimum_launcher_version: string;
  update_reason: string;
  remote_status: string;
  remote_revision_status: string;
  expected_sha256: string;
  integrity_verified: boolean;
  integrity_status: string;
  download_strategy: "release_runtime_zip" | "none";
  message: string;
  error: string;
};

export type UpdateNotice = {
  version?: string;
  revision?: string;
  target_revision?: string;
  date?: string;
  title?: string;
  summary?: string;
  highlights?: string[];
  compatibility?: string;
  trace?: Record<string, unknown>;
};

export async function checkUpdate(opts?: ApiOpts): Promise<UpdateCheck> {
  return apiCall<UpdateCheck>("/api/update/check", undefined, opts);
}

export type UpdateStatusInfo = {
  status: "ok";
  job_id: string;
  running: boolean;
  done: boolean;
  failed: boolean;
  cancelled: boolean;
  phase: LifecycleJobPhase;
  progress: number;
  step: string;
  message: string;
  log_tail: string[];
  cancellable: boolean;
  bytes_total: number;
  bytes_downloaded: number;
  bytes_per_second: number;
  rolled_back: boolean;
  rollback_error: string;
  cleanup_pending: boolean;
  cleanup_warning: string;
  interrupted: boolean;
  recovery_required: boolean;
  error: string;
};

export async function fetchUpdateStatus(opts?: ApiOpts): Promise<UpdateStatusInfo> {
  return apiCall<UpdateStatusInfo>(
    "/api/update/status",
    undefined,
    { ...opts, timeoutMs: opts?.timeoutMs ?? UPDATE_STATUS_POLL_TIMEOUT_MS },
  );
}

export type UpdateReconnectResponse = UpdateStatusInfo & { reconnected: true };

export async function reconnectUpdate(opts?: ApiOpts): Promise<UpdateReconnectResponse> {
  return apiCall<UpdateReconnectResponse>("/api/update/reconnect", undefined, opts);
}

export type UninstallCheck = {
  can_uninstall: boolean;
  modes: string[];
  install_dir: string;
};

export async function checkUninstall(): Promise<UninstallCheck> {
  const payload = await requestJson<any>("/api/uninstall/check");
  if (payload.status !== "ok") throw new Error(payload.error || "卸载检查失败");
  return payload;
}

export type DiagnosticReport = Blob;

export async function fetchDiagnosticReport(opts?: ApiOpts): Promise<DiagnosticReport> {
  const res = await secureFetch("/api/diagnostics/package", { signal: opts?.signal });
  if (!res.ok) {
    throw new ApiError(
      "DiagnosticError",
      `诊断包生成失败 (HTTP ${res.status})`,
      res.status,
    );
  }
  return await res.blob();
}

export async function runUninstall(mode: "cadence_only" | "detach") {
  const payload = await requestJson<any>("/api/uninstall/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (payload.status !== "ok") throw new Error(payload.error || "卸载启动失败");
  return payload;
}
