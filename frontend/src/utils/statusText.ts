const RISK_STATUS_TEXT: Record<string, string> = {
  warn: "警告",
  ok: "通过",
  info: "提示",
};

export function riskStatusText(value: unknown): string {
  return RISK_STATUS_TEXT[String(value ?? "").toLowerCase()] || "提示";
}
