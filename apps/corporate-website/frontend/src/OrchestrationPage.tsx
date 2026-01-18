import { Link } from "react-router-dom";
import { motion } from "framer-motion";

export default function OrchestrationPage() {
    return (
        <div className="minkops-bg">
            <nav className="glass-nav">
                <Link to="/" className="nav-logo">Minkops</Link>
                <div className="nav-links">
                    <Link to="/">Home</Link>
                    <Link to="/about">About</Link>
                    <a href="/#access" className="cta-button">Get Access</a>
                </div>
            </nav>

            <main style={{ paddingTop: "120px", paddingBottom: "4rem", minHeight: "100vh" }}>
                <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "0 2rem" }}>
                    <motion.div
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.8 }}
                        style={{ textAlign: "center", marginBottom: "5rem" }}
                    >
                        <h1 style={{ fontSize: "3.5rem", fontWeight: "700", marginBottom: "1rem" }}>
                            Orchestrated Intelligence
                        </h1>
                        <p style={{ fontSize: "1.2rem", color: "var(--text-muted)", maxWidth: "700px", margin: "0 auto" }}>
                            Agents simply don't just chat. They work together. See how Minkops orchestrates complex business flows autonomously.
                        </p>
                    </motion.div>

                    {/* Workflow 1: Marketing */}
                    <WorkflowSection
                        title="1. Automated Marketing Campaign"
                        description="From idea to published ad copy without human intervention."
                        align="left"
                    >
                        <FlowChart>
                            <Node agent="Floc" role="Copywriter" color="#ff4500" />
                            <Arrow label="Drafts Copy" />
                            <Node agent="Ora" role="Visual Experience" color="#7000ff" />
                            <Arrow label="Generates Assets" />
                            <Node type="output" label="Published Campaign" color="#000" />
                        </FlowChart>
                    </WorkflowSection>

                    {/* Workflow 2: Social Media */}
                    <WorkflowSection
                        title="2. Intelligent Social Engagement"
                        description="Handling public perception and private support simultaneously."
                        align="right"
                    >
                        <FlowChart>
                            <Node agent="Eko" role="Social Handler" color="#00bfff" />
                            <Arrow label="Detects Complaint" />
                            <Node agent="Kall" role="CS Rep" color="#ff0080" />
                            <Arrow label="Resolves Ticket" />
                            <Node agent="Eko" role="Social Handler" color="#00bfff" />
                        </FlowChart>
                    </WorkflowSection>

                    {/* Workflow 3: Fast Food */}
                    <WorkflowSection
                        title="3. QSR Operations"
                        description="Zero-man fast food store management."
                        align="left"
                    >
                        <FlowChart>
                            <Node agent="Hosi" role="Front of House" color="#ffd700" />
                            <Arrow label="Order Taken" />
                            <Node agent="Cruz" role="Store Manager" color="#111" />
                            <Arrow label="Relays Ticket" />
                            <Node agent="Tony" role="Kitchen Staff" color="#ff4500" />
                        </FlowChart>
                    </WorkflowSection>

                    <div style={{ textAlign: "center", marginTop: "5rem" }}>
                        <Link to="/" className="cta-button large-cta">
                            Build Your Fleet
                        </Link>
                    </div>
                </div>
            </main>
        </div>
    );
}

function WorkflowSection({ title, description, children, align }: { title: string, description: string, children: React.ReactNode, align: 'left' | 'right' }) {
    return (
        <motion.div
            initial={{ opacity: 0, x: align === 'left' ? -50 : 50 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8 }}
            style={{
                marginBottom: "8rem",
                display: "flex",
                flexDirection: "column",
                alignItems: align === 'left' ? 'flex-start' : 'flex-end'
            }}
        >
            <h2 style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>{title}</h2>
            <p style={{ fontSize: "1.1rem", color: "var(--text-muted)", marginBottom: "2rem", maxWidth: "500px", textAlign: align }}>{description}</p>
            <div style={{
                width: "100%",
                background: "rgba(255,255,255,0.4)",
                backdropFilter: "blur(10px)",
                border: "1px solid rgba(0,0,0,0.05)",
                borderRadius: "20px",
                padding: "3rem",
                display: "flex",
                justifyContent: "center"
            }}>
                {children}
            </div>
        </motion.div>
    );
}

function FlowChart({ children }: { children: React.ReactNode }) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap", justifyContent: "center" }}>
            {children}
        </div>
    );
}

function Node({ agent, role, type, label, color }: { agent?: string, role?: string, type?: string, label?: string, color: string }) {
    return (
        <motion.div
            whileHover={{ scale: 1.05, y: -5 }}
            style={{
                width: "160px",
                height: "160px",
                borderRadius: "20px",
                background: type === 'output' ? '#111' : 'rgba(255,255,255,0.8)',
                border: `2px solid ${color}`,
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                alignItems: "center",
                padding: "1rem",
                boxShadow: "0 10px 30px rgba(0,0,0,0.05)",
                textAlign: "center"
            }}
        >
            {type === 'output' ? (
                <span style={{ color: "#fff", fontWeight: "700", fontSize: "1.1rem" }}>{label}</span>
            ) : (
                <>
                    <span style={{ fontSize: "1.5rem", fontWeight: "800", color: color, marginBottom: "0.2rem" }}>{agent}</span>
                    <span style={{ fontSize: "0.9rem", color: "#666", textTransform: "uppercase", letterSpacing: "0.05em" }}>{role}</span>
                </>
            )}
        </motion.div>
    );
}

function Arrow({ label }: { label: string }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", margin: "0 1rem" }}>
            <span style={{ fontSize: "0.8rem", color: "#999", marginBottom: "0.2rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</span>
            <svg width="40" height="12" viewBox="0 0 40 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M0 6L38 6" stroke="#CCC" strokeWidth="2" />
                <path d="M34 1L39 6L34 11" stroke="#CCC" strokeWidth="2" strokeLinecap="round" />
            </svg>
        </div>
    );
}
