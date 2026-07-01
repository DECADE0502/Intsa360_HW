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
  summary: { failed: number; warnings: number; ok: number; total: number };
  manifest: Record<string, unknown>;
  checks: LifecycleCheck[];
};

async function requestJson<T = any>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(input, init);
  } catch (error) {
    const err = error as Error;
    if (err.name === "TypeError" || /fetch/i.test(err.message || "")) {
      throw new Error("后端服务已断开，请重新启动平台或点击重新连接。");
    }
    throw err;
  }
  let payload: any = {};
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }
  if (!res.ok) {
    throw new Error(payload.error || payload.message || `请求失败 (${res.status})`);
  }
  return payload as T;
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

export async function fetchPlatformStatus() {
  const payload = await requestJson<any>("/api/platform/status");
  return payload;
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
  const payload = await requestJson<any>("/api/upload", { method: "POST", body: form });
  if (payload.status !== "ok") throw new Error(payload.error || "上传失败");
  return payload;
}

export async function runTool(tool: string, params: Record<string, unknown>) {
  const payload = await requestJson<any>(`/api/tools/${tool}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (payload.status === "error") throw new Error(payload.error || "运行失败");
  return payload;
}

export async function fetchVersion(): Promise<string> {
  const payload = await requestJson<any>("/api/version");
  if (payload.status !== "ok") throw new Error(payload.error || "版本获取失败");
  return payload.version;
}

export async function startUpdate() {
  const payload = await requestJson<any>("/api/update/run", { method: "POST" });
  if (payload.status !== "ok") throw new Error(payload.error || "更新启动失败");
  return payload;
}

export type UpdateCheck = {
  version: string;
  revision: string;
  remote_version: string;
  remote_revision: string;
  update_notice?: UpdateNotice;
  notice_status: string;
  display_remote: string;
  has_update: boolean;
  can_update: boolean;
  update_reason: string;
  remote_status: string;
  remote_revision_status: string;
  message: string;
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

export async function checkUpdate(): Promise<UpdateCheck> {
  const payload = await requestJson<any>("/api/update/check");
  if (payload.status !== "ok") throw new Error(payload.error || "更新检查失败");
  return payload;
}

export type UpdateStatusInfo = {
  running: boolean;
  done: boolean;
  failed: boolean;
  progress: number;
  step: string;
  message: string;
  log_tail: string[];
};

export async function fetchUpdateStatus(): Promise<UpdateStatusInfo> {
  const payload = await requestJson<any>("/api/update/status");
  if (payload.status !== "ok") throw new Error(payload.error || "更新状态获取失败");
  return payload;
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

export async function runUninstall(mode: "detach") {
  const payload = await requestJson<any>("/api/uninstall/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (payload.status !== "ok") throw new Error(payload.error || "卸载启动失败");
  return payload;
}
