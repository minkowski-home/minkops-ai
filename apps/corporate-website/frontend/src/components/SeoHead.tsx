import { useEffect } from "react";

type SeoHeadProps = {
  /** Page-specific title. The site name is appended automatically. */
  title: string;
  /** One to two sentence meta description used by search engines and social previews. */
  description: string;
  /** Site-relative path (e.g. "/blogs/what-is-an-ai-employee") used to build canonical/OG URLs. */
  path: string;
};

const SITE_URL = "https://minkops.com";

/**
 * Lightweight, dependency-free per-page SEO metadata.
 *
 * The corporate site has a single static <title> in index.html and no other
 * per-route meta tags, which is fine for the marketing pages but not for blog
 * content that needs to rank and preview well when shared. This component
 * imperatively upserts the tags that matter (title, description, canonical,
 * Open Graph, Twitter card) on mount and restores the previous title on
 * unmount, without pulling in react-helmet or a similar dependency.
 */
function upsertMetaTag(attr: "name" | "property", key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attr, key);
    document.head.appendChild(element);
  }
  element.setAttribute("content", content);
}

export default function SeoHead({ title, description, path }: SeoHeadProps) {
  useEffect(() => {
    const previousTitle = document.title;
    const url = `${SITE_URL}${path}`;

    document.title = `${title} | Minkops Blog`;

    upsertMetaTag("name", "description", description);
    upsertMetaTag("property", "og:title", title);
    upsertMetaTag("property", "og:description", description);
    upsertMetaTag("property", "og:type", "article");
    upsertMetaTag("property", "og:url", url);
    upsertMetaTag("name", "twitter:card", "summary_large_image");
    upsertMetaTag("name", "twitter:title", title);
    upsertMetaTag("name", "twitter:description", description);

    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.setAttribute("rel", "canonical");
      document.head.appendChild(canonical);
    }
    canonical.setAttribute("href", url);

    return () => {
      document.title = previousTitle;
    };
  }, [title, description, path]);

  return null;
}
