import "./App.css";

const features = [
  {
    title: "Conversational agents",
    description:
      "Autonomous intake, payments, and upsell/cross-sell experiences that feel human while staying compliant."
  },
  {
    title: "Operational assistants",
    description:
      "Track inventory, relay real-time updates, and manage attendance with secure voice identities."
  },
  {
    title: "Analytical & administrative",
    description:
      "Forecast demand, automate payroll, scheduling, reporting, and expose audit-ready activity through the knowledge graph."
  },
  {
    title: "Communications",
    description:
      "Handle calls, email, and support ticket triage with traceable AI employees that share policy decisions centrally."
  }
];

const quickLinks = [
  { label: "Demo", href: "/products-demo" },
  { label: "Products", href: "/products" },
  { label: "About", href: "/about" },
  { label: "Careers", href: "/careers" },
  { label: "Contact", href: "/contact" }
];

const socials = [
  { label: "Facebook", href: "https://facebook.com/pluseleven" },
  { label: "Twitter", href: "https://twitter.com/pluseleven" },
  { label: "LinkedIn", href: "https://linkedin.com/company/pluseleven" }
];

function App() {
  return (
    <div className="cs-page">
      <header className="cs-hero">
        <nav className="cs-nav">
          <div className="cs-logo">
            <img src="/images/iota-logo.png" alt="pluseleven" />
            <span>pluseleven</span>
          </div>
          <div className="cs-nav-links">
            {quickLinks.map((link) => (
              <a key={link.label} href={link.href}>
                {link.label}
              </a>
            ))}
          </div>
        </nav>
        <div className="cs-hero__content">
          <div>
            <span className="cs-topper">Autonomous intelligence for every industry</span>
            <h1>pluseleven</h1>
            <p>
              A unified suite of AI employees that run on a shared knowledge graph, enforce
              organizational policies, and plug directly into your existing orchestration layer.
            </p>
            <div className="cs-hero__actions">
              <a className="cs-button-solid" href="mailto:info@pluseleven.com">
                Get in touch
              </a>
              <a className="cs-button-outline" href="/products-demo">
                Explore a demo
              </a>
            </div>
          </div>
          <div className="cs-hero__visual">
            <img
              src="https://csimg.nyc3.cdn.digitaloceanspaces.com/Images/placeholder-alexa.jpg"
              alt="pluseleven operations"
              loading="lazy"
            />
          </div>
        </div>
      </header>

      <section className="cs-features">
        <div className="cs-section-heading">
          <h2>Enterprise-ready AI employees</h2>
          <p>
            Conversational, operational, administrative, analytical, and communications agents work
            together inside a central orchestration layer with auditability and failover.
          </p>
        </div>
        <div className="cs-card-group">
          {features.map((feature) => (
            <article key={feature.title} className="cs-item">
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className="cs-footer">
        <div className="cs-footer-content">
          <div className="footer-section">
            <h4>Contact Us</h4>
            <address>
              <a href="mailto:info@pluseleven.com">info@pluseleven.com</a>
              <p>Phone: +1 234 567 8900</p>
              <p>Address: 100 Hacker Way, Menlo Park, CA 94025</p>
            </address>
          </div>
          <div className="footer-section">
            <h4>Quick Links</h4>
            <ul>
              {quickLinks.map((link) => (
                <li key={link.label}>
                  <a href={link.href}>{link.label}</a>
                </li>
              ))}
            </ul>
          </div>
          <div className="footer-section">
            <h4>Follow Us</h4>
            <nav className="cs-social-links">
              {socials.map((social) => (
                <a key={social.label} href={social.href}>
                  {social.label}
                </a>
              ))}
            </nav>
          </div>
        </div>
        <div className="cs-footer-bottom">
          <p>&copy; 2024 pluseleven. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}

export default App;
