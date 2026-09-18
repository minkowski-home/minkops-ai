import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type RefObject
} from "react";
import { AGENTS, DEPARTMENTS, type Department } from "../../content/agents";
import type { Team } from "../../content/team";
import { Icon } from "../../ui/Icon";
import { AgentTile } from "../../ui/product";
import { Button, cx } from "../../ui/primitives";

/*
 * "Build your own": every employee, hired one at a time.
 *
 * The roster has to read well at 14 people and at 100, so the view has three
 * layers:
 *  1. A shift strip: one small tile per employee, the whole team at a glance.
 *     Clicking a tile jumps to that employee's department.
 *  2. Department filters, the grouping that stays meaningful as the roster grows.
 *  3. A windowed grid: two rows at a time, sized to however many columns the
 *     viewport actually fits, with the next batch revealed on request.
 */

const ROWS_PER_BATCH = 2;
/** On a single-column phone layout, two rows would be two cards: too stingy. */
const MIN_BATCH = 4;
/** Matches the grid's minmax() floor. Used only until the grid has been measured. */
const FALLBACK_COLUMNS = 4;
/** How many of the next batch get a glyph preview on the reveal button. */
const PREVIEW_FACES = 4;

type Filter = Department | "all";

/** Tracks how many columns the auto-fill grid currently resolves to. */
function useGridColumns(ref: RefObject<HTMLElement>) {
  const [columns, setColumns] = useState(FALLBACK_COLUMNS);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      const template = getComputedStyle(element).gridTemplateColumns;
      const count = template.split(" ").filter(Boolean).length;
      if (count > 0) setColumns(count);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  return columns;
}

function ShiftStrip({ onPick }: { onPick: (department: Department) => void }) {
  return (
    <div className="mk-shift">
      <p className="mk-shift__label">
        <span className="mk-shift__dot" aria-hidden="true" />
        <strong>{AGENTS.length} on shift</strong> · {DEPARTMENTS.length} departments · 0
        sick days this year
      </p>
      <ul className="mk-shift__team" aria-label="Everyone on shift">
        {AGENTS.map((employee) => (
          <li key={employee.name}>
            <button
              type="button"
              className="mk-shift__agent"
              title={`${employee.name} · ${employee.role}`}
              aria-label={`${employee.name}, ${employee.role}. Show the ${employee.department} team.`}
              onClick={() => onPick(employee.department)}
            >
              <Icon name={employee.glyph} size={16} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function EmployeeGrid({
  team,
  onToggle
}: {
  team: Team;
  onToggle: (name: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [batches, setBatches] = useState(1);
  // Index from which cards animate in. Cards already on screen stay still.
  const [revealFrom, setRevealFrom] = useState<number | null>(null);
  const gridRef = useRef<HTMLUListElement>(null);
  const columns = useGridColumns(gridRef);

  const employees = useMemo(
    () => AGENTS.filter((employee) => filter === "all" || employee.department === filter),
    [filter]
  );

  const batchSize = Math.max(MIN_BATCH, columns * ROWS_PER_BATCH);
  const visibleCount = Math.min(employees.length, batchSize * batches);
  const visible = employees.slice(0, visibleCount);
  const upcoming = employees.slice(visibleCount, visibleCount + batchSize);
  const remaining = employees.length - visibleCount;

  const departmentCounts = useMemo(
    () =>
      new Map(
        DEPARTMENTS.map((department) => [
          department,
          AGENTS.filter((employee) => employee.department === department).length
        ])
      ),
    []
  );

  const chooseFilter = (next: Filter) => {
    if (next === filter) return;
    setFilter(next);
    setBatches(1);
    setRevealFrom(0);
  };

  const showMore = () => {
    setRevealFrom(visibleCount);
    setBatches((current) => current + 1);
  };

  const showFewer = () => {
    setRevealFrom(null);
    setBatches(1);
    const top = gridRef.current?.getBoundingClientRect().top ?? 0;
    if (top < 0) gridRef.current?.scrollIntoView({ block: "center" });
  };

  const filters: ReadonlyArray<{ value: Filter; label: string; count: number }> = [
    { value: "all", label: "Everyone", count: AGENTS.length },
    ...DEPARTMENTS.map((department) => ({
      value: department,
      label: department,
      count: departmentCounts.get(department) ?? 0
    }))
  ];

  return (
    <div className="mk-roster-view">
      <ShiftStrip
        onPick={(department) => {
          chooseFilter(department);
          gridRef.current?.scrollIntoView({ block: "nearest" });
        }}
      />

      <div className="mk-roster-filters" role="group" aria-label="Filter by department">
        {filters.map((option) => (
          <button
            key={option.value}
            type="button"
            className={cx("mk-roster-filter", filter === option.value && "is-active")}
            aria-pressed={filter === option.value}
            onClick={() => chooseFilter(option.value)}
          >
            {option.label}
            <span className="mk-roster-filter__count">{option.count}</span>
          </button>
        ))}
      </div>

      <ul className="mk-roster" aria-label="Minkops employees" ref={gridRef}>
        {visible.map((employee, index) => {
          const animate = revealFrom !== null && index >= revealFrom;
          const hired = team.includes(employee.name);
          return (
            <li
              // Keyed per filter so switching departments replays the entrance.
              key={`${filter}:${employee.name}`}
              className={cx("mk-roster__item", animate && "is-revealed")}
              style={
                animate
                  ? ({ "--mk-stagger": index - (revealFrom ?? 0) } as CSSProperties)
                  : undefined
              }
            >
              <AgentTile
                name={employee.name}
                role={employee.role}
                department={employee.department}
                glyph={employee.glyph}
                now={employee.now}
                selected={hired}
                action={
                  <Button
                    size="sm"
                    variant={hired ? "secondary" : "ghost"}
                    fullWidth
                    aria-pressed={hired}
                    // A toggle keeps one label; aria-pressed carries the state.
                    aria-label={`${employee.name} on your shortlist`}
                    onClick={() => onToggle(employee.name)}
                    iconLeft={<Icon name={hired ? "check" : "plus"} size={12} />}
                  >
                    {hired ? "Shortlisted" : "Shortlist"}
                  </Button>
                }
              />
            </li>
          );
        })}
      </ul>

      <div className="mk-roster-more">
        <p className="mk-roster-more__count" aria-live="polite">
          Showing {visibleCount} of {employees.length}
          {filter === "all" ? "" : ` in ${filter.toLowerCase()}`}
        </p>

        {remaining > 0 ? (
          <Button
            variant="secondary"
            size="lg"
            onClick={showMore}
            className="mk-roster-more__button"
            iconRight={
              <Icon name="chevronRight" size={14} className="mk-roster-more__chevron" />
            }
          >
            <span className="mk-roster-more__faces" aria-hidden="true">
              {upcoming.slice(0, PREVIEW_FACES).map((employee) => (
                <span key={employee.name} className="mk-roster-more__face">
                  <Icon name={employee.glyph} size={16} />
                </span>
              ))}
            </span>
            {upcoming.length === remaining
              ? `Meet the last ${remaining}`
              : `Meet the next ${upcoming.length}`}
          </Button>
        ) : batches > 1 ? (
          <Button variant="ghost" size="lg" onClick={showFewer}>
            Show fewer
          </Button>
        ) : null}
      </div>
    </div>
  );
}
