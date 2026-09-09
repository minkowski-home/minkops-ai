import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import PageShell from "./components/PageShell";
import SiteFooter from "./components/SiteFooter";
import SiteNav from "./components/SiteNav";

export default function BlogsPage() {
  return (
    <PageShell>
      <SiteNav />

      <main className="page-main">
        <div className="page-container blog">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <h1 className="page-title">Blog</h1>
            <p className="page-subtitle" style={{ marginBottom: "3rem" }}>
              Insights from the future of autonomous work.
            </p>

            <div className="blog-list">
              <Link to="/blogs/what-is-an-ai-employee" className="blog-card-link">
                <motion.div whileHover={{ y: -5 }} className="blog-card">
                  <span className="blog-card-tag">Guide</span>
                  <h2 className="blog-card-title">
                    What Is an AI Employee? A Practical Guide for Small Business
                    Owners
                  </h2>
                  <p className="blog-card-excerpt">
                    AI employee, AI agent, AI tool — the terms get used
                    interchangeably, but they aren&apos;t the same thing. Here&apos;s
                    the practical difference, and how to evaluate one before you
                    hire it.
                  </p>
                  <div className="blog-card-cta">Read Article →</div>
                </motion.div>
              </Link>

              <Link to="/blogs/minkowski-home-day-to-day-operations" className="blog-card-link">
                <motion.div whileHover={{ y: -5 }} className="blog-card">
                  <span className="blog-card-tag">Case Study</span>
                  <h2 className="blog-card-title">
                    A Week Inside Minkowski Home&apos;s Day-to-Day Operations on
                    Minkops
                  </h2>
                  <p className="blog-card-excerpt">
                    Not a launch story — the ordinary week. How Minkowski Home runs
                    inbox triage, support, and lead follow-up on a small fleet of
                    Minkops agents instead of a growing support team.
                  </p>
                  <div className="blog-card-cta">Read Article →</div>
                </motion.div>
              </Link>

              <Link to="/blogs/myndral-day-to-day-operations" className="blog-card-link">
                <motion.div whileHover={{ y: -5 }} className="blog-card">
                  <span className="blog-card-tag">Case Study</span>
                  <h2 className="blog-card-title">
                    How Myndral Runs Listener Support and Catalog Ops on Minkops
                  </h2>
                  <p className="blog-card-excerpt">
                    A curated music label with dozens of artists and no support team
                    to speak of. Here&apos;s how Myndral keeps up with listener email
                    and catalog questions using Minkops agents instead.
                  </p>
                  <div className="blog-card-cta">Read Article →</div>
                </motion.div>
              </Link>

              <Link to="/blogs/auto-lead-generation-agent" className="blog-card-link">
                <motion.div whileHover={{ y: -5 }} className="blog-card">
                  <span className="blog-card-tag">Product</span>
                  <h2 className="blog-card-title">
                    Building an Auto Lead Generation Agent: From Target List to Booked
                    Meetings
                  </h2>
                  <p className="blog-card-excerpt">
                    A detailed look at how we&apos;re designing a policy-driven agent that
                    can source, validate, personalize, and run compliant outreach—with
                    measurable learning loops.
                  </p>
                  <div className="blog-card-cta">Read Article →</div>
                </motion.div>
              </Link>

              <Link to="/blogs/minkowski-case-study" className="blog-card-link">
                <motion.div whileHover={{ y: -5 }} className="blog-card">
                  <span className="blog-card-tag">Case Study</span>
                  <h2 className="blog-card-title">
                    Zero-Man Operations: The &quot;Sustainable Brutalism&quot; Launch
                  </h2>
                  <p className="blog-card-excerpt">
                    How we utilized Leed, Eko, and Kall to handle lead generation, social
                    media, and support without a single human employee.
                  </p>
                  <div className="blog-card-cta">Read Article →</div>
                </motion.div>
              </Link>
            </div>
          </motion.div>
        </div>
      </main>

      <SiteFooter />
    </PageShell>
  );
}
