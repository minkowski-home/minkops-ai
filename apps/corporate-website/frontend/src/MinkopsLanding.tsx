import { motion } from "framer-motion";
import PageShell from "./components/PageShell";
import SiteFooter from "./components/SiteFooter";
import SiteNav from "./components/SiteNav";
import InterestForm from "./components/InterestForm";
import AgentDemoSection from "./components/AgentDemoSection";

export default function MinkopsLanding() {
  return (
    <PageShell>
      <SiteNav />

      <main className="landing-main">
        <section className="hero-section">
          <motion.div
            className="hero-panel glass-panel-vibrant soft-enter"
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1 }}
          >
            <div className="hero-copy hero-copy-full">
              <h1 className="hero-title">
                Intelligence <span className="text-accent">Redefined</span>
              </h1>
              <p className="hero-subtitle">
                Meet the full suite of AI Employees
                <br />
                Powering zero-man companies
              </p>
              <div className="scroll-indicator">
                <span>Scroll to Request Access</span>
                <div className="arrow-down"></div>
              </div>
            </div>
          </motion.div>
        </section>

        <section id="access" className="access-section">
          <motion.div
            className="access-form-wrap"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
          >
            <InterestForm />
          </motion.div>
        </section>

        <section className="demo-section-shell">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
          >
            <AgentDemoSection />
          </motion.div>
        </section>
      </main>

      <SiteFooter />
    </PageShell>
  );
}
