import { Link } from "react-router-dom";
import { motion } from "framer-motion";

export default function BlogsPage() {
  return (
    <div className="minkops-bg">
      <nav className="glass-nav">
        <Link to="/" className="nav-logo">Minkops</Link>
        <div className="nav-links">
          <Link to="/">Home</Link>
          <Link to="/about">About</Link>
        </div>
      </nav>

      <main style={{ paddingTop: "120px", paddingBottom: "4rem", minHeight: "100vh" }}>
        <div style={{ maxWidth: "800px", margin: "0 auto", padding: "0 2rem" }}>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <h1 style={{ fontSize: "3rem", fontWeight: "700", marginBottom: "1rem" }}>Blogs</h1>
            <p style={{ fontSize: "1.2rem", color: "var(--text-muted)", marginBottom: "3rem" }}>
              Insights from the future of autonomous work.
            </p>

            <div style={{ display: "grid", gap: "2rem" }}>
              <Link to="/blogs/minkowski-case-study" style={{ textDecoration: "none", color: "inherit" }}>
                <motion.div
                  whileHover={{ y: -5 }}
                  style={{
                    padding: "2rem",
                    background: "rgba(255,255,255,0.6)",
                    borderRadius: "20px",
                    border: "1px solid rgba(0,0,0,0.05)",
                    cursor: "pointer"
                  }}
                >
                  <span style={{ fontSize: "0.8rem", color: "var(--primary-glow)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.05em" }}>Case Study</span>
                  <h2 style={{ fontSize: "1.8rem", margin: "0.5rem 0 1rem", fontWeight: "700" }}>Zero-Man Operations: How Minkowski Home achieved 100% automated accuracy</h2>
                  <p style={{ color: "var(--text-muted)", lineHeight: "1.6" }}>
                    How we utilized Leed, Eko, and Kall to handle lead generation, social media, and support without a single human employee.
                  </p>
                  <div style={{ marginTop: "1.5rem", fontWeight: "500", fontSize: "0.9rem" }}>Read Article →</div>
                </motion.div>
              </Link>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
