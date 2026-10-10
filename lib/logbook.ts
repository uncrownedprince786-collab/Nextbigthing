/// The logbook's stored lines, read back into what the page renders.
///
/// `tools/audit_log.py` stores each entry as `[text, style]` pairs. This reads them defensively -- the
/// column is JSON written by another program -- and classifies each line once, so the page only has to
/// draw: a rule for a divider, a heading, a bold line, or plain text with its indentation kept.

export type LogLine =
  | { kind: "rule" }
  | { kind: "title"; text: string }
  | { kind: "heading"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "text"; text: string; indent: number };

export function toLines(stored: unknown): LogLine[] {
  if (!Array.isArray(stored)) return [];
  const out: LogLine[] = [];
  for (const item of stored) {
    if (!Array.isArray(item)) continue;
    const text = typeof item[0] === "string" ? item[0] : "";
    const style = typeof item[1] === "string" ? item[1] : "";
    if (/^[=-]{10,}$/.test(text.trim())) {
      out.push({ kind: "rule" });
    } else if (!text.trim()) {
      continue;
    } else if (style === "title" || style === "heading" || style === "bold") {
      out.push({ kind: style, text: text.trim() });
    } else {
      const indent = text.length - text.trimStart().length;
      out.push({ kind: "text", text: text.trim(), indent });
    }
  }
  // Two rules in a row (the review's double divider) draw as one.
  return out.filter((l, i) => !(l.kind === "rule" && out[i - 1]?.kind === "rule"));
}
