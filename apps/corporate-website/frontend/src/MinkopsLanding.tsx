
import { useState, useMemo, useEffect } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import IndustryCanvas from "./components/IndustryCanvas";
import AgentCanvas from "./components/AgentCanvas";
import "./App.css";

// Real Agent Data from README with Industry Mapping
// Mapping:
// indiv -> generic
// fastfood -> fastfood
// interiordesign -> interiordesign
// store -> store
const agentsInfo = [
    {
        id: "sarah",
        name: "Leed",
        role: "Lead Generation Caller",
        description: "Proactive outreach agent that qualifies leads and schedules meetings immediately.",
        color: "#FF0080", // Pink (Primary)
        priority: "Immediate",
        industry: "generic"
    },
    {
        id: "jaina",
        name: "Kall",
        role: "Customer Support Rep",
        description: "Handles phone calls and tickets with high empathy and perfect policy compliance.",
        color: "#00BFFF", // Sky Blue (Secondary)
        priority: "High",
        industry: "generic"
    },
    {
        id: "ethan",
        name: "Flox",
        role: "Marketing Specialist",
        description: "Generates high-converting ad copy and email campaigns tailored to your brand voice.",
        color: "#7000FF", // Purple
        priority: "High",
        industry: "generic"
    },
    {
        id: "nathan",
        name: "Imel",
        role: "Email Handler",
        description: "Manages inbox, drafts responses, and organizes communication threads.",
        color: "#FFA500", // Orange
        priority: "Immediate",
        industry: "generic"
    },
    {
        id: "ryan",
        name: "Eko",
        role: "Social Media Handler",
        description: "Engages with your audience and manages posting schedules across platforms.",
        color: "#FF4500", // Red-Orange
        priority: "Moderate",
        industry: "generic"
    },
    {
        id: "bianca",
        name: "Ora",
        role: "Moodboard Generator",
        description: "Visual agent creates aesthetic moodboards and style guides for interior design.",
        color: "#FFD700", // Gold
        priority: "Moderate",
        industry: "interiordesign"
    },
    {
        id: "devin",
        name: "Cruz",
        role: "Manager's Assistant",
        description: "Assists with shift scheduling, inventory checks, and team communication.",
        color: "#20B2AA", // Light Sea Green
        priority: "Very Low",
        industry: "fastfood"
    },
    {
        id: "emily",
        name: "Hosi",
        role: "Front of House",
        description: "Manages reservations, guest greeting, and seating arrangements.",
        color: "#FF69B4", // Hot Pink
        priority: "Very Low",
        industry: "fastfood"
    },
    {
        id: "tony",
        name: "Prex",
        role: "Back of House",
        description: "Monitors kitchen workflow, order tickets, and prep stations.",
        color: "#8B0000", // Dark Red
        priority: "Very Low",
        industry: "fastfood"
    },
    {
        id: "kim",
        name: "Opi",
        role: "Store Manager's Assistant",
        description: "Helps with daily store operations, reporting, and staff coordination.",
        color: "#4682B4", // Steel Blue
        priority: "Low",
        industry: "store"
    },
    {
        id: "mark",
        name: "Insy",
        role: "Business Analyst",
        description: "Analyzes sales data and market trends to provide actionable insights.",
        color: "#2E8B57", // Sea Green
        priority: "Low",
        industry: "store" // Generic/Store fit
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
        shape: "person",
        filterKey: "generic"
    },
    {
        id: "fastfood",
        name: "Fast Food",
        role: "Automated Drive-Thru",
        description: "Voice agents that handle orders with speed and accuracy.",
        color: "#FFA500", // Orange
        shape: "burger",
        filterKey: "fastfood"
    },
    {
        id: "interiordesign",
        name: "Interior Design",
        role: "Style Curator",
        description: "AI that generates moodboards and sources furniture.",
        color: "#7000FF", // Purple
        shape: "chair",
        filterKey: "interiordesign"
    },
    {
        id: "store",
        name: "Store Owner",
        role: "Inventory Manager",
        description: "Predict stock levels and automate reordering.",
        color: "#00BFFF", // Sky Blue
        shape: "store",
        filterKey: "store"
    },
    {
        id: "custom",
        name: "Custom Set",
        role: "Enterprise Solution",
        description: "Build a custom fleet of agents tailored to your business.",
        color: "#FFD700", // Gold
        shape: "custom",
        filterKey: "all"
    },
    {
        id: "researcher",
        name: "Researcher",
        role: "Market Analyst",
        description: "Deep dive into market trends, competitor analysis, and data synthesis.",
        color: "#00CED1", // Dark Turquoise
        shape: "researcher",
        filterKey: "generic"
    }
];

export default function MinkopsLanding() {
    const [viewState, setViewState] = useState<'industry' | 'agents'>('industry');

    // Industry Selection State
    const [selectedIndustryIndex, setSelectedIndustryIndex] = useState(2);
    const selectedIndustry = industriesInfo[selectedIndustryIndex];

    // Filter Agents based on selected Industry
    const filteredAgents = useMemo(() => {
        const filter = selectedIndustry.filterKey;
        if (filter === "all") return agentsInfo;

        // For specific industries, show industry-specific AND generic agents
        // For 'generic' (Individual), show only generic
        if (filter === "generic") {
            return agentsInfo.filter(a => a.industry === "generic");
        }

        return agentsInfo.filter(a => a.industry === filter || a.industry === "generic");
    }, [selectedIndustry]);

    // Agent Selection State
    const [selectedAgentIndex, setSelectedAgentIndex] = useState(0);
    const selectedAgent = filteredAgents[selectedAgentIndex] || filteredAgents[0];

    // Reset agent selection when industry changes
    useEffect(() => {
        setSelectedAgentIndex(0);
    }, [selectedIndustryIndex]);

    const handleNextSelection = () => {
        if (viewState === 'industry') {
            setSelectedIndustryIndex((prev) => (prev + 1) % industriesInfo.length);
        } else {
            setSelectedAgentIndex((prev) => (prev + 1) % filteredAgents.length);
        }
    };

    const handlePrevSelection = () => {
        if (viewState === 'industry') {
            setSelectedIndustryIndex((prev) => (prev - 1 + industriesInfo.length) % industriesInfo.length);
        } else {
            setSelectedAgentIndex((prev) => (prev - 1 + filteredAgents.length) % filteredAgents.length);
        }
    };

    const handleProceedToAgents = () => {
        setViewState('agents');
    };

    const handleBackToIndustries = () => {
        setViewState('industry');
    };

    const handleHomeClick = (e: React.MouseEvent) => {
        e.preventDefault();
        setViewState('industry');
        // Optional: scroll to top if needed, but current single page design fits within viewport mostly
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    return (
        <div className="minkops-bg">
            {/* Navbar */}
            <nav className="glass-nav">
                <div className="nav-logo" onClick={handleHomeClick} style={{ cursor: 'pointer' }}>Minkops</div>
                <div className="nav-links">
                    <a href="#agents" onClick={(e) => { e.preventDefault(); setViewState('agents'); }}>Agents</a>
                    <Link to="/about">About</Link>
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
                                            <button className="cta-button large-cta" onClick={handleProceedToAgents}>
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
                                        agents={filteredAgents}
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

                                        <div className="action-buttons" style={{ marginTop: '1.5rem', pointerEvents: 'auto', display: 'flex', gap: '1rem', justifyContent: 'center' }}>
                                            <button className="cta-button btn-hire">
                                                Hire {selectedAgent.name}
                                            </button>
                                            <button className="cta-button btn-interview">
                                                Interview {selectedAgent.name}
                                            </button>
                                        </div>

                                        <div style={{ marginTop: '1rem', pointerEvents: 'auto' }}>
                                            <button
                                                className="secondary-button"
                                                onClick={handleBackToIndustries}
                                                style={{
                                                    background: 'transparent',
                                                    border: 'none',
                                                    padding: '0.5rem 1rem',
                                                    cursor: 'pointer',
                                                    color: 'var(--text-muted)',
                                                    fontSize: '0.9rem',
                                                    textDecoration: 'underline'
                                                }}
                                            >
                                                Back to Industries
                                            </button>
                                        </div>
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
                            <a href="#agents" onClick={() => setViewState('agents')}>Agents</a>
                            <a href="#orchestration">Orchestration</a>
                            <a href="#security">Security</a>
                            <a href="#pricing">Pricing</a>
                        </div>

                        <div className="footer-column">
                            <h4>Company</h4>
                            <Link to="/about">About Us</Link>
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
