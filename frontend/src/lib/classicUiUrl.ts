/** URL for the classic static UI served by FastAPI. */
export function getClassicUiUrl(): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, "");
  if (base) return `${base}/classic`;
  return "http://localhost:8000/classic";
}
