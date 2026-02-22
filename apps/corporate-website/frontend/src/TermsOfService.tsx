import { motion } from "framer-motion";
import PageShell from "./components/PageShell";
import SiteFooter from "./components/SiteFooter";
import SiteNav from "./components/SiteNav";

export default function TermsOfService() {
  return (
    <PageShell>
      <SiteNav />

      <main className="page-main">
        <div className="page-container narrow">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
          >
            <h1 className="page-title">Terms of Service</h1>

            <div className="site-glass-card">
              <section className="legal-section">
                <h2>1. Acceptance of Terms</h2>
                <p>
                  By accessing and using Minkops, a product of Minkowski Home, you accept
                  and agree to be bound by the terms and provision of this agreement.
                </p>
              </section>

              <section className="legal-section">
                <h2>2. Use of Service</h2>
                <p>
                  Our AI agents are designed to assist with business operations. You agree
                  to use these agents responsibly and in compliance with all applicable
                  laws and regulations.
                </p>
              </section>

              <section className="legal-section">
                <h2>3. Data &amp; Privacy</h2>
                <p>
                  We respect your data. Your interaction with our agents is encrypted and
                  governed by our Privacy Policy.
                </p>
              </section>

              <section className="legal-section">
                <h2>4. Contact Information</h2>
                <p>
                  For any questions regarding these Terms, please contact us at{" "}
                  <a
                    href="mailto:info@minkowskihome.com"
                    style={{ color: "var(--primary-glow)" }}
                  >
                    info@minkowskihome.com
                  </a>
                  .
                </p>
              </section>

              <section className="legal-section">
                <h2>5. Corporate Address</h2>
                <p>
                  Minkops is a product of Minkowski Home. Our corporate mailing address
                  is 375 University Avenue Suite 3215, Toronto, ON M5G 2J5, Canada.
                </p>
              </section>
            </div>
          </motion.div>
        </div>
      </main>

      <SiteFooter />
    </PageShell>
  );
}
