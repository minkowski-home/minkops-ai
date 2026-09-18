import { useLocation } from "react-router-dom";
import { PageHero } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { ButtonLink } from "../ui/primitives";

export default function NotFoundPage() {
  const { pathname } = useLocation();

  return (
    <>
      <SeoHead
        title="Page not found"
        description="This page doesn't exist, or it moved when we rebuilt the site."
        path={pathname}
      />
      <PageHero
        eyebrow="404 · Not found"
        title="Nothing lives at this address."
        lead="Even Imel couldn't find this one. The link may be old, or the page may have moved when we rebuilt the site. Everything that matters is a click away."
      >
        <p className="mk-not-found__path">{pathname}</p>
        <div className="mk-not-found__actions">
          <ButtonLink to="/" variant="primary" size="lg">
            Back to the start
          </ButtonLink>
          <ButtonLink to="/blogs" variant="secondary" size="lg">
            Read the blog
          </ButtonLink>
        </div>
      </PageHero>
    </>
  );
}
