import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { postPath, type PostMeta } from "../../content/posts";
import { Section } from "../../layout/Section";
import SeoHead from "../../layout/SeoHead";
import { Icon } from "../../ui/Icon";
import { Badge, ButtonLink, Eyebrow } from "../../ui/primitives";

/** Shared frame for every post: SEO, header, prose column and closing call to action. */
export default function BlogPostLayout({
  post,
  cta,
  children
}: {
  post: PostMeta;
  cta: { title: string; body: string; label: string; to: string };
  children: ReactNode;
}) {
  return (
    <>
      <SeoHead
        title={post.title}
        description={post.description}
        path={postPath(post)}
        type="article"
      />

      <article className="mk-post">
        <header className="mk-post__header">
          <div className="mk-container mk-container--narrow mk-post__header-inner mk-enter">
            <Link to="/blogs" className="mk-post__back">
              <Icon name="chevronLeft" size={14} />
              All posts
            </Link>
            <div className="mk-post__meta">
              <Badge>{post.tag}</Badge>
              <span className="mk-post__date">
                <time dateTime={post.date}>{post.date}</time> · {post.readMinutes} min
                read
              </span>
            </div>
            <h1 className="mk-post__title">{post.title}</h1>
            <p className="mk-post__standfirst">{post.description}</p>
          </div>
        </header>

        <Section narrow>
          <div className="mk-prose">{children}</div>
        </Section>
      </article>

      <Section tone="sunken" narrow>
        <div className="mk-cta-band">
          <div className="mk-cta-band__text">
            <Eyebrow>Before you go</Eyebrow>
            <h2 className="mk-cta-band__title">{cta.title}</h2>
            <p className="mk-cta-band__lead">{cta.body}</p>
          </div>
          <div className="mk-cta-band__actions">
            <ButtonLink
              to={cta.to}
              size="lg"
              variant="primary"
              iconRight={<Icon name="chevronRight" size={16} />}
            >
              {cta.label}
            </ButtonLink>
          </div>
        </div>
      </Section>
    </>
  );
}

/** A margin note inside a post: mono eyebrow over a short, quotable point. */
export function PostNote({ label, children }: { label: string; children: ReactNode }) {
  return (
    <aside className="mk-prose-note">
      <Eyebrow>{label}</Eyebrow>
      <p>{children}</p>
    </aside>
  );
}

/** Machine output inside a post. Lines starting with "//" render as comments. */
export function PostCode({ lines, label }: { lines: readonly string[]; label: string }) {
  return (
    <figure className="mk-prose-figure">
      <figcaption className="mk-visually-hidden">{label}</figcaption>
      <pre className="mk-prose-code">
        <code>
          {lines.map((line, index) => (
            <span
              key={index}
              className={
                line.trimStart().startsWith("//") ? "mk-prose-code__comment" : undefined
              }
            >
              {line}
              {"\n"}
            </span>
          ))}
        </code>
      </pre>
    </figure>
  );
}
