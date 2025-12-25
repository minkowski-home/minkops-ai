import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import AgentCanvas from "./components/AgentCanvas";
import "./App.css"; // We will update this next

const agentsInfo = [
    {
        id: 0,
        title: "Conversational",
        description: "Natural language processing for seamless human-like interactions.",
        videoColor: "#ff0080"
    },
    {
        id: 1,
        title: "Operational",
        description: "Streamline workflows and manage resources with precision.",
        videoColor: "#4d4dff"
    },
    {
        id: 2,
        title: "Analytical",
        description: "Deep insights and predictive modeling for data-driven decisions.",
        videoColor: "#ffff00"
    },
    {
        id: 3,
        title: "Communications",
        description: "Centralized hub for internal and external messaging.",
        videoColor: "#00ffff"
    }
];

export default function MinkopsLanding() {
    const [selectedAgentId, setSelectedAgentId] = useState(0);

    const selectedAgent = agentsInfo.find((a) => a.id === selectedAgentId);

    return (
        <div className="minkops-bg">
            {/* Background Gradients */}
            <div className="gradient-orb orb-1" />
            <div className="gradient-orb orb-2" />

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
                            The next generation of autonomous corporate agents.
                        </p>
                        <div className="scroll-indicator">
                            <span>Scroll to Explore</span>
                            <div className="arrow-down"></div>
                        </div>
                    </motion.div>
                </section>

                {/* 3D Agent Selector */}
                <section id="agents" className="agents-section">
                    <motion.div
                        initial={{ opacity: 0 }}
                        whileInView={{ opacity: 1 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8 }}
                        className="agents-header"
                    >
                        <h2>Select Your Agent</h2>
                        <p>Interact with the models below to see their capabilities.</p>
                    </motion.div>

                    <div className="canvas-wrapper">
                        <AgentCanvas selectedId={selectedAgentId} onSelect={setSelectedAgentId} />
                    </div>
                </section>

                {/* Demo Video Section */}
                <section className="demo-section">
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={selectedAgentId}
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 20 }}
                            transition={{ duration: 0.5 }}
                            className="demo-container"
                        >
                            <div className="demo-text">
                                <h3>{selectedAgent?.title}</h3>
                                <p>{selectedAgent?.description}</p>
                            </div>

                            <div
                                className="video-placeholder"
                                style={{
                                    boxShadow: `0 0 50px ${selectedAgent?.videoColor}40`,
                                    border: `1px solid ${selectedAgent?.videoColor}`
                                }}
                            >
                                <div
                                    className="video-content"
                                    style={{ backgroundColor: `${selectedAgent?.videoColor}20` }}
                                >
                                    <span style={{ color: selectedAgent?.videoColor, fontSize: '2rem' }}>
                                        DEMO VIDEO: {selectedAgent?.title.toUpperCase()}
                                    </span>
                                    <div className="play-button" style={{ borderColor: selectedAgent?.videoColor }}>
                                        ▶
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    </AnimatePresence>
                </section>

                {/* Footer */}
                <footer className="simple-footer">
                    <p>&copy; 2025 Minkops AI.</p>
                </footer>
            </main>
        </div>
    );
}
