export interface SourceFile { id: string; path: string; sha256: string }
export interface Source { id: string; label: string; writable: boolean; files: SourceFile[] }
export interface Column { name: string; type: 'string' | 'number' | 'integer' | 'boolean'; concept: string; required: boolean }
export interface Sheet { file_id: string; sheet: string; table?: string | null; header_row: number; role: 'reference' | 'destination' | 'ignore'; key_columns: string[]; columns: Column[] }
export interface Catalog { sheets: Sheet[]; context_notes?: {company_guid:string;observation:string;certainty:string;evidence_ids:string[]}[] }
export interface Evidence { field: string; page: number; quote: string }
export interface BillRecord { company_guid?:string|null; company_name?:string; company_evidence?:string; source_file_id: string; destination_file_id: string; sheet: string; table?: string | null; operation: 'append' | 'update'; data: Record<string, string | number | boolean | null>; evidence: Evidence[]; findings: string[]; derived_fields?: Record<string,string>; status?: string; decision?: 'approve' | 'hold' | 'reject'; current_excel?:Record<string,unknown>; current?: { date:string; invoice_number:string; vendor:string; entries:{ledger:string;amount:number}[] } }
export interface BillResult { records: BillRecord[]; findings: string[]; unresolved?: { source_file_id: string; reason: string }[] }
export interface WritePlan { id: string; source_id: string; path: string; before_sha256: string; after_sha256: string; verified_at: string | null; cancelled_at: string | null; changes: { sheet: string; table?: string | null; row: number; operation: string }[] }
export interface TallyWrite { id:string; device_id:string; company:string; record_index:number; outcome:string|null; verified_at:string|null; finished_at:string|null; cancelled_at:string|null }
export interface Run { id: string; actor_id: string; task_id: string; workflow_key: string; state: string; result: Catalog | BillResult | null; config: Record<string, unknown>; writes: WritePlan[]; tally_writes?:TallyWrite[]; error: string | null }
export interface SavedCatalog { id: string; catalog: Catalog; confirmed_at: string }
