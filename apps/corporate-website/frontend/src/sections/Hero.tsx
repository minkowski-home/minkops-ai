import { AGENTS, DEPARTMENTS } from "../content/agents";
import { FUNNEL_HREF } from "../content/site";
import { Icon } from "../ui/Icon";
import { ButtonLink, Eyebrow, StatusDot } from "../ui/primitives";

const pad = (value: number) => String(value).padStart(2, "0");

export default function Hero() {
  const facts = [
    {
      figure: pad(AGENTS.length),
      label: "Roles on shift",
      detail: `Across ${DEPARTMENTS.length} departments, from the front desk and the books to a building site and a kitchen.`
    },
    {
      figure: "24×7",
      label: "Hours they keep",
      detail: "Nobody clocks off, so Monday starts with the weekend already handled."
    },
    {
      figure: "0",
      label: "Instructions to type",
      detail: "Set the rules once. After that, your part is mostly saying yes or no."
    }
  ];

  return (
    <section className="mk-hero" aria-labelledby="hero-title">
      <div className="mk-container mk-hero__inner mk-enter">
        <Eyebrow rule>The operating system for zero-man companies</Eyebrow>

        <h1 id="hero-title" className="mk-hero__title">
          Every desk filled. <span className="mk-accent">No one sitting at them.</span>
        </h1>

        <div className="mk-hero__lead">
          <p>
            Minkops is building a company&apos;s worth of AI employees. Each one takes a
            whole role, not a single task, and they all share one memory of your business,
            so work moves between them the way it would between colleagues who&apos;ve sat
            side by side for years.
          </p>
          <p>
            You set the rules once. They run the day, around the clock, and bring you only
            the calls that should be yours. The whole team is already on shift, and it
            keeps growing.
          </p>
        </div>

        <div className="mk-hero__actions">
          <ButtonLink
            to={FUNNEL_HREF}
            size="lg"
            variant="primary"
            iconRight={<Icon name="chevronRight" size={16} />}
          >
            Find your first hire
          </ButtonLink>
          <ButtonLink to="/orchestration" size="lg" variant="secondary">
            See how they work together
          </ButtonLink>
          <StatusDot
            status="active"
            halo
            label={`${AGENTS.length} employees on shift right now`}
          />
        </div>

        <dl className="mk-hero__facts">
          {facts.map((fact) => (
            <div key={fact.label} className="mk-hero__fact">
              <dt>
                <span className="mk-hero__figure">{fact.figure}</span>
                <span className="mk-hero__fact-label">{fact.label}</span>
              </dt>
              <dd>{fact.detail}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
