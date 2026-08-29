import { useState } from "react";
import { Archive, ArrowRight, BookOpen, Check, CheckCircle, ClipboardText, Cube, FileText, Gear, ShieldCheck, Sparkle, UsersThree, X } from "@phosphor-icons/react";

const agents = [
  ["Kall", "Customer Ops", "kall.png"], ["Sera", "Billing Ops", "sera.png"], ["Vale", "Fraud Ops", "vale.png"], ["Niko", "Logistics Ops", "niko.png"], ["Ivo", "Data Ops", "ivo.png"],
];
const evidence = [[FileText,"Customer request","Refund request #8421 · May 19, 2025"],[Cube,"Return received","Delivered · May 18, 2025"],[Archive,"Customer messages","3 messages · May 17–19, 2025"],[ShieldCheck,"Refund policy","Section 4.2 · Returns within 30 days"]];

export function App() {
  const [selected, setSelected] = useState("Kall");
  const [page, setPage] = useState("ledger");
  const [open, setOpen] = useState(true);
  const [outcome, setOutcome] = useState("pending");
  const [notice, setNotice] = useState("");
  const decide = (value) => { setOutcome(value); setNotice(value === "approved" ? "Refund approved — Mira will issue payment." : "Changes requested from Kall."); };
  return <main className="frame">
    <aside className="side"><div className="brand"><Sparkle weight="fill" size={22}/><span>Minkops</span></div>
      <nav>{[["Overview",ClipboardText,"system"],["Decision ledger",BookOpen,"ledger"],["Agents",UsersThree,"agents"],["Policies",ShieldCheck,"policies"]].map(([label,Icon,id])=><button key={id} className={page===id?"on":""} onClick={()=>setPage(id)}><Icon size={18}/>{label}</button>)}</nav>
      <p className="label">Active agents</p><div className="agent-list">{agents.map(([name,role,image])=><button className={selected===name?"agent selected":"agent"} onClick={()=>setSelected(name)} key={name}><img src={`/agents/${image}`} alt=""/><span><b>{name}</b><small><i/> {role}</small></span></button>)}</div>
      <footer><span className="operator">AQ</span><span><b>Avery Quinn</b><small>Operator</small></span></footer>
    </aside>
    {page === "ledger" ? (
      <Ledger outcome={outcome} open={open} setOpen={setOpen} decide={decide} notice={notice} clearNotice={()=>setNotice("")}/>
    ) : (
      <SystemReview page={page} setPage={setPage}/>
    )}
  </main>;
}

function Ledger({ outcome, open, setOpen, decide, notice, clearNotice }) {
  const state = outcome === "approved" ? "Approved" : outcome === "changes" ? "Changes requested" : "Awaiting approval";
  return <><section className="ledger"><header><div><h1>Decision ledger</h1><p>Chronological record of agent decisions and operator actions.</p></div><span className="health"><i/>All systems normal</span></header>
    {notice && <div className="toast" role="status"><CheckCircle weight="fill" size={17}/>{notice}<button onClick={clearNotice}><X size={15}/></button></div>}
    <div className="date"><b>May 20, 2025</b><span><i/>Live</span></div>
    <article className="event current"><time>9:41 AM</time><em/><div className="event-body"><div className="event-title"><img src="/agents/kall.png" alt=""/><span><b>Kall evaluated a refund request</b><small>Refund request #8421</small></span><mark className={outcome}>{state}</mark></div><div className="decision"><p className="label">Decision</p><h2>Approve full refund</h2><p>Reason: Item not as described and returned within policy window.</p><p className="label evidence-head">Evidence (4)</p><div className="evidence">{evidence.map(([Icon,title,sub])=><button key={title}><span className="icon"><Icon size={17}/></span><span><b>{title}</b><small>{sub}</small></span><ArrowRight size={15}/></button>)}</div><p className="label impact-head">Impact</p><dl><div><dt>Refund amount</dt><dd>$89.00</dd></div><div><dt>Customer</dt><dd>Jordan Lee · jordan.lee@example.com</dd></div></dl></div></div></article>
    <Mini time="9:32 AM" image="kall.png" title="Kall requested additional information" sub="Order #77391"/><Mini time="9:21 AM" image="kall.png" title="Kall closed a support case" sub={'Case #6592 · “Delivery update”'}/><Mini time="9:08 AM" image="sera.png" title="Sera updated payment method" sub="Customer Jordan Smith" muted/><div className="end">End of ledger</div>
  </section>
  <aside className={open?"approval":"approval hidden"}><button className="close" onClick={()=>setOpen(false)}><X size={20}/></button><div className="approval-agent"><img src="/agents/kall.png" alt="Kall"/><span><b>Kall</b><small>Customer Ops</small><small><i/>Active</small></span></div><p className="label">Refund request</p><h2>Refund request #8421</h2><dl className="summary">{[["Customer","Jordan Lee"],["Order","#77391"],["Requested","May 19, 2025"],["Amount","$89.00"],["Reason","Item not as described"]].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl><div className="approval-decision"><p className="label">Decision</p><b>Approve full refund</b><p>Item not as described and returned within policy window.</p></div><div className="checks"><p className="label">Checks</p>{["Policy eligible","No fraud signals","Prior refunds: none"].map(x=><span key={x}><CheckCircle weight="fill" size={16}/>{x}</span>)}</div><div className="actions"><button className="primary" disabled={outcome==="approved"} onClick={()=>decide("approved")}><Check weight="bold" size={17}/>{outcome==="approved"?"Refund approved":"Approve refund"}</button><button onClick={()=>decide("changes")}>Request changes</button></div></aside>
  {!open && <button className="review" onClick={()=>setOpen(true)}>Review decision <ArrowRight size={16}/></button>}</>;
}

function Mini({time,image,title,sub,muted}) { return <article className={muted?"event mini muted":"event mini"}><time>{time}</time><em/><div className="event-body"><div className="event-title"><img src={`/agents/${image}`} alt=""/><span><b>{title}</b><small>{sub}</small></span><mark className="resolved"><Check size={12}/>Resolved</mark></div></div></article>; }

function SystemReview({page,setPage}) { const title = page === "agents" ? "Agent identity" : page === "policies" ? "Policy components" : "Minkops system"; return <section className="system"><header><div><h1>{title}</h1><p>Production-ready foundation for thoughtful autonomous operations.</p></div><span className="release">v1.0 · Review ready</span></header><div className="system-grid"><section><p className="label">Color roles</p><div className="swatches"><span/><span/><span/><span/><span/></div><p>Warm parchment, ink, terracotta action, olive success, and considered plum accents.</p></section><section><p className="label">Actions</p><div className="demo-actions"><button className="primary">Primary action</button><button>Secondary action</button></div><p>One decisive action per region, with an explicit secondary path.</p></section><section><p className="label">Status</p><div className="status-row"><mark className="resolved">Resolved</mark><mark>Awaiting approval</mark><mark className="changes">Changes requested</mark></div><p>Status is always paired with a clear label, never color alone.</p></section><section><p className="label">Surfaces</p><div className="surface-demo"><span>Canvas</span><b>Decision surface</b></div><p>Paper-like structure, quiet dividers, and elevation only where it helps choices.</p></section></div><button className="back" onClick={()=>setPage("ledger")}>Open the decision ledger <ArrowRight size={16}/></button></section>; }
