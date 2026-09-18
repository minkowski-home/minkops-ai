import { useEffect } from "react";
import { SITE } from "../content/site";

type SeoHeadProps = {
  /** Page-specific title. The site name is appended unless `bare` is set. */
  title: string;
  /** One or two sentences for search results and link previews. */
  description: string;
  /** Site-relative path (e.g. "/about"), used for canonical and OG URLs. */
  path: string;
  type?: "website" | "article";
  /** Use the title exactly as given (the home page carries its own full title). */
  bare?: boolean;
};

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attr, key);
    document.head.appendChild(element);
  }
  element.setAttribute("content", content);
}

function upsertCanonical(href: string) {
  let element = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!element) {
    element = document.createElement("link");
    element.setAttribute("rel", "canonical");
    document.head.appendChild(element);
  }
  element.setAttribute("href", href);
}

/**
 * Per-route document metadata without a head-management dependency.
 *
 * Every routed page renders one of these, so each navigation overwrites the
 * full set of tags. Nothing needs restoring on unmount: the next page always
 * writes its own values, and index.html carries the home-page defaults for
 * crawlers that don't execute JavaScript.
 */
export default function SeoHead({
  title,
  description,
  path,
  type = "website",
  bare = false
}: SeoHeadProps) {
  useEffect(() => {
    const fullTitle = bare ? title : `${title} · ${SITE.name}`;
    const url = `${SITE.url}${path}`;

    document.title = fullTitle;
    upsertMeta("name", "description", description);
    upsertMeta("property", "og:site_name", SITE.name);
    upsertMeta("property", "og:title", fullTitle);
    upsertMeta("property", "og:description", description);
    upsertMeta("property", "og:type", type);
    upsertMeta("property", "og:url", url);
    upsertMeta("name", "twitter:card", "summary");
    upsertMeta("name", "twitter:title", fullTitle);
    upsertMeta("name", "twitter:description", description);
    upsertCanonical(url);
  }, [title, description, path, type, bare]);

  return null;
}
