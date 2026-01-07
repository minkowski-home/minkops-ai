import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import "./AboutPage.css";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.16, delayChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.7, ease: "easeOut" },
  },
};

export default function AboutPage() {
  return (
    <div className="about-page">
      <div className="about-glow glow-1" />
      <div className="about-glow glow-2" />
      <div className="about-grid" />

      <nav className="glass-nav about-nav">
        <Link className="nav-logo" to="/">
          Minkops
        </Link>
        <div className="nav-links">
          <Link to="/">Agents</Link>
          <Link to="/about">About</Link>
          <a className="cta-button" href="mailto:hello@minkops.ai">
            Get Access
          </a>
        </div>
      </nav>

      <main className="about-main">
        <motion.section
          className="about-hero"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          <motion.div className="about-hero-text" variants={itemVariants}>
            <span className="about-eyebrow">About Minkops</span>
            <h1>
              We build the operating system for zero-man companies so founders can
              focus on the mission.
            </h1>
            <p>
              Minkops orchestrates AI employees across voice, workflow, and
              customer touchpoints. We design the infrastructure, you decide the
              outcomes.
            </p>
            <div className="about-hero-actions">
              <Link className="cta-button" to="/">
                Explore Agents
              </Link>
              <a className="about-secondary" href="mailto:hello@minkops.ai">
                Talk to the team
              </a>
            </div>
          </motion.div>

          <motion.div className="about-hero-card" variants={itemVariants}>
            <div className="signal-row">
              <div className="signal-dot" />
              <span className="signal-label">Live signal</span>
              <span className="signal-chip">Always on</span>
            </div>
            <div className="signal-stat">
              <h3>12M+</h3>
              <p>Automated interactions in the last 12 months.</p>
            </div>
            <div className="signal-grid">
              <div>
                <h4>42</h4>
                <span>Enterprise playbooks</span>
              </div>
              <div>
                <h4>99.98%</h4>
                <span>Reliability in production</span>
              </div>
              <div>
                <h4>24/7</h4>
                <span>Ops coverage</span>
              </div>
              <div>
                <h4>18</h4>
                <span>Industries supported</span>
              </div>
            </div>
          </motion.div>
        </motion.section>

        <motion.section
          className="about-section"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.3 }}
        >
          <motion.div className="section-heading" variants={itemVariants}>
            <span className="section-eyebrow">Principles</span>
            <h2>We focus on durable systems, not demos.</h2>
            <p>
              Every release reinforces the same three ideas: clarity for operators,
              autonomy for agents, and safety for customers.
            </p>
          </motion.div>
          <div className="values-grid">
            <motion.div className="value-card" variants={itemVariants}>
              <h3>Human-first orchestration</h3>
              <p>
                Workflows stay legible. You can always see the plan, the owner,
                and the next action.
              </p>
            </motion.div>
            <motion.div className="value-card" variants={itemVariants}>
              <h3>Precision over volume</h3>
              <p>
                We tune for outcomes that matter, with guardrails and measurable
                improvements.
              </p>
            </motion.div>
            <motion.div className="value-card" variants={itemVariants}>
              <h3>Designed to scale quietly</h3>
              <p>
                Reliable agents are invisible. They handle the queue so humans can
                design what is next.
              </p>
            </motion.div>
          </div>
        </motion.section>

        <motion.section
          className="about-section about-steps"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.3 }}
        >
          <motion.div className="section-heading" variants={itemVariants}>
            <span className="section-eyebrow">How we build</span>
            <h2>From signal to execution in three layers.</h2>
          </motion.div>
          <div className="steps-grid">
            <motion.div className="step-card" variants={itemVariants}>
              <span className="step-number">01</span>
              <h3>Sense</h3>
              <p>
                We capture customer intent and operational friction from every
                channel in real time.
              </p>
            </motion.div>
            <motion.div className="step-card" variants={itemVariants}>
              <span className="step-number">02</span>
              <h3>Orchestrate</h3>
              <p>
                Agents collaborate with guardrails, playbooks, and escalation paths
                built for humans.
              </p>
            </motion.div>
            <motion.div className="step-card" variants={itemVariants}>
              <span className="step-number">03</span>
              <h3>Improve</h3>
              <p>
                Every outcome feeds back into the system so the fleet gets sharper
                each week.
              </p>
            </motion.div>
          </div>
        </motion.section>

        <motion.section
          className="about-section about-stats"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.3 }}
        >
          <motion.div className="section-heading" variants={itemVariants}>
            <span className="section-eyebrow">Momentum</span>
            <h2>Built with real operations in mind.</h2>
          </motion.div>
          <div className="stats-grid">
            <motion.div className="stat-card" variants={itemVariants}>
              <h3>4.6x</h3>
              <p>Average response speed gain for customer support teams.</p>
            </motion.div>
            <motion.div className="stat-card" variants={itemVariants}>
              <h3>80%</h3>
              <p>Routine tasks automated in the first 90 days.</p>
            </motion.div>
            <motion.div className="stat-card" variants={itemVariants}>
              <h3>14</h3>
              <p>Industries with active pilot programs this quarter.</p>
            </motion.div>
          </div>
        </motion.section>

        <motion.section
          className="about-cta"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.3 }}
        >
          <motion.div className="cta-panel" variants={itemVariants}>
            <div>
              <h2>Ready to design your autonomous team?</h2>
              <p>
                Tell us what should never fall through the cracks again. We will
                build the agent fleet around it.
              </p>
            </div>
            <div className="cta-actions">
              <Link className="cta-button" to="/">
                Meet the agents
              </Link>
              <a className="about-secondary" href="mailto:hello@minkops.ai">
                Book a call
              </a>
            </div>
          </motion.div>
        </motion.section>
      </main>
    </div>
  );
}
