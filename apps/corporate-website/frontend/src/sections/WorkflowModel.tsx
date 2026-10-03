import { Section } from "../layout/Section";

const STARTING_POINTS = [
  {
    number: "01",
    title: "You choose",
    description: "Pick the employees and workflows your business needs."
  },
  {
    number: "02",
    title: "Minkops curates",
    description: "Tell us what your business needs. We’ll put together a starting point."
  }
] as const;

export default function WorkflowModel() {
  return (
    <Section
      title="A good place to start."
    >
      <div className="mk-starting-points">
        <p className="mk-starting-points__origin">Your business</p>
        <ol className="mk-starting-points__options">
          {STARTING_POINTS.map((point) => (
            <li className="mk-starting-points__option" key={point.number}>
              <span className="mk-starting-points__number" aria-hidden="true">
                {point.number}
              </span>
              <div>
                <h3 className="mk-starting-points__title">{point.title}</h3>
                <p className="mk-starting-points__description">
                  {point.description}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </Section>
  );
}
