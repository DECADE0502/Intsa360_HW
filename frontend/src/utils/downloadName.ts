function pad(value: number) {
  return String(value).padStart(2, "0");
}

function localTimestamp(now: Date) {
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

function safeFilename(value: string) {
  const basename = value.replaceAll("\\", "/").split("/").pop()?.trim() || "";
  return basename.replace(/[\u0000-\u001f<>:"|?*]/g, "_");
}

function headerFilename(contentDisposition: string | null) {
  if (!contentDisposition) return "";
  const encoded = contentDisposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)?.[1]?.trim().replace(/^"|"$/g, "");
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      // Fall through to the ASCII filename supplied by the same header.
    }
  }
  return contentDisposition.match(/filename\s*=\s*"([^"]+)"/i)?.[1]
    || contentDisposition.match(/filename\s*=\s*([^;]+)/i)?.[1]?.trim()
    || "";
}

export function packageDownloadName(contentDisposition: string | null, boardName: string, now = new Date()) {
  const supplied = safeFilename(headerFilename(contentDisposition));
  if (supplied) return supplied;
  const safeBoard = safeFilename(boardName) || "BOM";
  return `${safeBoard}_${localTimestamp(now)}.zip`;
}
