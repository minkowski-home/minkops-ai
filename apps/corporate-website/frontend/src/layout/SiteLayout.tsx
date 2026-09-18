import { useLayoutEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import SiteFooter from "./SiteFooter";
import SiteNav from "./SiteNav";

/**
 * Restores the scroll position a visitor expects on client-side navigation.
 *
 * BrowserRouter doesn't reset scroll or honour hashes on its own, so a link
 * to "/#access" from another page would land at the top of the landing page.
 * Keyed on `location.key` so clicking the same hash link twice still scrolls.
 */
function ScrollManager() {
  const { pathname, hash, key } = useLocation();

  useLayoutEffect(() => {
    if (hash) {
      const target = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (target) {
        target.scrollIntoView({ block: "start" });
        return;
      }
    }
    window.scrollTo(0, 0);
  }, [pathname, hash, key]);

  return null;
}

export default function SiteLayout() {
  return (
    <div className="mk-site">
      <a className="mk-skip-link" href="#main">
        Skip to content
      </a>
      <ScrollManager />
      <SiteNav />
      <main id="main" className="mk-site__main" tabIndex={-1}>
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  );
}
