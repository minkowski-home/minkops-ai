import { useRef, useState } from 'react';
import type { Source } from './types';
import { eligibleFiles } from './fileSelection';

export function BillFileSelection({ sources, selected, busy, loading, loadFailed, onRetry, canConnect, onSelect, onUpload, onConnect, onRefresh, onReconnect }: {
  sources: Source[]; selected: string[]; busy: boolean; loading: boolean; loadFailed: boolean; onRetry: () => void; canConnect: boolean;
  onSelect: (ids: string[]) => void; onUpload: (files: FileList | null) => void;
  onConnect: () => void; onRefresh: (source: Source) => void; onReconnect: (source: Source) => void;
}) {
  const [query, setQuery] = useState('');
  const upload = useRef<HTMLInputElement>(null);
  const files = eligibleFiles(sources);
  const visible = files.filter(file => file.path.toLowerCase().includes(query.toLowerCase()));
  const visibleIds = new Set(visible.map(file => file.id));
  function selectMany(ids: string[], checked: boolean) {
    onSelect(checked ? [...new Set([...selected, ...ids])] : selected.filter(id => !ids.includes(id)));
  }
  return <section className="bill-file-selection" aria-label="Bill files">
    <div className="section-heading"><div><h3>Select bills</h3><p>Choose PDFs or images from uploads and connected folders.</p></div>
      <span role="status">{selected.length} of {files.length} selected</span></div>
    <div className="discovery-source-grid">
      <section className="discovery-source-card"><h4>Upload bills</h4><p>Add PDFs, PNG, JPEG or WebP images to this workspace.</p>
        <button className="button button-primary" disabled={busy || loading || loadFailed} onClick={() => upload.current?.click()}>Upload files</button>
        <input ref={upload} hidden aria-label="Upload workflow files" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp" disabled={busy || loading || loadFailed}
          onChange={e => { onUpload(e.target.files); e.target.value = ''; }} /></section>
      <section className="discovery-source-card"><h4>Connected folder</h4><p>Reuse bills from a folder on your PC. Refresh it when files change.</p>
        <button className="button button-ghost" disabled={busy || loading || loadFailed || !canConnect} onClick={onConnect}>Connect local folder</button>
        {!canConnect && <p className="quiet-state">Use the Windows app, Chrome or Edge to connect a folder.</p>}</section>
    </div>
    <div className="bill-selection-toolbar"><label className="config-field">Find a bill<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="File name or path" /></label>
      <button className="button button-ghost" disabled={busy || loading || loadFailed || !visible.length} onClick={() => selectMany(visible.map(file => file.id), true)}>{query ? 'Select results' : 'Select all'}</button>
      <button className="button button-ghost" disabled={busy || loading || loadFailed || !selected.length} onClick={() => onSelect([])}>Clear selection</button></div>
    {loading ? <p role="status">Loading bill files…</p> : loadFailed ? <div><p role="status">Bill files could not be loaded.</p><button className="button button-ghost" disabled={busy} onClick={onRetry}>Retry loading files</button></div> : !files.length ? <p className="quiet-state">No supported bills yet. Upload files or connect a folder to begin.</p> : !visible.length ? <p role="status">No bills match your search.</p> : sources.map(source => {
      const all = eligibleFiles([source]);
      const shown = all.filter(file => visibleIds.has(file.id));
      if (!shown.length) return null;
      const count = all.filter(file => selected.includes(file.id)).length;
      return <details className="bill-source" key={source.id} open>
        <summary><span>{source.label}</span><small>{source.writable ? 'Connected folder' : 'Uploaded files'} · {count} of {all.length} selected</small></summary>
        <div className="accounts-toolbar"><button className="button button-ghost" disabled={busy} onClick={() => selectMany(shown.map(file => file.id), !shown.every(file => selected.includes(file.id)))}>{shown.every(file => selected.includes(file.id)) ? 'Clear group' : 'Select group'}</button>
          {source.writable && <><button className="button button-ghost" disabled={busy} onClick={() => onRefresh(source)}>Refresh folder</button>
            <button className="button button-ghost" disabled={busy || !canConnect} onClick={() => onReconnect(source)}>Reconnect folder</button></>}</div>
        <div className="bill-file-list">{shown.map(file => <label className="bill-file-row" key={file.id}>
          <input type="checkbox" disabled={busy} checked={selected.includes(file.id)} onChange={e => selectMany([file.id], e.target.checked)} />
          <span>{file.path}</span><small>{file.path.split('.').pop()?.toUpperCase()}</small></label>)}</div>
      </details>;
    })}
    <p className="quiet-state">Selections are remembered in this browser. Newly added files stay unchecked after a refresh.</p>
  </section>;
}
