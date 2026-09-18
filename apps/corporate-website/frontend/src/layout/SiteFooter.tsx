import { Link } from "react-router-dom";
import { ACCESS_HREF, FUNNEL_HREF, SITE } from "../content/site";
import { Eyebrow } from "../ui/primitives";
import Wordmark from "./Wordmark";

type FooterLink = { label: string; to: string; external?: boolean };

const COLUMNS: ReadonlyArray<{ heading: string; links: readonly FooterLink[] }> = [
  {
    heading: "Platform",
    links: [
      { label: "Meet the team", to: "/" },
      { label: "How they work together", to: "/orchestration" },
      { label: "Find your first hire", to: FUNNEL_HREF },
      { label: "Get access", to: ACCESS_HREF }
    ]
  },
  {
    heading: "Company",
    links: [
      { label: "About us", to: "/about" },
      { label: "Careers", to: "/careers" },
      { label: "Blog", to: "/blogs" },
      { label: "LinkedIn", to: SITE.links.linkedin, external: true }
    ]
  },
  {
    heading: "Say hello",
    links: [
      { label: SITE.emails.general, to: `mailto:${SITE.emails.general}`, external: true },
      { label: SITE.emails.hr, to: `mailto:${SITE.emails.hr}`, external: true }
    ]
  },
  {
    heading: "The family",
    links: [
      { label: "Myndral", to: SITE.links.myndral, external: true },
      { label: "Minkowski Home", to: SITE.links.minkowskiHome, external: true }
    ]
  }
];

function FooterAnchor({ link }: { link: FooterLink }) {
  if (link.external) {
    const isWeb = link.to.startsWith("http");
    return (
      <a
        href={link.to}
        className="mk-footer__link"
        {...(isWeb ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      >
        {link.label}
      </a>
    );
  }
  return (
    <Link to={link.to} className="mk-footer__link">
      {link.label}
    </Link>
  );
}

export default function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="mk-footer">
      <div className="mk-footer__grid">
        <div className="mk-footer__brand">
          <Wordmark inverse />
          <p className="mk-footer__tagline">
            AI employees for small teams with more work than hands.
          </p>
          <address className="mk-footer__address">
            {SITE.address.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </address>
        </div>

        {COLUMNS.map((column) => (
          <div key={column.heading} className="mk-footer__col">
            <Eyebrow inverse>{column.heading}</Eyebrow>
            <ul className="mk-footer__list">
              {column.links.map((link) => (
                <li key={link.label}>
                  <FooterAnchor link={link} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mk-footer__base">
        <p>© {year} Minkops. A product of Minkowski Home. All rights reserved.</p>
        <span className="mk-footer__legal">
          <Link to="/privacy" className="mk-footer__link mk-footer__link--quiet">
            Privacy policy
          </Link>
          <Link to="/terms" className="mk-footer__link mk-footer__link--quiet">
            Terms of service
          </Link>
        </span>
      </div>
    </footer>
  );
}
