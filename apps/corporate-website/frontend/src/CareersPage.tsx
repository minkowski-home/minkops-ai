import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import "./App.css";

export default function CareersPage() {
    return (
        <div className="minkops-bg">
            <nav className="glass-nav">
                <Link to="/" className="nav-logo">Minkops</Link>
                <div className="nav-links">
                    <Link to="/">Home</Link>
                    <Link to="/about">About</Link>
                    <Link to="/" className="cta-button">Get Access</Link>
                </div>
            </nav>

            <main style={{ paddingTop: "8rem", paddingBottom: "4rem", minHeight: "100vh" }}>
                <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "0 2rem" }}>
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.8 }}
                        style={{ textAlign: "center", marginBottom: "4rem" }}
                    >
                        <h1 style={{ fontSize: "4rem", fontWeight: "700", marginBottom: "1rem" }}>Join the Revolution</h1>
                        <p style={{ fontSize: "1.5rem", color: "var(--text-muted)" }}>Help us build the operating system for zero-man companies.</p>
                    </motion.div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "2rem" }}>
                        {[
                            { title: "Senior AI Engineer", type: "Engineering", location: "Remote" },
                            { title: "Product Designer", type: "Design", location: "Remote" },
                            { title: "Growth Manager", type: "Marketing", location: "Hybrid" }
                        ].map((job, index) => (
                            <motion.div
                                key={index}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: index * 0.1, duration: 0.5 }}
                                style={{
                                    background: "var(--glass-bg)",
                                    backdropFilter: "blur(12px)",
                                    border: "1px solid var(--glass-border)",
                                    borderRadius: "16px",
                                    padding: "2rem",
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "1rem"
                                }}
                            >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <span style={{ fontSize: "0.9rem", color: "var(--primary-glow)", textTransform: "uppercase", letterSpacing: "0.1em" }}>{job.type}</span>
                                    <span style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>{job.location}</span>
                                </div>
                                <h3 style={{ fontSize: "1.5rem", fontWeight: "600" }}>{job.title}</h3>
                                <p style={{ color: "var(--text-muted)" }}>We are looking for a passionate individual to join our world-class team.</p>
                                <a href="mailto:hr@minkowskihome.com" style={{ marginTop: "1rem", display: "inline-block", fontWeight: "500", color: "black", textDecoration: "none" }}>Apply Now →</a>
                            </motion.div>
                        ))}
                    </div>

                    <div style={{ marginTop: "6rem", textAlign: "center" }}>
                        <h2 style={{ fontSize: "2rem", marginBottom: "1rem" }}>Don't see your role?</h2>
                        <p style={{ color: "var(--text-muted)", marginBottom: "2rem" }}>
                            We are always looking for exceptional talent. Send your resume to <a href="mailto:hr@minkowskihome.com" style={{ color: "var(--primary-glow)" }}>hr@minkowskihome.com</a>.
                        </p>
                    </div>
                </div>
            </main>

            <footer className="main-footer">
                <div className="footer-bottom">
                    <p>&copy; 2025 Minkops. A product of Minkowski Home. All rights reserved.</p>
                    <div className="legal-links">
                        <Link to="/privacy">Privacy Policy</Link>
                        <Link to="/terms">Terms of Service</Link>
                    </div>
                </div>
            </footer>
        </div>
    );
}
