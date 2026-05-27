import type { EvidenceItem } from "../api/types";

export type EvidenceFileGroup = {
  filename: string;
  bySourceType: { sourceType: string; items: EvidenceItem[] }[];
};

export function groupEvidenceByFileAndType(items: EvidenceItem[]): EvidenceFileGroup[] {
  const fileMap = new Map<string, Map<string, EvidenceItem[]>>();

  for (const item of items) {
    const filename = item.filename?.trim() || "unknown";
    const sourceType = item.source_type?.trim() || "unknown";
    if (!fileMap.has(filename)) fileMap.set(filename, new Map());
    const typeMap = fileMap.get(filename)!;
    if (!typeMap.has(sourceType)) typeMap.set(sourceType, []);
    typeMap.get(sourceType)!.push(item);
  }

  return [...fileMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([filename, typeMap]) => ({
      filename,
      bySourceType: [...typeMap.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([sourceType, typeItems]) => ({ sourceType, items: typeItems })),
    }));
}
