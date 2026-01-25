import { Link } from "react-router-dom";

export default function SiteFooter() {
  return (
    <footer className="main-footer">
      <div className="footer-content">
        <div className="footer-column brand-col">
          <div className="footer-logo">Minkops</div>
          <p>Operating system for zero-man companies</p>
        </div>

        <div className="footer-column">
          <h4>Platform</h4>
          <a href="/#access">Agents</a>
          <Link to="/orchestration">Orchestration</Link>
          <a href="/#access">Pricing</a>
        </div>

        <div className="footer-column">
          <h4>Company</h4>
          <Link to="/about">About Us</Link>
          <Link to="/careers">Careers</Link>
          <Link to="/blogs">Blog</Link>
          <a href="mailto:hello@minkops.ai">Contact</a>
          <a href="https://linkedin.com/company/minkops">LinkedIn</a>
        </div>
      </div>

      <div className="footer-bottom">
        <p>&copy; 2025 Minkops. A product of Minkowski Home. All rights reserved.</p>
        <div className="legal-links">
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/terms">Terms of Service</Link>
        </div>
      </div>
    </footer>
  );
}
