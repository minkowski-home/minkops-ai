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
            Minkops groups AI Employees around practical business Workflows. A Workflow
            describes the outcome, the steps involved and the tools it may use. Start with
            a repeatable process, then shape its access and review rules around your
            business.
          </p>
          <p>
            Skills explain how work should be done. Tools and connectors provide the
            approved way to interact with existing systems. People remain responsible for
            approvals and decisions the Workflow is not allowed to make.
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
