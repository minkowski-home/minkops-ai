import { Link } from "react-router-dom";
import { POSTS } from "../../content/posts";
import { FUNNEL_HREF, SITE } from "../../content/site";
import BlogPostLayout, { PostNote } from "./BlogPostLayout";

export default function MyndralOperations() {
  return (
    <BlogPostLayout
      post={POSTS.myndralOperations}
      cta={{
        title: "Small team, growing inbox?",
        body: "See which Minkops employee would take the most off your plate first. It takes four questions.",
        label: "Find your first hire",
        to: FUNNEL_HREF
      }}
    >
      <p>
        <a href={SITE.links.myndral} target="_blank" rel="noopener noreferrer">
          Myndral
        </a>{" "}
        is a curated music label built around original fictional artists and a growing
        musical universe. It isn&apos;t a marketplace or a prompt-to-song tool, and it
        deliberately doesn&apos;t take outside uploads. Every artist and album is created
        and looked after in-house. That curation is the whole product.
      </p>
      <p>
        It also means Myndral runs into a very ordinary small-team problem. A catalog that
        has grown to two dozen artists and dozens of albums produces a real, steady stream
        of listener email and catalog questions, and the team behind it is small enough
        that nobody wants that stream to become someone&apos;s full-time job. Here&apos;s
        how it&apos;s handled instead.
      </p>

      <h2>Listener email, read before anyone opens the inbox</h2>
      <p>
        <strong>Imel</strong> triages everything that arrives in Myndral&apos;s listener
        inbox: subscription questions, playback problems and, more often than you&apos;d
        expect from a music app, genuine questions about the lore. Fans of a closed
        musical universe ask detailed questions about artist backstories and how two
        artists&apos; catalogs connect. Imel sorts the billing issues from the canon
        questions, and drafts replies that stay consistent with each artist&apos;s
        established story instead of a generic &quot;thanks for reaching out.&quot;
      </p>
      <PostNote label="Why this is harder than a normal support inbox">
        A generic support bot doesn&apos;t know Myndral&apos;s canon. Imel works from the
        same catalog context the product itself is built on, so a reply about an
        artist&apos;s backstory doesn&apos;t contradict what&apos;s actually been
        published.
      </PostNote>

      <h2>Catalog and subscription questions, resolved without a queue</h2>
      <p>
        <strong>Kall</strong> handles the recurring account and subscription tickets: a
        listener who can&apos;t find a saved playlist after switching devices, someone
        asking why a track vanished from a playlist after an artist&apos;s catalog was
        updated. Each of those has a real, specific answer sitting in the account or
        catalog record, so Kall resolves the ticket directly instead of routing it into a
        backlog that gets worked through once a week.
      </p>
      <PostNote label="The quiet win">
        Tickets get closed the day they&apos;re opened, not the week they&apos;re opened,
        without adding a support hire to a five-person team.
      </PostNote>

      <h2>Watching the catalog, not just the inbox</h2>
      <p>
        <strong>Insi</strong>, our business analyst, keeps an eye on which artists and
        albums are landing with listeners and which are quietly underperforming. It&apos;s
        the same signal a label&apos;s A&amp;R team tracks by hand, watched continuously
        instead of reviewed once a quarter. A curated label needs that before deciding
        what to release next. It just shouldn&apos;t need a dedicated analyst on payroll
        to get it.
      </p>
      <PostNote label="Why curation and automation aren't in tension here">
        Myndral&apos;s whole pitch is coherence over volume. Employees carrying the
        operational load are what let a small team hold that bar, instead of trading it
        away for scale.
      </PostNote>

      <h2>What this actually proves</h2>
      <p>
        Myndral and Minkowski Home could hardly be less alike. One sells furniture; the
        other runs a music label. That&apos;s exactly why we use both as case studies. The
        same employees, <Link to="/orchestration">working as one team</Link>, handle inbox
        triage, support resolution and catalog monitoring in either one, because the
        underlying job doesn&apos;t change between a furniture company and a record label:
        read the message, work out what it needs, act on it inside a policy.
      </p>
    </BlogPostLayout>
  );
}
