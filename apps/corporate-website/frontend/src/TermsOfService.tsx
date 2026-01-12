import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import "./App.css";

export default function TermsOfService() {
    return (
        <div className="minkops-bg">
            <nav className="glass-nav">
                <Link to="/" className="nav-logo">Minkops</Link>
                <div className="nav-links">
                    <Link to="/">Home</Link>
                    <Link to="/about">About</Link>
                    <Link to="/careers">Careers</Link>
                    <Link to="/" className="cta-button">Get Access</Link>
                </div>
            </nav>

            <main style={{ paddingTop: "8rem", paddingBottom: "4rem", minHeight: "100vh" }}>
                <div style={{ maxWidth: "900px", margin: "0 auto", padding: "0 2rem" }}>
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.8 }}
                    >
                        <h1 style={{ fontSize: "3rem", marginBottom: "2rem", fontWeight: "700" }}>Terms of Service</h1>

                        <div style={{
                            background: "var(--glass-bg)",
                            backdropFilter: "blur(12px)",
                            border: "1px solid var(--glass-border)",
                            borderRadius: "24px",
                            padding: "3rem"
                        }}>
                            <section style={{ marginBottom: "2rem" }}>
                                <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>1. Acceptance of Terms</h2>
                                <p style={{ color: "var(--text-muted)", lineHeight: "1.6" }}>
                                    By accessing and using Minkops, a product of Minkowski Home, you accept and agree to be bound by the terms and provision of this agreement.
                                </p>
                            </section>

                            <section style={{ marginBottom: "2rem" }}>
                                <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>2. Use of Service</h2>
                                <p style={{ color: "var(--text-muted)", lineHeight: "1.6" }}>
                                    Our AI agents are designed to assist with business operations. You agree to use these agents responsibly and in compliance with all applicable laws and regulations.
                                </p>
                            </section>

                            <section style={{ marginBottom: "2rem" }}>
                                <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>3. Data & Privacy</h2>
                                <p style={{ color: "var(--text-muted)", lineHeight: "1.6" }}>
                                    We respect your data. Your interaction with our agents is encrypted and governed by our Privacy Policy.
                                </p>
                            </section>

                            <section style={{ marginBottom: "2rem" }}>
                                <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>4. Contact Information</h2>
                                <p style={{ color: "var(--text-muted)", lineHeight: "1.6" }}>
                                    For any questions regarding these Terms, please contact us at <a href="mailto:info@minkowskihome.com" style={{ color: "var(--primary-glow)" }}>info@minkowskihome.com</a>.
                                </p>
                            </section>
                        </div>
                    </motion.div>
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
