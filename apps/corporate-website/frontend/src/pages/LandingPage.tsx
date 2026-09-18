import { useState } from "react";
import type { WorkArea } from "../content/funnel";
import type { Team } from "../content/team";
import SeoHead from "../layout/SeoHead";
import AccessSection from "../sections/AccessSection";
import AgentFunnel from "../sections/AgentFunnel";
import ConsolePreview from "../sections/ConsolePreview";
import Hero from "../sections/Hero";
import Roster from "../sections/Roster";

export default function LandingPage() {
  // The funnel's recommendation flows down into the access form so the
  // visitor doesn't have to tell us twice what they care about.
  const [recommendedArea, setRecommendedArea] = useState<WorkArea>();
  // Likewise the team built on the roster travels with the access request.
  const [team, setTeam] = useState<Team>([]);

  return (
    <>
      <SeoHead
        bare
        title="Minkops · The operating system for zero-man companies"
        description="AI employees that each take a whole role, share one memory of your business and hand work to each other. You set the rules once and make only the calls that should be yours."
        path="/"
      />
      <Hero />
      <AgentFunnel onRecommendation={setRecommendedArea} />
      <Roster team={team} onTeamChange={setTeam} />
      <ConsolePreview />
      <AccessSection suggestedArea={recommendedArea} team={team} />
    </>
  );
}
