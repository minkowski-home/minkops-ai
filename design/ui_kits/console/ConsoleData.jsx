const AGENTS = [
  { id: "agent-imel", name: "Imel", role: "Email handler", status: "active", lastActive: "4m ago", enabled: true, team: "CX Response Team" },
  { id: "agent-kall", name: "Kall", role: "Support rep", status: "idle", lastActive: "22m ago", enabled: true, team: "CX Response Team" },
  { id: "agent-scout", name: "Scout", role: "Lead research", status: "active", lastActive: "2m ago", enabled: true, team: null },
  { id: "agent-synapse", name: "Synapse", role: "Reporting", status: "idle", lastActive: "3h ago", enabled: true, team: null },
  { id: "agent-aria", name: "Aria", role: "Scheduling", status: "disabled", lastActive: "never", enabled: false, team: null }
];

const TEAM = {
  id: "team-cx",
  name: "CX Response Team",
  description: "Handles end-to-end customer communication and support ticket resolution.",
  members: ["Imel", "Kall"],
  enabled: true
};

const MESSAGES = [
  { id: "m1", role: "human", sender: "You", content: "Imel — the Acme refund thread came back overnight. Draft the reply and flag anything over threshold.", time: "14:28" },
  { id: "m2", role: "agent", sender: "Imel", content: "Read and classified: refund request, ticket #2847. Drafted a reply approving $3,200. That's over the $1,000 auto-approval threshold, so it's waiting on you in the queue.", time: "14:29" },
  { id: "m3", role: "human", sender: "You", content: "Scout, pull the NovaBuild contact into the pipeline too.", time: "14:31" },
  { id: "m4", role: "agent", sender: "Scout", content: "Enriched Marcus Wren (VP Engineering, NovaBuild). Company size and budget signals are at 72% confidence — below auto-qualify, so I've queued it for review.", time: "14:32" }
];

const INTERRUPTS = [
  { id: "int-002", type: "escalation", priority: "critical", status: "pending", title: "Escalation: repeated SLA breach — TechFlow Inc", description: "TechFlow Inc has had 3 tickets breach SLA in 7 days. Kall has exhausted its KB resolution paths. Enterprise tier — manual intervention recommended.", agentName: "Kall", taskTitle: "TechFlow Inc — SLA breach pattern", time: "31m ago", suggestedAction: "Contact the TechFlow account manager directly and schedule a call." },
  { id: "int-001", type: "approval", priority: "high", status: "pending", title: "Approve refund: Acme Corp — $3,200", description: "Imel drafted a refund approval for ticket #2847. The amount exceeds the $1,000 auto-approval threshold and requires operator sign-off before sending.", agentName: "Imel", taskTitle: "Acme Corp refund request #2847", time: "8m ago", suggestedAction: "Review the drafted email and approve or modify the refund amount." },
  { id: "int-003", type: "review", priority: "medium", status: "pending", title: "Review scraped lead profile — Marcus Wren, NovaBuild", description: "Scout enriched a lead profile for Marcus Wren (VP Engineering, NovaBuild). Confidence on company size and budget signals is 72% — below the auto-qualify threshold.", agentName: "Scout", taskTitle: "Lead enrichment: Marcus Wren", time: "52m ago", suggestedAction: "Verify company size on LinkedIn and confirm the budget signal before qualifying." },
  { id: "int-004", type: "review", priority: "low", status: "acknowledged", title: "Draft blog post ready for review", description: "Synapse completed a first draft of the Q1 product update post based on your outline.", agentName: "Synapse", taskTitle: "Q1 product update blog post", time: "2h ago", suggestedAction: null }
];

const USER = { name: "Kartik Shah", role: "Operator", tenantName: "Minkowski Home", tenantId: "tenant_001" };

Object.assign(window, { AGENTS, TEAM, MESSAGES, INTERRUPTS, USER });
