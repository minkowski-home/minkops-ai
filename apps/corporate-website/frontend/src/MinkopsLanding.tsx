import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import AgentCanvas from "./components/AgentCanvas";
import "./App.css";

// Real Agent Data from README
// Colors assigned for visual distinction
const agentsInfo = [
    {
        id: "sarah",
        name: "Leed",
        role: "Lead Generation Caller",
        description: "Proactive outreach agent that qualifies leads and schedules meetings immediately.",
        color: "#FF0080", // Pink (Primary)
        priority: "Immediate"
    },
    {
        id: "jaina",
        name: "Kall",
        role: "Customer Support Rep",
        description: "Handles phone calls and tickets with high empathy and perfect policy compliance.",
        color: "#00BFFF", // Sky Blue (Secondary)
        priority: "High"
    },
    {
        id: "ethan",
        name: "Flox",
        role: "Marketing Specialist",
        description: "Generates high-converting ad copy and email campaigns tailored to your brand voice.",
        color: "#7000FF", // Purple
        priority: "High"
    },
    {
        id: "bianca",
        name: "Ora",
        role: "Moodboard Generator",
        description: "Visual agent creates aesthetic moodboards and style guides for interior design.",
        color: "#FFD700", // Gold
        priority: "Moderate"
    },
    {
        id: "ryan",
        name: "Eko",
        role: "Social Media Handler",
        description: "Engages with your audience and manages posting schedules across platforms.",
        color: "#FF4500", // Orange
        priority: "Moderate"
    }
];

export default function MinkopsLanding() {
    const [selectedIndex, setSelectedIndex] = useState(2); // Start with Ethan (index 2) as in sketch

    const selectedAgent = agentsInfo[selectedIndex];

    const handleNext = () => {
        setSelectedIndex((prev) => (prev + 1) % agentsInfo.length);
    };

    const handlePrev = () => {
        setSelectedIndex((prev) => (prev - 1 + agentsInfo.length) % agentsInfo.length);
    };

    return (
        <div className="minkops-bg">
            {/* Navbar */}
            <nav className="glass-nav">
                <div className="nav-logo">Minkops</div>
                <div className="nav-links">
                    <a href="#agents">Agents</a>
                    <a href="#about">About</a>
                    <a href="#contact" className="cta-button">Get Access</a>
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
                        <span>Scroll to Explore</span>
                        <div className="arrow-down"></div>
                    </div>
                </section>

                {/* 3D Agent Selector */}
                <section id="agents" className="agents-section">

                    <div className="canvas-wrapper">
                        {/* Navigation Overlay */}
                        <div className="nav-arrow nav-prev" onClick={handlePrev}>&lt;</div>
                        <div className="nav-arrow nav-next" onClick={handleNext}>&gt;</div>

                        <AgentCanvas
                            agents={agentsInfo}
                            selectedIndex={selectedIndex}
                            onSelect={setSelectedIndex}
                        />
                    </div>

                    {/* Selected Agent Info - Below Canvas as per logic flows better here */}
                    <motion.div
                        key={selectedAgent.id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="agent-info-overlay"
                    >
                        <span className="agent-name" style={{ backgroundImage: `linear-gradient(45deg, #333, ${selectedAgent.color})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                            {selectedAgent.name}
                        </span>
                        <p className="agent-desc">{selectedAgent.role}</p>
                    </motion.div>
                </section>

                {/* Demo Video Section */}
                <section className="demo-section">
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={selectedAgent.id}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.5 }}
                            className="demo-container"
                        >
                            <div className="demo-text">
                                <h3>Meet <span style={{ color: selectedAgent.color }}>{selectedAgent.name}</span></h3>
                                <p>{selectedAgent.description}</p>
                            </div>

                            <div className="video-wrapper">
                                <div className="seamless-video">
                                    {/* In a real app, this would be a <video> tag with autoPlay loop muted */}
                                    <div
                                        className="video-mock"
                                        style={{ background: `linear-gradient(135deg, #f5f5f5 0%, ${selectedAgent.color}20 100%)` }}
                                    >
                                        Video of {selectedAgent.name}
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    </AnimatePresence>
                </section>

                {/* Footer */}
                <footer className="main-footer">
                    <div className="footer-content">
                        <div className="footer-column brand-col">
                            <div className="footer-logo">Minkops</div>
                            <p>Operating system for zero-man companies</p>
                        </div>

                        <div className="footer-column">
                            <h4>Platform</h4>
                            <a href="#agents">Agents</a>
                            <a href="#orchestration">Orchestration</a>
                            <a href="#security">Security</a>
                            <a href="#pricing">Pricing</a>
                        </div>

                        <div className="footer-column">
                            <h4>Company</h4>
                            <a href="/about">About Us</a>
                            <a href="/careers">Careers</a>
                            <a href="/blog">Blog</a>
                            <a href="/contact">Contact</a>
                        </div>

                        <div className="footer-column">
                            <h4>Connect</h4>
                            <a href="https://twitter.com/minkops">Twitter</a>
                            <a href="https://linkedin.com/company/minkops">LinkedIn</a>
                            <a href="https://github.com/minkops">GitHub</a>
                        </div>
                    </div>

                    <div className="footer-bottom">
                        <p>&copy; 2025 Minkops AI Inc. All rights reserved.</p>
                        <div className="legal-links">
                            <a href="/privacy">Privacy Policy</a>
                            <a href="/terms">Terms of Service</a>
                        </div>
                    </div>
                </footer>
            </main>
        </div >
    );
}
