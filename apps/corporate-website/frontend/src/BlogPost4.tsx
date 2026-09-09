import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import PageShell from "./components/PageShell";
import SiteFooter from "./components/SiteFooter";
import SiteNav from "./components/SiteNav";
import SeoHead from "./components/SeoHead";
import { getAgentByName } from "./agentDirectory";

const TITLE = "A Week Inside Minkowski Home's Day-to-Day Operations on Minkops";
const DESCRIPTION =
  "Not a launch story - the ordinary week. How Minkowski Home runs inbox triage, customer support, and lead follow-up on a small fleet of Minkops agents instead of a growing support team.";
const PATH = "/blogs/minkowski-home-day-to-day-operations";

export default function BlogPost4() {
  const imelColor = getAgentByName("Imel")?.color ?? "#cf996e";
  const kallColor = getAgentByName("Kall")?.color ?? "#dd7f9e";

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
                We&apos;ve already written about the day <strong>Minkowski Home
                (MH)</strong> launched &quot;Concrete Comfort&quot; without a single
                human running the campaign. That story gets attention because
                launches are dramatic. This one is deliberately less dramatic,
                because most of what actually costs a small business its time
                isn&apos;t the big launch — it&apos;s the ordinary Tuesday.
              </p>
              <p>
                MH is a small furniture company. Before Minkops, a normal week meant
                someone — usually the same one or two people — triaging a shared
                inbox, answering the same handful of shipping and material questions
                over and over, and letting warm leads go cold because nobody got
                around to the follow-up call. Here&apos;s what that same week looks
                like now.
              </p>

              <h3>Monday, 7:14 AM — the inbox is already handled</h3>
              <p>
                <strong>Imel</strong>, our email agent, has been reading MH&apos;s
                inbox since before anyone opened a laptop. Order confirmations that
                never needed a human get filed automatically. A genuine question about
                a delayed shipment gets classified, matched against the actual
                logistics record, and drafted into a reply with the real delivery
                window — not a canned &quot;we&apos;ll look into it.&quot;
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
                  What used to take a person 45–60 minutes a day
                </strong>
                <em>
                  Reading every inbound email, deciding what&apos;s routine versus
                  what needs judgment, and drafting a reply that&apos;s actually
                  specific to the customer&apos;s order — now happens before the
                  workday starts.
                </em>
              </div>

              <h3>Wednesday — a support question that would have sat for a day</h3>
              <p>
                A customer writes in asking whether the walnut coffee table finish
                will match a chair they bought eight months ago. <strong>Kall</strong>,
                our support agent, doesn&apos;t escalate this into a queue. It pulls
                the customer&apos;s order history, checks the finish batch notes, and
                answers directly — with a note flagged for a human only because the
                answer touches a return policy edge case that&apos;s outside its
                decision scope. That&apos;s the guardrail working as intended: Kall
                doesn&apos;t guess on the parts it isn&apos;t supposed to decide, it
                hands those off and keeps moving on everything else.
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
                  The part that actually matters
                </strong>
                <em>
                  It&apos;s not that Kall answers fast. It&apos;s that it knows which
                  questions it&apos;s allowed to answer on its own, and which ones it
                  isn&apos;t.
                </em>
              </div>

              <h3>Friday — the leads that don&apos;t fall through anymore</h3>
              <p>
                MH used to lose a predictable share of warm leads to nothing more
                complicated than nobody following up in time. Now, when a prospect
                opens a quote three times but doesn&apos;t reply, that pattern gets
                flagged and worked — a follow-up goes out referencing the specific
                pieces they were looking at, not a generic &quot;just checking
                in.&quot; It&apos;s not a dramatic new capability. It&apos;s the
                unglamorous, repetitive discipline that a growing business always
                means to keep up with and rarely does.
              </p>

              <h3>Why this is the case study that actually matters</h3>
              <p>
                A zero-man product launch is a good story precisely because it&apos;s
                unusual. Most weeks aren&apos;t like that. Most weeks are inbox
                triage, the same three support questions, and a lead that almost got
                forgotten. That&apos;s the actual cost center in a small business —
                and it&apos;s exactly the part that doesn&apos;t need a person doing
                it manually every single week.
              </p>
              <p>
                MH still has people. They&apos;re just not the ones reading every
                email first anymore.
              </p>
            </div>

            <div className="blog-cta">
              <h3 style={{ fontSize: "2rem", marginBottom: "1rem" }}>
                Want to see this running on your own inbox?
              </h3>
              <p>Start with the one role that&apos;s costing you the most hours this month.</p>
              <a
                href="/#access"
                className="cta-button"
                style={{ display: "inline-block" }}
              >
                Talk to Minkops
              </a>
            </div>
          </motion.div>
        </article>
      </main>

      <SiteFooter />
    </PageShell>
  );
}
