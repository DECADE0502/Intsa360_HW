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

export async function fetchTools(): Promise<ToolInfo[]> {
  const res = await fetch("/api/tools");
  if (!res.ok) throw new Error("工具列表加载失败");
  const payload = await res.json();
  return payload.tools || [];
}

export async function fetchCapabilities(): Promise<{ platform: { name: string; cadence_menu: string }; capabilities: Capability[] }> {
  const res = await fetch("/api/capabilities");
  if (!res.ok) throw new Error("平台能力加载失败");
  return await res.json();
}

export async function fetchPlugins(): Promise<PluginsPayload> {
  const res = await fetch("/api/plugins");
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || "插件列表加载失败");
  return payload;
}

export async function fetchHistory(): Promise<HistoryRun[]> {
  const res = await fetch("/api/history");
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || "历史记录加载失败");
  return payload.runs || [];
}

export async function fetchHistoryRun(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`/api/history/${encodeURIComponent(id)}`);
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || "历史详情加载失败");
  return payload;
}

export async function deleteHistoryRun(id: string) {
  const res = await fetch(`/api/history/${encodeURIComponent(id)}`, { method: "DELETE" });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "删除记录失败");
  return payload;
}

export async function clearHistory() {
  const res = await fetch("/api/history", { method: "DELETE" });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "清空历史失败");
  return payload;
}

export async function fetchPlatformStatus() {
  const res = await fetch("/api/platform/status");
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || "平台状态加载失败");
  return payload;
}

export async function fetchLifecycleCheck(): Promise<LifecyclePayload> {
  const res = await fetch("/api/lifecycle/check");
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "安装自检加载失败");
  return payload;
}

export async function setCadenceMenuVisibility(id: string, showInCadence: boolean) {
  const res = await fetch(`/api/capabilities/${encodeURIComponent(id)}/cadence-menu`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ show_in_cadence: showInCadence, redeploy: true }),
  });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "菜单状态更新失败");
  return payload.capability as Capability;
}

export async function setPluginCadenceMenuVisibility(id: string, showInCadence: boolean) {
  const res = await fetch(`/api/plugins/${encodeURIComponent(id)}/cadence-menu`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ show_in_cadence: showInCadence, redeploy: true }),
  });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "插件菜单状态更新失败");
  return payload.plugin as PluginInfo;
}

export async function uploadFiles(files: File[]): Promise<{ files: Array<{ path: string; name: string }> }> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const res = await fetch("/api/upload", { method: "POST", body: form });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "上传失败");
  return payload;
}

export async function runTool(tool: string, params: Record<string, unknown>) {
  const res = await fetch(`/api/tools/${tool}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  const payload = await res.json();
  if (!res.ok || payload.status === "error") throw new Error(payload.error || "运行失败");
  return payload;
}

export async function fetchVersion(): Promise<string> {
  const res = await fetch("/api/version");
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "版本获取失败");
  return payload.version;
}

export async function startUpdate() {
  const res = await fetch("/api/update/run", { method: "POST" });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "更新启动失败");
  return payload;
}

export type UpdateCheck = {
  version: string;
  remote_version: string;
  has_update: boolean;
  can_update: boolean;
  remote_status: string;
  message: string;
};

export async function checkUpdate(): Promise<UpdateCheck> {
  const res = await fetch("/api/update/check");
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "更新检查失败");
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
  const res = await fetch("/api/update/status");
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "更新状态获取失败");
  return payload;
}

export type UninstallStatusInfo = UpdateStatusInfo;

export async function fetchUninstallStatus(): Promise<UninstallStatusInfo> {
  const res = await fetch("/api/uninstall/status");
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "卸载状态获取失败");
  return payload;
}

export type UninstallCheck = {
  can_uninstall: boolean;
  modes: string[];
  install_dir: string;
};

export async function checkUninstall(): Promise<UninstallCheck> {
  const res = await fetch("/api/uninstall/check");
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "卸载检查失败");
  return payload;
}

export async function runUninstall(mode: "detach" | "full") {
  const res = await fetch("/api/uninstall/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  const payload = await res.json();
  if (!res.ok || payload.status !== "ok") throw new Error(payload.error || "卸载启动失败");
  return payload;
}
