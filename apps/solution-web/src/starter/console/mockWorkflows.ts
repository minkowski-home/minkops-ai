import type { PresetWorkflow } from "./types";

export const PRESET_WORKFLOWS: PresetWorkflow[] = [
  {
    id: "whatsapp-image-to-excel",
    agentId: "agent-imel",
    label: "WhatsApp images → Excel",
    detail: "Read incoming WhatsApp images, extract structured records, route exceptions for review, and write approved rows to Excel.",
    outcome: "The WhatsApp image-to-Excel workflow is planned and cannot be started yet.",
    availability: "planned"
  },
  {
    id: "transactions-to-warehouse",
    agentId: "agent-synapse",
    label: "Transaction reconciliation → warehouse",
    detail: "Collect transactions across connected banks and accounts, reconcile them, then load the curated result into the warehouse on a fixed schedule.",
    outcome: "The transaction-reconciliation workflow is planned and cannot be started yet.",
    availability: "planned"
  }
];
