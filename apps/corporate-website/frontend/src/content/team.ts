import { AGENTS } from "./agents";

/**
 * The visitor's team: the employees they've picked on the roster, either one
 * by one or by hiring a crew. Stored as names, always kept in roster order and
 * free of duplicates, so two crews that share a member (Imel is on several)
 * never list them twice.
 */
export type Team = readonly string[];

const ROSTER_ORDER = new Map(AGENTS.map((agent, index) => [agent.name, index]));

function normalise(names: Iterable<string>): Team {
  return [...new Set(names)].sort(
    (a, b) => (ROSTER_ORDER.get(a) ?? 0) - (ROSTER_ORDER.get(b) ?? 0)
  );
}

export function addToTeam(team: Team, names: readonly string[]): Team {
  return normalise([...team, ...names]);
}

export function removeFromTeam(team: Team, names: readonly string[]): Team {
  const leaving = new Set(names);
  return team.filter((name) => !leaving.has(name));
}

export function hasEveryone(team: Team, names: readonly string[]): boolean {
  return names.every((name) => team.includes(name));
}
