import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import PageShell from "./components/PageShell";
import SiteFooter from "./components/SiteFooter";
import SiteNav from "./components/SiteNav";
import SeoHead from "./components/SeoHead";
import { getAgentByName } from "./agentDirectory";

const TITLE = "How Myndral Runs Listener Support and Catalog Ops on Minkops";
const DESCRIPTION =
  "Myndral is a curated music label with dozens of artists and albums and no support team to speak of. Here's how it keeps up with listener email and catalog questions using Minkops agents instead.";
const PATH = "/blogs/myndral-day-to-day-operations";

export default function BlogPost5() {
  const imelColor = getAgentByName("Imel")?.color ?? "#cf996e";
  const kallColor = getAgentByName("Kall")?.color ?? "#dd7f9e";
  const insiColor = getAgentByName("Insi")?.color ?? "#69a9a5";

  return (
    <PageShell>
      <SeoHead title={TITLE} description={DESCRIPTION} path={PATH} />
      <SiteNav />

      <main className="page-main">
        <article className="page-container blog">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <Link to="/blogs" className="back-link">
              ← Back to Blog
            </Link>

            <span className="blog-card-tag">Case Study</span>
            <h1 className="page-title">{TITLE}</h1>

            <div className="blog-meta">
              <span>Sep 9, 2026</span>
              <span>7 min read</span>
            </div>

            <div className="blog-content">
              <p>
                <a href="https://app.myndral.com">Myndral</a> is a curated music
                label built around original fictional artists and a growing musical
                universe — not a marketplace, not a prompt-to-song tool, and
                deliberately not open to outside uploads. Every artist and album is
                created and maintained in-house. That curation is the entire product.
              </p>
              <p>
                It also means Myndral runs into a very ordinary small-team problem:
                a catalog that&apos;s grown to two dozen artists and dozens of albums
                generates a real, steady stream of listener email and catalog
                questions, and the team behind it is small enough that nobody wants
                that stream to become someone&apos;s full-time job. Here&apos;s how
                it&apos;s handled instead.
              </p>

              <h3>Listener email, read before anyone opens the inbox</h3>
              <p>
                <strong>Imel</strong> triages everything that comes into Myndral&apos;s
                listener inbox: subscription questions, playback issues, and — more
                often than you&apos;d expect from a music app — genuine questions
                about the lore. Fans of a closed musical universe ask detailed
                questions about artist backstories and how two artists&apos;
                catalogs connect. Imel classifies what&apos;s a billing issue versus
                what&apos;s a canon question, and drafts a reply that&apos;s
                consistent with the artist&apos;s established story rather than a
                generic &quot;thanks for reaching out.&quot;
              </p>
              <div className="blog-callout" style={{ borderLeftColor: imelColor }}>
                <strong
                  style={{
                    display: "block",
                    fontSize: "1rem",
                    marginBottom: "0.5rem",
                    color: imelColor,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em"
                  }}
                >
                  Why this is harder than a normal support inbox
                </strong>
                <em>
                  A generic support bot doesn&apos;t know Myndral&apos;s canon. Imel
                  works from the same catalog context the product itself is built
                  on, so a reply about an artist&apos;s backstory doesn&apos;t
                  contradict what&apos;s actually published.
                </em>
              </div>

              <h3>Catalog and subscription questions, resolved without a queue</h3>
              <p>
                <strong>Kall</strong> handles the recurring account and subscription
                tickets — a listener who can&apos;t find a saved playlist after
                switching devices, someone asking why a track disappeared from a
                playlist after an artist&apos;s catalog was updated. Each of those
                has a real, specific answer sitting in the account or catalog record;
                Kall resolves the ticket directly instead of routing it into a
                backlog that only gets worked through once a week.
              </p>
              <div className="blog-callout" style={{ borderLeftColor: kallColor }}>
                <strong
                  style={{
                    display: "block",
                    fontSize: "1rem",
                    marginBottom: "0.5rem",
                    color: kallColor,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em"
                  }}
                >
                  The quiet win
                </strong>
                <em>
                  Tickets get closed the day they&apos;re opened, not the week
                  they&apos;re opened — without adding a support hire to a five-person
                  team.
                </em>
              </div>

              <h3>Watching the catalog, not just the inbox</h3>
              <p>
                <strong>Insi</strong>, the business analyst agent, keeps an eye on
                which artists and albums are actually landing with listeners versus
                which are quietly underperforming — the same signal a label&apos;s
                A&amp;R team would track by hand, except it&apos;s watched
                continuously instead of reviewed once a quarter. That&apos;s
                information a curated label genuinely needs before deciding what to
                release next; it just doesn&apos;t need a dedicated analyst on
                payroll to get it.
              </p>
              <div className="blog-callout" style={{ borderLeftColor: insiColor }}>
                <strong
                  style={{
                    display: "block",
                    fontSize: "1rem",
                    marginBottom: "0.5rem",
                    color: insiColor,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em"
                  }}
                >
                  Why curation and automation aren&apos;t in tension here
                </strong>
                <em>
                  Myndral&apos;s whole pitch is coherence over volume. Agents
                  handling the operational load are what make it possible for a
                  small team to hold that bar instead of trading it away for scale.
                </em>
              </div>

              <h3>What this is actually proof of</h3>
              <p>
                Myndral and Minkowski Home could not be less alike as businesses —
                one sells furniture, the other runs a music label. That&apos;s the
                point of using both as a case study. The same fleet of agents —{" "}
                <Link to="/orchestration">built on one orchestration layer</Link>{" "}
                — covers inbox triage, support resolution, and operational
                monitoring in either one, because the underlying job (read the
                message, decide what it needs, act on it inside a policy) doesn&apos;t
                actually change between a furniture company and a record label.
              </p>
            </div>

            <div className="blog-cta">
              <h3 style={{ fontSize: "2rem", marginBottom: "1rem" }}>
                Running a small team with a growing inbox?
              </h3>
              <p>See which Minkops agent would take the most off your plate first.</p>
              <a
                href="/#access"
                className="cta-button"
                style={{ display: "inline-block" }}
              >
                Find Your First Agent
              </a>
            </div>
          </motion.div>
        </article>
      </main>

      <SiteFooter />
    </PageShell>
  );
}
