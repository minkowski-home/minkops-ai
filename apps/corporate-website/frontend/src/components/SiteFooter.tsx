import { Link } from "react-router-dom";

export default function SiteFooter() {
  return (
    <footer className="main-footer glass-panel-vibrant soft-enter">
      <div className="footer-content">
        <div className="footer-column brand-col">
          <div className="footer-logo">Minkops</div>
          <p>Operating system for zero-man companies</p>
          <address className="footer-address">
            375 University Avenue Suite 3215
            <br />
            Toronto, ON M5G 2J5
            <br />
            Canada
          </address>
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
          <a href="mailto:info@minkops.com">
            Enquiries: info@minkops.com
          </a>
          <a href="mailto:hr@minkops.com">
            HR & Verification: hr@minkops.com
          </a>
          <a href="https://linkedin.com/company/minkops">LinkedIn</a>
        </div>

        <div className="footer-column">
          <h4>More from the family</h4>
          <a href="https://app.myndral.com">Myndral</a>
          <a href="https://minkowskihome.com">Minkowski Home</a>
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
