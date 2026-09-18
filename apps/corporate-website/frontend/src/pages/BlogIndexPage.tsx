import { Link } from "react-router-dom";
import { POST_INDEX, postPath } from "../content/posts";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { Badge } from "../ui/primitives";

export default function BlogIndexPage() {
  return (
    <>
      <SeoHead
        title="Blog"
        description="Notes from a company that runs on its own product: what's working, what surprised us, and what we learned putting AI employees to work."
        path="/blogs"
      />

      <PageHero
        eyebrow="Blog"
        title="Notes from a company that runs on its own product."
        lead="What's working, what surprised us, and what we'd do differently next time. No invented metrics and no imaginary customers."
      />

      <Section>
        <ol className="mk-post-list">
          {POST_INDEX.map((post) => (
            <li key={post.slug}>
              <Link to={postPath(post)} className="mk-post-card">
                <span className="mk-post-card__meta">
                  <Badge>{post.tag}</Badge>
                  <span className="mk-post-card__date">
                    <time dateTime={post.date}>{post.date}</time> · {post.readMinutes} min
                    read
                  </span>
                </span>
                <span className="mk-post-card__title">{post.title}</span>
                <span className="mk-post-card__excerpt">{post.description}</span>
                <span className="mk-post-card__cta">Read the post</span>
              </Link>
            </li>
          ))}
        </ol>
      </Section>
    </>
  );
}
