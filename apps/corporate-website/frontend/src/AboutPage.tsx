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
    transition: { duration: 0.7 },
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
            <span className="about-eyebrow">Internal Preview</span>
            <h1>
              Built for Minkowski Home. Refined for the world.
            </h1>
            <p>
              Minkops is the internal operating system powering Minkowski Home.
              We are using these agents to run our own company, proving their value
              every day before opening them up to the public.
            </p>
            <div className="about-hero-actions">
              <Link className="cta-button" to="/">
                View Agents
              </Link>
              <a className="about-secondary" href="mailto:hello@minkops.ai">
                Join Waitlist
              </a>
            </div>
          </motion.div>

          <motion.div className="about-hero-card" variants={itemVariants}>
            <div className="signal-row">
              <div className="signal-dot" />
              <span className="signal-label">Status</span>
              <span className="signal-chip">Internal Beta</span>
            </div>
            <div className="signal-stat">
              <h3>Minkowski Home</h3>
              <p>Primary Internal User</p>
            </div>
            <div className="signal-grid">
              <div>
                <h4>100%</h4>
                <span>Internal usage</span>
              </div>
              <div>
                <h4>Zero</h4>
                <span>Manual overhead</span>
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
            <span className="section-eyebrow">Philosophy</span>
            <h2>Dogfooding our own future.</h2>
            <p>
              We believe the best way to build autonomous agents is to rely on them ourselves.
              Minkops isn't just a product; it's how we work.
            </p>
          </motion.div>
          <div className="values-grid">
            <motion.div className="value-card" variants={itemVariants}>
              <h3>Tested in production</h3>
              <p>
                Every agent we offer has been used to solve real problems within Minkowski Home first.
              </p>
            </motion.div>
            <motion.div className="value-card" variants={itemVariants}>
              <h3>Real-world results</h3>
              <p>
                We don't rely on theoretical benchmarks. We look at our own bottom line and operational efficiency.
              </p>
            </motion.div>
            <motion.div className="value-card" variants={itemVariants}>
              <h3>Ready for scale</h3>
              <p>
                Because we run on Minkops, we know it handles complexity, improved reliability, and scale.
              </p>
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
              <h2>Opening to the public soon.</h2>
              <p>
                We are finalizing our internal testing. Be the first to know when we launch.
              </p>
            </div>
            <div className="cta-actions">
              <a className="cta-button" href="mailto:hello@minkops.ai">
                Request Early Access
              </a>
            </div>
          </motion.div>
        </motion.section>
      </main>
    </div>
  );
}
