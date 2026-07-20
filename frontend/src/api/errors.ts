export class ApiError extends Error {
  constructor(
    public readonly kind: string,
    public readonly userMessage: string,
    public readonly httpStatus: number,
    public readonly raw?: unknown,
  ) {
    super(userMessage);
    this.name = 'ApiError';
  }
}

const DISCONNECTED_MESSAGE = "后端服务已断开，请重新启动平台或点击重新连接。";
const TIMEOUT_MESSAGE = "请求超时，请稍后重试。";
const GENERIC_MESSAGE = "操作失败，请重试或查看系统状态。";

export function toUserMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.userMessage || GENERIC_MESSAGE;
  }
  const name = typeof error === "object" && error !== null && "name" in error ? String(error.name) : "";
  const rawMessage =
    typeof error === "object" && error !== null && "message" in error ? String(error.message) : String(error ?? "");
  if (name === "AbortError") {
    console.warn("[Insta360_HW] 请求被中止", error);
    return TIMEOUT_MESSAGE;
  }
  if (/fetch/i.test(rawMessage) || (error instanceof TypeError && /(network|load)/i.test(rawMessage))) {
    console.warn("[Insta360_HW] 后端连接失败", error);
    return DISCONNECTED_MESSAGE;
  }
  console.warn("[Insta360_HW] 未分类的前端异常", error);
  return GENERIC_MESSAGE;
}
