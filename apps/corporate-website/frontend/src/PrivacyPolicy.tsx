import { motion } from "framer-motion";
import PageShell from "./components/PageShell";
import SiteFooter from "./components/SiteFooter";
import SiteNav from "./components/SiteNav";

export default function PrivacyPolicy() {
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
            <h1 className="page-title">Privacy Policy</h1>

            <div className="site-glass-card">
              <section className="legal-section">
                <h2>1. Information Collection</h2>
                <p>
                  We collect information that you provide directly to us when you request
                  access, create an account, or communicate with us.
                </p>
              </section>

              <section className="legal-section">
                <h2>2. Use of Information</h2>
                <p>
                  We use the information we collect to provide, maintain, and improve our
                  services, including our AI agents.
                </p>
              </section>

              <section className="legal-section">
                <h2>3. Data Security</h2>
                <p>
                  We implement appropriate security measures to protect your personal
                  information against unauthorized access or disclosure.
                </p>
              </section>

              <section className="legal-section">
                <h2>4. Contact Us</h2>
                <p>
                  If you have questions about this Privacy Policy or business
                  collaborations, contact{" "}
                  <a
                    href="mailto:info@minkowskihome.com"
                    style={{ color: "var(--primary-glow)" }}
                  >
                    info@minkowskihome.com
                  </a>
                  . For HR-related requests, employee verification, and job
                  applications, contact{" "}
                  <a
                    href="mailto:hr@minkowskihome.com"
                    style={{ color: "var(--primary-glow)" }}
                  >
                    hr@minkowskihome.com
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
