import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import PageShell from "./components/PageShell";
import SiteFooter from "./components/SiteFooter";
import SiteNav from "./components/SiteNav";

export default function OrchestrationPage() {
  return (
    <PageShell>
      <SiteNav />

      <main className="page-main">
        <div className="page-container">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            className="orchestration-hero"
          >
            <h1 className="page-title">Orchestrated Intelligence</h1>
            <p className="page-subtitle orchestration-subtitle">
              Agents don&apos;t just chat. They work together. See how Minkops
              orchestrates complex business flows autonomously.
            </p>
          </motion.div>

          <WorkflowSection
            title="1. Automated Marketing Campaign"
            description="From idea to published ad copy without human intervention."
            align="left"
          >
            <FlowChart>
              <Node agent="Floc" agentRole="Copywriter" color="#ff4500" />
              <Arrow label="Drafts Copy" />
              <Node agent="Ora" agentRole="Visual Experience" color="#7000ff" />
              <Arrow label="Generates Assets" />
              <Node type="output" label="Published Campaign" color="#000" />
            </FlowChart>
          </WorkflowSection>

          <WorkflowSection
            title="2. Intelligent Social Engagement"
            description="Handling public perception and private support simultaneously."
            align="right"
          >
            <FlowChart>
              <Node agent="Eko" agentRole="Social Handler" color="#00bfff" />
              <Arrow label="Detects Complaint" />
              <Node agent="Kall" agentRole="CS Rep" color="#ff0080" />
              <Arrow label="Resolves Ticket" />
              <Node agent="Eko" agentRole="Social Handler" color="#00bfff" />
            </FlowChart>
          </WorkflowSection>

          <WorkflowSection
            title="3. QSR Operations"
            description="Zero-man fast food store management."
            align="left"
          >
            <FlowChart>
              <Node agent="Hosi" agentRole="Front of House" color="#ffd700" />
              <Arrow label="Order Taken" />
              <Node agent="Cruz" agentRole="Store Manager" color="#111" />
              <Arrow label="Relays Ticket" />
              <Node agent="Tony" agentRole="Kitchen Staff" color="#ff4500" />
            </FlowChart>
          </WorkflowSection>

          <div className="orchestration-cta">
            <Link to="/" className="cta-button large-cta">
              Build Your Fleet
            </Link>
          </div>
        </div>
      </main>

      <SiteFooter />
    </PageShell>
  );
}

function WorkflowSection({
  title,
  description,
  children,
  align
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  align: "left" | "right";
}) {
  return (
    <motion.section
      initial={{ opacity: 0, x: align === "left" ? -50 : 50 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.8 }}
      className={[
        "workflow-section",
        align === "left" ? "align-left" : "align-right"
      ].join(" ")}
    >
      <h2 className="workflow-title">{title}</h2>
      <p
        className={[
          "workflow-desc",
          align === "left" ? "align-left" : "align-right"
        ].join(" ")}
      >
        {description}
      </p>
      <div className="workflow-card">{children}</div>
    </motion.section>
  );
}

function FlowChart({ children }: { children: React.ReactNode }) {
  return <div className="flowchart">{children}</div>;
}

function Node({
  agent,
  agentRole,
  type,
  label,
  color
}: {
  agent?: string;
  agentRole?: string;
  type?: string;
  label?: string;
  color: string;
}) {
  return (
    <motion.div
      whileHover={{ scale: 1.05, y: -5 }}
      className={["flow-node", type === "output" ? "output" : ""].join(" ")}
      style={{ borderColor: color }}
    >
      {type === "output" ? (
        <span className="flow-output">{label}</span>
      ) : (
        <>
          <span className="flow-agent" style={{ color }}>
            {agent}
          </span>
          <span className="flow-role">{agentRole}</span>
        </>
      )}
    </motion.div>
  );
}

function Arrow({ label }: { label: string }) {
  return (
    <div className="flow-arrow">
      <span className="flow-arrow-label">{label}</span>
      <svg
        className="flow-arrow-icon"
        width="40"
        height="12"
        viewBox="0 0 40 12"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M0 6L38 6" stroke="#CCC" strokeWidth="2" />
        <path d="M34 1L39 6L34 11" stroke="#CCC" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}
