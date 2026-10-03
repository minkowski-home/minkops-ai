import SeoHead from "../layout/SeoHead";
import AccessSection from "../sections/AccessSection";
import AgentFunnel from "../sections/AgentFunnel";
import ConsolePreview from "../sections/ConsolePreview";
import Hero from "../sections/Hero";
import WorkflowModel from "../sections/WorkflowModel";

export default function LandingPage() {
  return (
    <>
      <SeoHead
        bare
        title="Minkops · The operating system for zero-man companies"
        description="Minkops groups AI Employees around practical business Workflows, with skills, approved tools, connectors and clear points for human review."
        path="/"
      />
      <Hero />
      <WorkflowModel />
      <AgentFunnel />
      <ConsolePreview />
      <AccessSection />
    </>
  );
}
