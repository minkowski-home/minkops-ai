
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import IndustryCanvas from "./components/IndustryCanvas";
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

// Industry Data
const industriesInfo = [
    {
        id: "indiv",
        name: "Individual",
        role: "Personal Assistant",
        description: "Organize your life with a dedicated personal AI assistant.",
        color: "#FF0080", // Pink
        shape: "sphere"
    },
    {
        id: "fastfood",
        name: "Fast Food",
        role: "Automated Drive-Thru",
        description: "Voice agents that handle orders with speed and accuracy.",
        color: "#FFA500", // Orange
        shape: "box"
    },
    {
        id: "interiordesign",
        name: "Interior Design",
        role: "Style Curator",
        description: "AI that generates moodboards and sources furniture.",
        color: "#7000FF", // Purple
        shape: "torus"
    },
    {
        id: "store",
        name: "Store Owner",
        role: "Inventory Manager",
        description: "Predict stock levels and automate reordering.",
        color: "#00BFFF", // Sky Blue
        shape: "cone"
    },
    {
        id: "custom",
        name: "Custom Set",
        role: "Enterprise Solution",
        description: "Build a custom fleet of agents tailored to your business.",
        color: "#FFD700", // Gold
        shape: "icosahedron"
    }
];

export default function MinkopsLanding() {
    const [viewState, setViewState] = useState<'industry' | 'agents'>('industry');

    // Industry Selection State
    const [selectedIndustryIndex, setSelectedIndustryIndex] = useState(2);
    const selectedIndustry = industriesInfo[selectedIndustryIndex];

    // Agent Selection State
    const [selectedAgentIndex, setSelectedAgentIndex] = useState(2);
    const selectedAgent = agentsInfo[selectedAgentIndex];

    const handleNextSelection = () => {
        if (viewState === 'industry') {
            setSelectedIndustryIndex((prev) => (prev + 1) % industriesInfo.length);
        } else {
            setSelectedAgentIndex((prev) => (prev + 1) % agentsInfo.length);
        }
    };

    const handlePrevSelection = () => {
        if (viewState === 'industry') {
            setSelectedIndustryIndex((prev) => (prev - 1 + industriesInfo.length) % industriesInfo.length);
        } else {
            setSelectedAgentIndex((prev) => (prev - 1 + agentsInfo.length) % agentsInfo.length);
        }
    };

    const handleProceedToAgents = () => {
        setViewState('agents');
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
                        <span>Scroll to Explore {viewState === 'industry' ? 'Industries' : 'Agents'}</span>
                        <div className="arrow-down"></div>
                    </div>
                </section>

                {/* 3D Selector Section (Industry or Agent) */}
                <section id="agents" className="agents-section">
                    <AnimatePresence mode="wait">
                        {viewState === 'industry' ? (
                            <motion.div
                                key="industry-view"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0, x: -50 }}
                                transition={{ duration: 0.5 }}
                                className="selection-container"
                                style={{ width: '100%' }}
                            >
                                <div className="canvas-wrapper">
                                    <IndustryCanvas
                                        industries={industriesInfo}
                                        selectedIndex={selectedIndustryIndex}
                                        onSelect={setSelectedIndustryIndex}
                                    />
                                </div>

                                <div className="agent-controls">
                                    <div className="nav-arrow nav-prev" onClick={handlePrevSelection}>
                                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M15 19L8 12L15 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                        </svg>
                                    </div>

                                    <div className="agent-info-overlay">
                                        <span className="agent-name" style={{ backgroundImage: `linear-gradient(45deg, #333, ${selectedIndustry.color})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                                            {selectedIndustry.name}
                                        </span>
                                        <p className="agent-desc">{selectedIndustry.description}</p>

                                        <div style={{ marginTop: '1.5rem', pointerEvents: 'auto' }}>
                                            <button className="cta-button" onClick={handleProceedToAgents}>
                                                Explore Agents
                                            </button>
                                        </div>
                                    </div>

                                    <div className="nav-arrow nav-next" onClick={handleNextSelection}>
                                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M9 5L16 12L9 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                        </svg>
                                    </div>
                                </div>
                            </motion.div>
                        ) : (
                            <motion.div
                                key="agent-view"
                                initial={{ opacity: 0, x: 50 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ duration: 0.5 }}
                                className="selection-container"
                                style={{ width: '100%' }}
                            >
                                <div className="canvas-wrapper">
                                    <AgentCanvas
                                        agents={agentsInfo}
                                        selectedIndex={selectedAgentIndex}
                                        onSelect={setSelectedAgentIndex}
                                    />
                                </div>

                                <div className="agent-controls">
                                    <div className="nav-arrow nav-prev" onClick={handlePrevSelection}>
                                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M15 19L8 12L15 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                        </svg>
                                    </div>

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

                                    <div className="nav-arrow nav-next" onClick={handleNextSelection}>
                                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M9 5L16 12L9 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                        </svg>
                                    </div>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </section>

                {/* Demo Video Section - Only for Agents */}
                <AnimatePresence>
                    {viewState === 'agents' && (
                        <motion.section
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            className="demo-section"
                        >
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
                        </motion.section>
                    )}
                </AnimatePresence>

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
