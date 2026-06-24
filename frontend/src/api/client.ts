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

export async function fetchPlatformStatus() {
  const res = await fetch("/api/platform/status");
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.error || "平台状态加载失败");
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
