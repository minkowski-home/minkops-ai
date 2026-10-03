import { Link } from "react-router-dom";
import { ACCESS_HREF, FUNNEL_HREF } from "../content/site";
import { Section } from "../layout/Section";

const STARTING_POINTS = [
  {
    number: "01",
    title: "You choose",
    description: "Pick the employees and workflows your business needs.",
    action: "Explore workflow examples",
    to: FUNNEL_HREF
  },
  {
    number: "02",
    title: "Minkops curates",
    description: "Tell us what your business needs. We’ll put together a starting point.",
    action: "Tell us what you need",
    to: ACCESS_HREF
  }
] as const;

export default function WorkflowModel() {
  return (
    <Section
      title="A good place to start."
    >
      <div className="mk-starting-points">
        <ol className="mk-starting-points__options">
          {STARTING_POINTS.map((point) => (
            <li key={point.number}>
              <Link className="mk-starting-points__option" to={point.to}>
                <span className="mk-starting-points__number" aria-hidden="true">
                  {point.number}
                </span>
                <span className="mk-starting-points__content">
                  <h3 className="mk-starting-points__title">{point.title}</h3>
                  <span className="mk-starting-points__description">
                    {point.description}
                  </span>
                  <span className="mk-starting-points__action">
                    {point.action}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </div>
    </Section>
  );
}
