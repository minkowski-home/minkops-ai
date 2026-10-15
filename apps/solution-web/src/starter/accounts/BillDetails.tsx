import { useRef } from "react";
import { billDetails } from "./billView";
import type { BillRecord } from "./types";

/** A read-only card of what a proposal enters in Tally. Decisions stay on the bill. */
export function BillDetailsButton({ record, config, name }: { record: BillRecord; config: Record<string, unknown>; name: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const details = billDetails(record, config);
  return <>
    <button className="button button-ghost" onClick={() => dialog.current?.showModal()}>Show details</button>
    {/* A native modal dialog: Escape closes it and focus returns to the button. */}
    <dialog ref={dialog} className="bill-details" aria-label={`Details for ${name}`}>
      <header><h4>{details.title}</h4><p className="quiet-state">{name}</p></header>
      <dl>{details.rows.map(([label, value], index) => <div key={index}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <button className="button button-ghost" onClick={() => dialog.current?.close()}>Close</button>
    </dialog>
  </>;
}
