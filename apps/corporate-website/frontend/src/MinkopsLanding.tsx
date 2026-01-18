import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import InterestForm from "./components/InterestForm";
import AgentDemoSection from "./components/AgentDemoSection";
import "./App.css";

export default function MinkopsLanding() {
    const handleHomeClick = (e: React.MouseEvent) => {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    return (
        <div className="minkops-bg">
            {/* Navbar */}
            <nav className="glass-nav">
                <div className="nav-logo" onClick={handleHomeClick} style={{ cursor: 'pointer' }}>Minkops</div>
                <div className="nav-links">
                    <a href="#access" onClick={(e) => {
                        e.preventDefault();
                        const element = document.getElementById('access');
                        if (element) element.scrollIntoView({ behavior: 'smooth' });
                    }}>Get Access</a>
                    <Link to="/about">About</Link>
                    <a href="#access" className="cta-button">Get Access</a>
                </div>
            </nav>

            <main>
                {/* Hero Section */}
                <section className="hero-section">
                    <div className="gradient-orb orb-1" />
                    <div className="gradient-orb orb-2" />
                    <motion.div
                        initial={{ opacity: 0, y: 50 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 1 }}
                        className="hero-content"
                    >
                        <h1 className="hero-title">
                            Intelligence <span className="text-gradient">Redefined</span>
                        </h1>
                        <p className="hero-subtitle">
                            Meet the full suite of AI Employees
                            <br />
                            Powering zero-man companies
                        </p>
                    </motion.div>
                    <div className="scroll-indicator">
                        <span>Scroll to Request Access</span>
                        <div className="arrow-down"></div>
                    </div>
                </section>

                {/* Interest Form Section */}
                <section id="access" className="agents-section" style={{ minHeight: '100vh', justifyContent: 'flex-start', paddingTop: '10vh' }}>
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        whileInView={{ opacity: 1, scale: 1 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8 }}
                        style={{ width: '100%' }}
                    >
                        <InterestForm />
                    </motion.div>
                </section>

                {/* Demo Section */}
                <AgentDemoSection />

                {/* Footer */}
                <footer className="main-footer">
                    <div className="footer-content">
                        <div className="footer-column brand-col">
                            <div className="footer-logo">Minkops</div>
                            <p>Operating system for zero-man companies</p>
                        </div>

                        <div className="footer-column">
                            <h4>Platform</h4>
                            <a href="#access">Agents</a>
                            <Link to="/orchestration">Orchestration</Link>
                            <a href="#access">Pricing</a>
                        </div>

                        <div className="footer-column">
                            <h4>Company</h4>
                            <Link to="/about">About Us</Link>
                            <Link to="/careers">Careers</Link>
                            <Link to="/blogs">Blog</Link>
                            <a href="/contact">Contact</a>
                            <a href="https://linkedin.com/company/minkops">LinkedIn</a>
                        </div>
                    </div>

                    <div className="footer-bottom">
                        <p>&copy; 2025 Minkops. A product of Minkowski Home. All rights reserved.</p>
                        <div className="legal-links">
                            <Link to="/privacy">Privacy Policy</Link>
                            <Link to="/terms">Terms of Service</Link>
                        </div>
                    </div>
                </footer>
            </main>
        </div >
    );
}
