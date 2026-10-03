import { Section } from "../layout/Section";
import { Card, Eyebrow } from "../ui/primitives";

const MODEL = [
  {
    name: "Employee",
    body: "The product grouping for AI-supported business work, configured under rules set by people."
  },
  {
    name: "Workflow",
    body: "The defined business outcome, steps, and points where a person reviews or decides."
  },
  {
    name: "Skills, tools and connectors",
    body: "Skills describe procedures. Approved tools and connectors provide access to files and external systems."
  }
] as const;

export default function WorkflowModel() {
  return (
    <Section
      eyebrow="The product model"
      title="Employee, Workflow, skills and tools."
      lead="The Employee is the product grouping. The Workflow is the unit of work. Its instructions describe the procedure, while approved tools and connectors determine which systems it can use."
    >
      <ol className="mk-model">
        {MODEL.map((item, index) => (
          <li key={item.name}>
            <Card className="mk-model__card">
              <Eyebrow>{String(index + 1).padStart(2, "0")}</Eyebrow>
              <h3 className="mk-model__title">{item.name}</h3>
              <p className="mk-model__body">{item.body}</p>
            </Card>
          </li>
        ))}
      </ol>
      <p className="mk-model__note">
        A skill describes a procedure; it does not grant system access or prove an
        external write. Workflows need explicit access and verification for those steps.
      </p>
    </Section>
  );
}
