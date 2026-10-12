/** Only schema-declared defaults are persisted; resource grants remain run-specific. */
export function defaultableValues(values: Record<string, unknown>, properties: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(values).filter(([key]) => key in properties));
}

/** A completed write and outstanding human attention are independent outcomes. */
export function billOutcome(status: string | undefined, attention: boolean): string {
  const suffix = attention ? " · check Attention" : "";
  if (status === "saved") return "Saved and verified" + suffix;
  if (status === "duplicate") return "Duplicate skipped" + suffix;
  if (status === "writing") return "Saving and checking";
  if (status === "rejected") return "Not written";
  if (status === "held" || attention) return "Needs attention";
  return "Ready to write";
}

export function elapsedLabel(start: string, end: number): string | null {
  const beginning = Date.parse(start);
  if (!Number.isFinite(beginning) || !Number.isFinite(end) || beginning > end) return null;
  const seconds = Math.floor((end - beginning) / 1000);
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
