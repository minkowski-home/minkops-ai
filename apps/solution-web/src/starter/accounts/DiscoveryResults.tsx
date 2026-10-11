import { useState } from "react";
import { Icon } from "../console/Icon";
import { Spinner } from "../components/Feedback";
import { discoverySources, masterLabel, sourcePage, type DiscoveryRun, type SourceSummary } from "./discoveryView";

const statusLabels: Record<string, string> = { ready: "Collected", reading: "Reading", waiting: "Waiting for PC", unavailable: "Needs attention" };
const number = (value: number | undefined) => value == null ? "—" : value.toLocaleString();

function SourceRow({ source, controlled }: { source: SourceSummary; controlled: boolean }) {
  const masters = source.collections.find(c => c.category === "masters");
  const vouchers = source.collections.find(c => c.category === "vouchers");
  const types = Object.entries(masters?.counts ?? {}).sort(([a], [b]) => a.localeCompare(b));
  const priority = (type: string) => type === "LEDGER" ? 2 : type === "STOCKITEM" ? 1 : 0;
  const preview = [...types].sort((a, b) => priority(b[0]) - priority(a[0]) || b[1] - a[1]).slice(0, 2);
  return <details className="discovery-company">
    <summary>
      <span className="discovery-company-name"><strong>{source.label}</strong>
        <small>{source.tool === "tally" ? preview.length ? preview.map(([type, count]) => `${number(count)} ${masterLabel(type).toLowerCase()}`).join(" · ") : "Tally" : "Excel folder"}</small>
      </span>
      <span className="discovery-count"><strong>{number(source.tool === "excel" ? source.workbooks.reduce((sum, book) => sum + (book.structure?.sheets.length ?? 0), 0) : masters?.status === "ready" ? masters.count : undefined)}</strong><small>{source.tool === "excel" ? "sheets" : "masters"}</small></span>
      <span className="discovery-count"><strong>{source.tool === "excel" ? number(source.workbooks.length) : number(vouchers?.status === "ready" ? vouchers.count : undefined)}</strong><small>{source.tool === "excel" ? "workbooks" : "vouchers"}</small></span>
      <span className={`discovery-source-status is-${source.status}`}>
        {source.status === "ready" ? <Icon name="check" size={14} /> : source.status === "reading" && !controlled ? <Spinner /> : source.status === "unavailable" ? <Icon name="bell" size={14} /> : null}
        {controlled && source.status === "reading" ? "Last observed" : statusLabels[source.status] ?? "Needs attention"}
      </span>
      <span className="discovery-row-chevron" aria-hidden="true"><Icon name="chevronRight" size={16} /></span>
    </summary>
    <div className="discovery-company-detail">
      {source.error && <p className="form-message" role="alert">{source.error}</p>}
      {masters && <>
        <h4>{masters.label}</h4>
        {types.length ? <dl className="discovery-type-counts">{types.map(([type, count]) => <div key={type}><dt>{masterLabel(type)}</dt><dd>{number(count)}</dd></div>)}</dl>
          : <p className="quiet-state">{masters.status !== "ready" ? "Master collection needs attention." : masters.count === 0 ? "No masters in this export." : "Counts by type are unavailable in this older catalog."}</p>}
        {masters.summary && <p className="discovery-export-note">{number(masters.summary.exported_count)} exported records · {number(masters.summary.duplicate_count)} duplicates · {number(masters.summary.metadata_count)} metadata records. Counts above include statutory and default masters.</p>}
      </>}
      {source.collections.filter(c => c.category !== "masters").map(collection => <p key={collection.category} className="discovery-collection-note">
        <strong>{collection.label}</strong> · {collection.status === "ready" ? `${number(collection.count)} records` : "Needs attention"}
        {collection.error && <span>{collection.error}</span>}
      </p>)}
      {source.workbooks.map(book => <details className="discovery-workbook" key={book.path}>
        <summary>{book.path}<span>{book.status === "ready" ? `${book.structure?.sheets.length ?? 0} sheets` : "Needs attention"}</span></summary>
        {book.error ? <p role="alert">Source unavailable. Reconnect the original workbook.</p> : book.structure?.sheets.map(sheet => <p key={sheet.sheet}>{sheet.sheet} · {sheet.columns} columns · {sheet.tables.length} named tables</p>)}
      </details>)}
    </div>
  </details>;
}

export function DiscoveryResults({ run }: { run: DiscoveryRun }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const sources = discoverySources(run);
  const visible = sourcePage(sources, query, page);
  const companies = run.catalog?.sources.flatMap(s => s.snapshot?.companies ?? []) ?? [];
  const masterCount = sources.reduce((sum, source) => sum + source.collections.filter(c => c.category === "masters" && c.status === "ready").reduce((n, c) => n + (c.count ?? 0), 0), 0);
  const voucherCount = sources.reduce((sum, source) => sum + source.collections.filter(c => c.category === "vouchers" && c.status === "ready").reduce((n, c) => n + (c.count ?? 0), 0), 0);
  const workbookCount = sources.reduce((sum, source) => sum + source.workbooks.filter(book => book.status === "ready").length, 0);
  return <>
    {run.catalog && <dl className="discovery-totals" aria-label="Collected totals">
      {run.config.tally && <><div><dt>Companies found</dt><dd>{number(companies.length || run.catalog.sources.filter(s => s.tool === "tally" && s.snapshot?.company).length)}</dd></div>
        <div><dt>Collected masters</dt><dd>{number(masterCount)}</dd></div><div><dt>Collected vouchers</dt><dd>{number(voucherCount)}</dd></div></>}
      {run.config.excel_source_ids.length > 0 && <div><dt>Collected workbooks</dt><dd>{number(workbookCount)}</dd></div>}
    </dl>}
    {sources.length > 5 && <div className="discovery-list-controls">
      <label className="config-field">Find a company or folder<input type="search" value={query} placeholder="Search sources" onChange={event => { setQuery(event.target.value); setPage(0); }} /></label>
      <span role="status">{visible.total} of {sources.length} sources</span>
    </div>}
    <div className="discovery-company-list" aria-label="Sources by company or folder">
      {visible.items.map(source => <SourceRow key={source.key} source={source} controlled={["paused", "stopped"].includes(run.state)} />)}
      {!visible.items.length && <p className="quiet-state">{query ? "No sources match your search." : "No sources were collected."}</p>}
    </div>
    {visible.pages > 1 && <nav className="discovery-pagination" aria-label="Source pages">
      <span>Page {visible.current + 1} of {visible.pages}</span>
      <button className="button button-ghost" disabled={visible.current === 0} onClick={() => setPage(visible.current - 1)}>Previous</button>
      <button className="button button-ghost" disabled={visible.current === visible.pages - 1} onClick={() => setPage(visible.current + 1)}>Next</button>
    </nav>}
  </>;
}
