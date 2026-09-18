import { getAgent } from "../../content/agents";
import { ACCESS_HREF } from "../../content/site";
import type { Team } from "../../content/team";
import { Icon } from "../../ui/Icon";
import { Button, ButtonLink, cx } from "../../ui/primitives";

/*
 * The visitor's shortlist, shared by both ways of browsing. It sticks to the
 * bottom of the viewport while the roster is on screen and hands off to the
 * access form. Deliberately not a cart: nothing is bought here, and every sale
 * starts with a conversation, so the call to action books one.
 */
export default function TeamTray({
  team,
  onRemove,
  onClear
}: {
  team: Team;
  onRemove: (name: string) => void;
  onClear: () => void;
}) {
  const empty = team.length === 0;

  return (
    <div className={cx("mk-tray", empty && "is-empty")} aria-live="polite">
      <div className="mk-tray__summary">
        <p className="mk-tray__title">
          Your shortlist
          <span className="mk-tray__count">{team.length}</span>
        </p>
        {empty ? (
          <p className="mk-tray__hint">
            Shortlist a crew or pick people one at a time. We&apos;ll talk it through
            together before anyone starts.
          </p>
        ) : (
          <ul className="mk-tray__members" aria-label="Your shortlist">
            {team.map((name) => (
              <li key={name} className="mk-tray__member">
                <span className="mk-tray__glyph" aria-hidden="true">
                  <Icon name={getAgent(name).glyph} size={14} />
                </span>
                {name}
                <button
                  type="button"
                  className="mk-tray__remove"
                  aria-label={`Remove ${name} from your shortlist`}
                  onClick={() => onRemove(name)}
                >
                  <Icon name="x" size={10} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {empty ? null : (
        <div className="mk-tray__actions">
          <Button variant="ghost" size="md" onClick={onClear}>
            Start over
          </Button>
          <ButtonLink
            to={ACCESS_HREF}
            variant="primary"
            size="md"
            iconRight={<Icon name="chevronRight" size={14} />}
          >
            Talk it through with us
          </ButtonLink>
        </div>
      )}
    </div>
  );
}
