import type { SettingSpec } from "../api";
import type { Catalog, Run } from "./types";
import type { ProgressState, TaskProgressView } from "../workspace/progress";

export interface Config {
  destination_mode?: "excel" | "tally" | "both";
  depth: "client_context";
  ai_context?: boolean;
  excel_source_ids: string[];
  tally: { port: number; period: { from: string; to: string } } | null;
}
export interface MasterSummary {
  exported_count: number;
  unique_count: number;
  duplicate_count: number;
  metadata_count: number;
  counts_by_type: Record<string, number>;
}
interface Collection {
  category: string;
  status: string;
  count?: number;
  error?: string;
}
interface NativeRecords extends Omit<Collection, "category"> {
  records?: { type: string; data: Record<string, unknown> }[];
}
export interface Book {
  path: string;
  file_id?: string;
  status: string;
  error?: string;
  structure?: { sheets: { sheet: string; columns: number; tables: { name: string }[] }[] };
}
export interface DiscoveredSource {
  key: string;
  tool: string;
  label?: string;
  status: string;
  error?: string;
  workbooks?: Book[];
  snapshot?: {
    company?: string;
    collections?: Collection[];
    scope_error?: string;
    companies?: {
      company: string;
      company_guid?: string;
      status: string;
      error?: string;
      master_summary?: MasterSummary;
      master_lookup_error?: string;
      masters?: NativeRecords;
      vouchers?: NativeRecords;
    }[];
  };
}
export interface CollectionProgress {
  completed: number;
  total: number;
  activity: string;
  item?: string;
}
export interface DiscoveryRun {
  id: string;
  task_id: string;
  device_id: string;
  config: Config;
  state: string;
  ready: boolean;
  observations: { key: string; status: string; category?: string; progress?: CollectionProgress }[];
  mapping_run: Run | null;
  /** Optional AI context analysis failed for a Tally-only collection. */
  analysis_failed?: boolean;
  catalog: {
    context_error?: string;
    context_notes?: { company_guid: string; observation: string; certainty: string; evidence_ids: string[] }[];
    partial: boolean;
    sources: DiscoveredSource[];
    review: { status: string; reused_from: string | null };
    excel_mappings: Catalog | null;
  } | null;
}
export const masterLabels: Record<string, string> = {
  LEDGER: "Ledgers", GROUP: "Groups", VOUCHERTYPE: "Voucher types",
  STOCKITEM: "Stock items", STOCKGROUP: "Stock groups", STOCKCATEGORY: "Stock categories",
  UNIT: "Units", GODOWN: "Godowns", CURRENCY: "Currencies", COSTCATEGORY: "Cost categories",
  COSTCENTRE: "Cost centres", TAXUNIT: "Tax units",
  INCOMETAXCLASSIFICATION: "Income-tax classifications", INCOMETAXSLAB: "Income-tax slabs"
};
export const masterLabel = (type: string) => masterLabels[type] ?? type.replaceAll("_", " ");
export interface SourceSummary {
  key: string;
  tool: string;
  label: string;
  status: string;
  error?: string;
  collections: (Collection & { label: string; counts?: Record<string, number>; summary?: MasterSummary })[];
  workbooks: Book[];
}

/** Presentation only: never deduplicate records or reinterpret native identities here. */
export function discoverySources(run: DiscoveryRun): SourceSummary[] {
  const sources = run.catalog?.sources ?? [
    ...run.config.excel_source_ids.map(key => ({ key, tool: "excel", status: "waiting" })),
    ...(run.config.tally ? [{ key: "tally", tool: "tally", status: "waiting" }] : [])
  ] as DiscoveredSource[];
  return sources.flatMap<SourceSummary>(source => {
    if (source.snapshot?.companies) return source.snapshot.companies.map((company, index) => {
      const summary = company.master_summary;
      const counts: Record<string, number> = {};
      if (!summary) for (const record of company.masters?.records ?? []) counts[record.type] = (counts[record.type] ?? 0) + 1;
      const masterStatus = company.master_lookup_error ? "unavailable" : company.masters?.status ?? "unavailable";
      const voucherStatus = company.vouchers?.status ?? "unavailable";
      return {
        key: `${source.key}:${company.company_guid ?? index}`, tool: "tally", label: company.company,
        status: masterStatus !== "ready" || voucherStatus !== "ready" ? "unavailable" : company.status,
        error: company.master_lookup_error ?? company.error,
        collections: [
          { category: "masters", label: summary ? "Unique masters" : "Exported masters", status: masterStatus,
            count: summary?.unique_count ?? company.masters?.count, counts: summary?.counts_by_type ?? counts, summary },
          { category: "vouchers", label: "Vouchers", status: voucherStatus, count: company.vouchers?.count }
        ], workbooks: []
      };
    });
    const observed = run.observations.filter(o => o.key === source.key && !o.category).at(-1);
    const hasCompanyActivity = run.observations.some(o => o.key === source.key && o.category);
    const status = source.status === "waiting" ? run.state === "failed" ? "unavailable" : observed?.status ?? (hasCompanyActivity ? "reading" : "waiting") : source.status;
    return [{ key: source.key, tool: source.tool,
      label: source.label ?? source.snapshot?.company ?? (source.tool === "tally" ? "Companies open in Tally" : "Excel folder"),
      status: source.workbooks?.some(b => b.status !== "ready") ? "unavailable" : status,
      error: source.error, workbooks: source.workbooks ?? [],
      collections: (source.snapshot?.collections ?? []).map(collection => ({
        category: collection.category, count: collection.count, status: collection.status, error: collection.error,
        label: collection.category === "masters" ? "Exported masters" : collection.category === "vouchers" ? "Vouchers" : collection.category
      }))
    }];
  });
}

export function sourcePage(sources: SourceSummary[], query: string, page: number, size = 8) {
  const filtered = sources.filter(source => source.label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  const current = Math.max(0, Math.min(page, pages - 1));
  return { items: filtered.slice(current * size, (current + 1) * size), total: filtered.length, pages, current };
}

/** A phase meter measures native reads/workbooks, never elapsed time or AI work. */
export function discoveryProgress(run: DiscoveryRun): TaskProgressView {
  const partial = Boolean(run.catalog?.partial);
  const failed = run.state === "failed";
  const finished = run.ready && !failed && !partial;
  const review = run.state === "review";
  const native = !run.catalog;
  const latest = run.observations.at(-1);
  if (["paused", "stopped"].includes(run.state)) {
    const current = run.catalog && !run.catalog.partial ? 2 : run.observations.length ? 1 : 0;
    return { stages: ["Get ready", run.catalog && run.config.ai_context !== false ? "Analyze context" : "Collect sources", "Review sources", "Finished"],
      states: [0, 1, 2, 3].map(i => i < current ? "done" : i > current ? "upcoming" : run.state === "paused" ? "waiting" : "failed"),
      current, finished: false, running: false, percent: null, label: run.state === "paused" ? "Paused" : "Stopped",
      meterLabel: "Source discovery", activity: run.state === "paused" ? "Resume to continue. An operation already underway may finish." : "Remaining work stopped. Completed saves remain." };
  }
  const measured = latest?.progress;
  const current = finished ? 3 : partial || failed ? 1 : review || run.state === "completed" ? 2 : native && run.state === "queued" ? 0 : 1;
  const running = !finished && !partial && !failed && !review && run.state !== "completed";
  const waiting = running && run.state === "queued";
  const states: ProgressState[] = ["upcoming", "upcoming", "upcoming", "upcoming"];
  for (let i = 0; i < current; i++) states[i] = "done";
  states[current] = finished ? "done" : failed ? "failed" : partial || review || !running ? "attention" : waiting ? "waiting" : "active";
  const hasMeasure = native && !failed && !partial && measured && Number.isSafeInteger(measured.total) && measured.total > 0 && Number.isSafeInteger(measured.completed) && measured.completed >= 0 && measured.completed <= measured.total;
  const percent = finished ? 100 : hasMeasure ? Math.round(measured.completed / measured.total * 100) : null;
  const activity = finished ? "Sources confirmed and saved" : failed ? "Discovery stopped. Check the sources and run again."
    : partial ? "Collected results are saved. Resolve unavailable sources, then run again."
      : review ? "Check the results below, then confirm sources"
        : run.state === "completed" ? "This catalog is not confirmed for reuse"
          : !native ? waiting ? "Waiting to check context and mappings" : "Source collection finished. Analyzing client context and mappings before review."
            : measured ? [measured.activity, measured.item].filter(Boolean).join(" · ")
              : latest ? `${latest.status === "ready" ? "Collected" : latest.status === "unavailable" ? "Source needs attention" : "Reading"} · ${latest.category ?? (latest.key === "tally" ? "Tally" : "Excel folder")}`
                : "Keep Minkops open on the selected PC. This page updates automatically.";
  return {
    stages: ["Get ready", run.catalog && run.config.ai_context !== false ? "Analyze context" : "Collect sources", "Review sources", "Finished"], states, current, finished, running,
    label: finished ? "Finished and checked" : partial || failed ? "Needs attention" : review ? "Ready for your review" : waiting ? native ? "Waiting for your PC" : "Preparing review" : native ? "Collecting your sources" : "Preparing review",
    activity, percent, meterLabel: finished ? "Discovery complete" : native ? "Source collection" : "Context and mapping review",
    countLabel: hasMeasure ? `${measured.completed} of ${measured.total} ${latest?.key === "tally" ? "native reads" : "workbooks"}` : undefined
  };
}

export type SourceMode = "tally" | "excel" | "both";
const SOURCE_MODES: SourceMode[] = ["tally", "excel", "both"];

/** Source choices the workspace enables; a paused saved choice falls back to the first enabled one. */
export function sourceModes(spec: SettingSpec | undefined, saved: unknown) {
  const enabled = spec?.["x-enabled-options"];
  const modes = SOURCE_MODES.filter((mode) => !enabled || enabled.includes(mode));
  return { modes, selected: modes.find((mode) => mode === saved) ?? modes[0] };
}

/** Complete sources can be confirmed once mappings are ready, or without notes after a failed analysis. */
export function canConfirm(run: DiscoveryRun, mappingsReady: boolean) {
  return run.state === "review" && Boolean(run.catalog) && !run.catalog?.partial
    && (!run.mapping_run || mappingsReady || Boolean(run.analysis_failed));
}
