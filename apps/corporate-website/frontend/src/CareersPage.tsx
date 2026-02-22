import { motion } from "framer-motion";
import PageShell from "./components/PageShell";
import SiteFooter from "./components/SiteFooter";
import SiteNav from "./components/SiteNav";

export default function CareersPage() {
  const jobs = [
    { title: "Senior AI Engineer", type: "Engineering", location: "Remote" },
    { title: "Product Designer", type: "Design", location: "Remote" },
    { title: "Growth Manager", type: "Marketing", location: "Hybrid" }
  ];

  return (
    <PageShell>
      <SiteNav />

      <main className="page-main">
        <div className="page-container">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            style={{ textAlign: "center", marginBottom: "4rem" }}
          >
            <h1 className="page-title">Join the Revolution</h1>
            <p className="page-subtitle">
              Help us build the operating system for zero-man companies.
            </p>
          </motion.div>

          <div className="jobs-grid">
            {jobs.map((job, index) => (
              <motion.div
                key={job.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className="job-card"
              >
                <div className="job-card-header">
                  <span className="job-type">{job.type}</span>
                  <span className="job-location">{job.location}</span>
                </div>
                <h3 className="job-title">{job.title}</h3>
                <p className="job-desc">
                  We are looking for a passionate individual to join our world-class team.
                </p>
                <a href="mailto:hr@minkowskihome.com" className="job-apply">
                  Apply Now →
                </a>
              </motion.div>
            ))}
          </div>

          <div style={{ marginTop: "6rem", textAlign: "center" }}>
            <h2 style={{ fontSize: "2rem", marginBottom: "1rem" }}>
              Don&apos;t see your role?
            </h2>
            <p style={{ color: "var(--text-muted)", marginBottom: "2rem" }}>
              We are always looking for exceptional talent. Send your resume to{" "}
              <a
                href="mailto:hr@minkowskihome.com"
                style={{ color: "var(--primary-glow)" }}
              >
                hr@minkowskihome.com
              </a>
              .
            </p>
            <p style={{ color: "var(--text-muted)", marginBottom: "0" }}>
              For general business enquiries and collaborations, contact{" "}
              <a
                href="mailto:info@minkowskihome.com"
                style={{ color: "var(--primary-glow)" }}
              >
                info@minkowskihome.com
              </a>
              .
            </p>
          </div>
        </div>
      </main>

      <SiteFooter />
    </PageShell>
  );
}
