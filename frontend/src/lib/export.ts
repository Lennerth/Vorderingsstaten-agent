import type { ProgressReportResponse } from "../api/types";

export function downloadText(filename: string, content: string, type = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function exportMarkdown(markdown: string) {
  downloadText(`vorderingsstaat-${today()}.md`, markdown || "", "text/markdown;charset=utf-8");
}

export function exportJson(data: ProgressReportResponse | null) {
  downloadText(
    `vorderingsstaat-${today()}.json`,
    JSON.stringify(data ?? {}, null, 2),
    "application/json;charset=utf-8",
  );
}

function today() {
  return new Date().toISOString().slice(0, 10);
}
