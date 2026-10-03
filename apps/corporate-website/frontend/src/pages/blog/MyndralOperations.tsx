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
        body: "Describe a process you want to improve and see an illustrative workflow outline to discuss.",
        label: "Find a workflow starting point",
        to: FUNNEL_HREF
      }}
    >
      <PostNote label="Illustrative design example">
        This article sketches a possible Workflow. It is not evidence of a deployed
        Minkops integration, measured results or current Myndral operations.
      </PostNote>
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
        This example uses catalog and listener questions to illustrate a routing
        workflow. It makes no claim about Myndral&apos;s current systems or message volume.
      </p>

      <h2>Listener email, read before anyone opens the inbox</h2>
      <p>
        A possible inbox Workflow could classify a listener question as billing, playback
        or catalog context, then prepare a draft using approved source material. A person
        would review the draft and handle anything the available context cannot answer.
        No listener inbox is connected in this example.
      </p>
      <PostNote label="Context a workflow would need">
        A real implementation would need an approved, current catalog source and a way
        for a person to verify the draft before it is sent.
      </PostNote>

      <h2>Catalog and subscription questions, resolved without a queue</h2>
      <p>
        For an account or subscription question, a proposed Workflow could gather the
        relevant record and prepare a response for review. Whether it can retrieve that
        record or resolve the request depends on separately approved integrations and
        permissions; neither is demonstrated here.
      </p>
      <PostNote label="Outcome to verify">
        Response time and resolution rate would need to be measured in a real deployment.
        This sketch reports no operational results.
      </PostNote>

      <h2>Watching the catalog, not just the inbox</h2>
      <p>
        A reporting Workflow might summarize approved catalog and listening data for a
        person to review before making a release decision. This example has no access to
        Myndral&apos;s analytics and makes no claim about listener response or release
        performance.
      </p>
      <PostNote label="Human decision point">
        The example leaves interpretation and release choices with a person; it does not
        automate catalog decisions.
      </PostNote>

      <h2>What this actually proves</h2>
      <p>
        This sketch proves no integration or customer outcome. It illustrates how a
        furniture business and a music label might discuss similar workflow building
        blocks—message triage, approved context and human review—while keeping each
        business&apos;s tools, permissions and procedures distinct. See the{" "}
        <Link to="/orchestration">product model</Link> for those boundaries.
      </p>
    </BlogPostLayout>
  );
}
