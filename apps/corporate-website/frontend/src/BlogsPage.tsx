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

            <div style={{ 
              padding: "2rem", 
              background: "rgba(255,255,255,0.5)", 
              borderRadius: "20px", 
              border: "1px solid rgba(0,0,0,0.05)" 
            }}>
              <h2 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>Coming Soon</h2>
              <p style={{ color: "var(--text-muted)" }}>
                Our team is busy building the future. Check back later for updates.
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
