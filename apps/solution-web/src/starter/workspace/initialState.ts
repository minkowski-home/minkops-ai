export type WorkflowPresetId = "whatsapp-image-to-excel" | "transactions-to-warehouse";
export interface WorkflowInstance { id: string; presetId: WorkflowPresetId; title: string; description: string; team: string; configuration: Record<string, string>; }
export interface HiredTeam { id: string; name: string; description: string; workflows: WorkflowPresetId[]; }
export interface ActiveTask { id: string; workflowId: string; title: string; state: "running" | "waiting"; }
export interface AttentionItem { id: string; taskId: string; title: string; detail: string; }
export const HIRED_TEAMS: HiredTeam[] = [
  { id: "image-operations", name: "Image operations", description: "Receives images, extracts a record, and routes exceptions for review.", workflows: ["whatsapp-image-to-excel"] },
  { id: "ledger-operations", name: "Ledger operations", description: "Collects account activity and prepares it for reconciliation.", workflows: ["transactions-to-warehouse"] }
];
export const ACTIVATED_WORKFLOWS: WorkflowInstance[] = [
  { id: "whatsapp-receipts", presetId: "whatsapp-image-to-excel", title: "WhatsApp images to Excel", description: "Extract records from incoming images and write approved rows to Excel.", team: "Image operations", configuration: { "WhatsApp account": "Operations", "Excel destination": "Daily records" } },
  { id: "transaction-reconciliation", presetId: "transactions-to-warehouse", title: "Transaction reconciliation", description: "Reconcile connected account activity and prepare the warehouse update.", team: "Ledger operations", configuration: { "Accounts": "All connected accounts", "Run cadence": "Every day" } }
];
