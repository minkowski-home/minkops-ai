import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Link, useLocation } from "react-router-dom";

type SiteNavProps = {
  className?: string;
};

export default function SiteNav({ className }: SiteNavProps) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  const toggleMenu = () => setIsMobileMenuOpen((open) => !open);

  return (
    <nav className={["glass-nav", className].filter(Boolean).join(" ")}>
      <Link to="/" className="nav-logo">
        Minkops
      </Link>

      <div className="nav-links desktop-only">
        <Link to="/">Agents</Link>
        <Link to="/orchestration">Orchestration</Link>
        <Link to="/about">About</Link>
        <Link to="/blogs">Blog</Link>
        <Link to="/careers">Careers</Link>
        <a href="/#access" className="cta-button">
          Get Access
        </a>
      </div>

      <button
        type="button"
        className="mobile-toggle"
        onClick={toggleMenu}
        aria-label="Toggle menu"
      >
        <div className={`hamburger ${isMobileMenuOpen ? "open" : ""}`}>
          <span />
          <span />
          <span />
        </div>
      </button>

      <AnimatePresence>
        {isMobileMenuOpen && (
          <motion.div
            className="mobile-menu-overlay"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            <div className="mobile-nav-links">
              <Link to="/" onClick={toggleMenu}>
                Agents
              </Link>
              <Link to="/orchestration" onClick={toggleMenu}>
                Orchestration
              </Link>
              <Link to="/about" onClick={toggleMenu}>
                About
              </Link>
              <Link to="/blogs" onClick={toggleMenu}>
                Blog
              </Link>
              <Link to="/careers" onClick={toggleMenu}>
                Careers
              </Link>
              <a href="/#access" className="cta-button" onClick={toggleMenu}>
                Get Access
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}
