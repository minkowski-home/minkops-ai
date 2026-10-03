import { FUNNEL_HREF } from "../content/site";
import { Icon } from "../ui/Icon";
import { ButtonLink, Eyebrow } from "../ui/primitives";

export default function Hero() {
  return (
    <section className="mk-hero" aria-labelledby="hero-title">
      <div className="mk-container mk-hero__inner mk-enter">
        <Eyebrow rule>AI employees · practical workflows</Eyebrow>

        <h1 id="hero-title" className="mk-hero__title">
          Every desk filled. <span className="mk-accent">No one sitting at them.</span>
        </h1>

        <div className="mk-hero__lead">
          <p>
            Start with the repeat work that keeps landing on your plate. Minkops helps
            you find a good way to handle it while keeping you in charge of the decisions
            that matter.
          </p>
          <p>
            Choose and set things up yourself, or tell us about your business and let
            Minkops put together a good place to start.
          </p>
        </div>

        <div className="mk-hero__actions">
          <ButtonLink
            to={FUNNEL_HREF}
            size="lg"
            variant="primary"
            iconRight={<Icon name="chevronRight" size={16} />}
          >
            Explore a workflow
          </ButtonLink>
          <ButtonLink to="/orchestration" size="lg" variant="secondary">
            How it works
          </ButtonLink>
        </div>
      </div>
    </section>
  );
}
