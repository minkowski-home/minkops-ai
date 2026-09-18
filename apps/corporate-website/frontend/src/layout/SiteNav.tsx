import { useEffect, useId, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { ACCESS_HREF } from "../content/site";
import { ButtonLink, cx } from "../ui/primitives";
import Wordmark from "./Wordmark";

const NAV_ITEMS = [
  { to: "/", label: "Employees", end: true },
  { to: "/orchestration", label: "How it works" },
  { to: "/about", label: "About" },
  { to: "/blogs", label: "Blog" },
  { to: "/careers", label: "Careers" }
] as const;

function navLinkClass({ isActive }: { isActive: boolean }) {
  return cx("mk-nav__link", isActive && "is-active");
}

export default function SiteNav() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const menuId = useId();

  // Any navigation (including hash jumps) should close the mobile menu.
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname, location.hash]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  return (
    <header className="mk-nav">
      <div className="mk-nav__bar">
        <Link to="/" className="mk-nav__brand" aria-label="Minkops home">
          <Wordmark />
        </Link>

        <nav className="mk-nav__links" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={"end" in item ? item.end : false}
              className={navLinkClass}
            >
              {item.label}
            </NavLink>
          ))}
          <ButtonLink
            to={ACCESS_HREF}
            variant="primary"
            size="md"
            className="mk-nav__cta"
          >
            Get access
          </ButtonLink>
        </nav>

        <button
          type="button"
          className="mk-nav__toggle"
          aria-expanded={menuOpen}
          aria-controls={menuId}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span className="mk-visually-hidden">
            {menuOpen ? "Close menu" : "Open menu"}
          </span>
          <span
            className={cx("mk-nav__burger", menuOpen && "is-open")}
            aria-hidden="true"
          >
            <span />
            <span />
          </span>
        </button>
      </div>

      <nav
        id={menuId}
        className={cx("mk-nav__sheet", menuOpen && "is-open")}
        aria-label="Primary, mobile"
        hidden={!menuOpen}
      >
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={"end" in item ? item.end : false}
            className={navLinkClass}
          >
            {item.label}
          </NavLink>
        ))}
        <ButtonLink to={ACCESS_HREF} variant="primary" size="lg" fullWidth>
          Get access
        </ButtonLink>
      </nav>
    </header>
  );
}
