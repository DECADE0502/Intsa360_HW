export function outputHref(path: string): string {
  const normalized = String(path || "").replaceAll("\\", "/");
  const marker = "/data/outputs/";
  const index = normalized.indexOf(marker);
  const relative = index >= 0
    ? normalized.slice(index + marker.length)
    : normalized.replace(/^data\/outputs\//, "");
  const encoded = relative
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return `/outputs/${encoded}`;
}
