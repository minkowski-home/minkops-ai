import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Link, NavLink, useLocation } from "react-router-dom";

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
        minkops
      </Link>

      <div className="nav-links desktop-only">
        <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}>
          Agents
        </NavLink>
        <NavLink to="/orchestration" className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}>
          Orchestration
        </NavLink>
        <NavLink to="/about" className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}>
          About
        </NavLink>
        <NavLink to="/blogs" className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}>
          Blog
        </NavLink>
        <NavLink to="/careers" className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}>
          Careers
        </NavLink>
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
              <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`} onClick={toggleMenu}>
                Agents
              </NavLink>
              <NavLink to="/orchestration" className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`} onClick={toggleMenu}>
                Orchestration
              </NavLink>
              <NavLink to="/about" className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`} onClick={toggleMenu}>
                About
              </NavLink>
              <NavLink to="/blogs" className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`} onClick={toggleMenu}>
                Blog
              </NavLink>
              <NavLink to="/careers" className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`} onClick={toggleMenu}>
                Careers
              </NavLink>
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
