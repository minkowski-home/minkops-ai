import type { ReactNode } from "react";
import { Eyebrow, cx } from "../ui/primitives";

/**
 * The marketing site's section scaffold: 1200px container, hairline top rule,
 * optional eyebrow / title / lead header. Sections are separated by a rule,
 * never by a colour change; `sunken` is the one permitted secondary tone.
 */
export function Section({
  id,
  eyebrow,
  title,
  lead,
  tone = "page",
  narrow = false,
  className,
  children
}: {
  id?: string;
  eyebrow?: ReactNode;
  title?: ReactNode;
  lead?: ReactNode;
  tone?: "page" | "sunken";
  narrow?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={title ? headingId : undefined}
      className={cx("mk-section", tone === "sunken" && "mk-section--sunken", className)}
    >
      <div
        className={cx(
          "mk-container",
          narrow && "mk-container--narrow",
          "mk-section__inner"
        )}
      >
        {eyebrow || title || lead ? (
          <header className="mk-section__head">
            {eyebrow ? <Eyebrow rule>{eyebrow}</Eyebrow> : null}
            {title ? (
              <h2 id={headingId} className="mk-section__title">
                {title}
              </h2>
            ) : null}
            {lead ? <p className="mk-section__lead">{lead}</p> : null}
          </header>
        ) : null}
        {children}
      </div>
    </section>
  );
}

/** Top-of-page header for every route except the landing page's hero. */
export function PageHero({
  eyebrow,
  title,
  lead,
  children
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="mk-page-hero">
      <div className="mk-container mk-page-hero__inner mk-enter">
        <Eyebrow rule>{eyebrow}</Eyebrow>
        <h1 className="mk-page-hero__title">{title}</h1>
        {lead ? <p className="mk-page-hero__lead">{lead}</p> : null}
        {children}
      </div>
    </header>
  );
}
