import { useId, useRef, useState, type KeyboardEvent } from "react";
import { AGENTS } from "../content/agents";
import { CREWS, type Crew } from "../content/crews";
import { ANCHORS } from "../content/site";
import { addToTeam, removeFromTeam, type Team } from "../content/team";
import { Section } from "../layout/Section";
import { cx } from "../ui/primitives";
import CrewGrid from "./roster/CrewGrid";
import EmployeeGrid from "./roster/EmployeeGrid";
import TeamTray from "./roster/TeamTray";

/*
 * The roster offers two ways to hire, over one shared team:
 *  - Crews: ready-made teams built around a role you'd otherwise hire for.
 *  - Build your own: pick employees one at a time.
 * The team lives in the landing page so the access form can read it.
 */

type Mode = "crews" | "individuals";

const MODES: ReadonlyArray<{ id: Mode; label: string; hint: string }> = [
  { id: "crews", label: "Ready-made crews", hint: `${CREWS.length} crews` },
  { id: "individuals", label: "Build your own", hint: `${AGENTS.length} people` }
];

export default function Roster({
  team,
  onTeamChange
}: {
  team: Team;
  onTeamChange: (team: Team) => void;
}) {
  const [mode, setMode] = useState<Mode>("crews");
  const tabRefs = useRef(new Map<Mode, HTMLButtonElement>());
  const baseId = useId();

  const toggleCrew = (crew: Crew, hired: boolean) =>
    onTeamChange(
      hired ? removeFromTeam(team, crew.members) : addToTeam(team, crew.members)
    );

  const toggleEmployee = (name: string) =>
    onTeamChange(
      team.includes(name) ? removeFromTeam(team, [name]) : addToTeam(team, [name])
    );

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next: Mode = mode === "crews" ? "individuals" : "crews";
    const target =
      event.key === "Home" ? "crews" : event.key === "End" ? "individuals" : next;
    setMode(target);
    tabRefs.current.get(target)?.focus();
  };

  return (
    <Section
      id={ANCHORS.roster}
      tone="sunken"
      eyebrow={`The team · ${AGENTS.length} roles and counting`}
      title="Hire one. Or hire the whole crew."
      lead="Every Minkops employee owns a whole job, the way a person would. Shortlist a ready-made crew built around a role you'd otherwise advertise for, or pick people one at a time. Then we sit down together and work out what fits your business."
    >
      <div className="mk-mode" role="tablist" aria-label="How would you like to hire?">
        {MODES.map((option) => {
          const selected = option.id === mode;
          return (
            <button
              key={option.id}
              ref={(node) => {
                if (node) tabRefs.current.set(option.id, node);
              }}
              type="button"
              role="tab"
              id={`${baseId}-${option.id}-tab`}
              aria-selected={selected}
              aria-controls={`${baseId}-${option.id}-panel`}
              tabIndex={selected ? 0 : -1}
              className={cx("mk-mode__tab", selected && "is-selected")}
              onClick={() => setMode(option.id)}
              onKeyDown={onTabKeyDown}
            >
              {option.label}
              <span className="mk-mode__hint">{option.hint}</span>
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`${baseId}-${mode}-panel`}
        aria-labelledby={`${baseId}-${mode}-tab`}
        key={mode}
        className="mk-mode__panel"
      >
        {mode === "crews" ? (
          <CrewGrid team={team} onToggle={toggleCrew} />
        ) : (
          <EmployeeGrid team={team} onToggle={toggleEmployee} />
        )}
      </div>

      <TeamTray
        team={team}
        onRemove={(name) => onTeamChange(removeFromTeam(team, [name]))}
        onClear={() => onTeamChange([])}
      />
    </Section>
  );
}
