import type { CSSProperties } from "react";
import { getAgent } from "../../content/agents";
import { CREWS, type Crew } from "../../content/crews";
import { hasEveryone, type Team } from "../../content/team";
import { Icon } from "../../ui/Icon";
import { Button, Eyebrow, cx } from "../../ui/primitives";

/*
 * "Crews": ready-made teams named after the hire they stand in for. The card
 * leads with that hire ("Does the job of a staffing clerk") because that's the
 * comparison a business owner is actually making, then shows who's in the crew
 * and what they take off your plate.
 */

function CrewCard({
  crew,
  hired,
  onToggle
}: {
  crew: Crew;
  hired: boolean;
  onToggle: () => void;
}) {
  const titleId = `crew-${crew.id}`;
  return (
    <article className={cx("mk-crew", hired && "is-hired")} aria-labelledby={titleId}>
      <div className="mk-crew__head">
        <Eyebrow>Crew · {crew.members.length} employees</Eyebrow>
        <h3 className="mk-crew__name" id={titleId}>
          {crew.name}
        </h3>
        <p className="mk-crew__replaces">
          <span>Does the job of</span> {crew.replaces}
        </p>
      </div>

      <p className="mk-crew__pitch">{crew.pitch}</p>

      <ul className="mk-crew__members" aria-label={`Who's in the ${crew.name}`}>
        {crew.members.map((name) => {
          const member = getAgent(name);
          return (
            <li key={name} className="mk-crew__member" title={member.role}>
              <span className="mk-crew__member-glyph" aria-hidden="true">
                <Icon name={member.glyph} size={14} />
              </span>
              {name}
            </li>
          );
        })}
      </ul>

      <ul className="mk-crew__covers">
        {crew.covers.map((line) => (
          <li key={line}>
            <Icon name="check" size={12} />
            {line}
          </li>
        ))}
      </ul>

      <Button
        className="mk-crew__action"
        variant={hired ? "secondary" : "primary"}
        fullWidth
        aria-pressed={hired}
        aria-label={`${crew.name} on your shortlist`}
        onClick={onToggle}
        iconLeft={<Icon name={hired ? "check" : "plus"} size={14} />}
      >
        {hired ? "On your shortlist" : "Shortlist this crew"}
      </Button>
    </article>
  );
}

export default function CrewGrid({
  team,
  onToggle
}: {
  team: Team;
  onToggle: (crew: Crew, hired: boolean) => void;
}) {
  return (
    <ul className="mk-crews" aria-label="Ready-made crews">
      {CREWS.map((crew, index) => {
        const hired = hasEveryone(team, crew.members);
        return (
          <li
            key={crew.id}
            className="mk-roster__item is-revealed"
            style={{ "--mk-stagger": index } as CSSProperties}
          >
            <CrewCard crew={crew} hired={hired} onToggle={() => onToggle(crew, hired)} />
          </li>
        );
      })}
    </ul>
  );
}
