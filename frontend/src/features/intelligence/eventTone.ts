/** Audit event type -> timeline dot colour. Unknown types fall back to grey. */
export const EVENT_TONE = (type: string): string => {
  if (type.includes("STALE") || type.includes("REJECT")) return "var(--risk-critical)";
  if (type.includes("APPROV")) return "var(--policy-passed)";
  if (type.includes("CONFIRM") || type.includes("FULFIL") || type.includes("DELIVER")) return "var(--state-confirmed)";
  if (type.includes("MATERIAL") || type.includes("COUNTER") || type.includes("REVIS")) return "var(--state-negotiating)";
  if (type.includes("SENT") || type.includes("SUBMIT") || type.includes("ORDER")) return "var(--accent-500)";
  if (type.includes("POLICY") || type.includes("ALLOCAT")) return "var(--gov-500)";
  return "var(--ink-300)";
};
