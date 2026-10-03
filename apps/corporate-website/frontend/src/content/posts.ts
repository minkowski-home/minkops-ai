/**
 * Blog post metadata. The index page, each post's header and its SEO tags
 * all read from here, so a title or date is only ever edited in one place.
 */
export type PostMeta = {
  slug: string;
  title: string;
  /** Meta description and index excerpt. One or two sentences. */
  description: string;
  tag: "Guide" | "Case study" | "Engineering";
  /** ISO date, rendered in mono as-is: it's a machine value. */
  date: string;
  readMinutes: number;
};

export const POSTS = {
  whatIsAnAiEmployee: {
    slug: "what-is-an-ai-employee",
    title: "What is an AI employee? A practical guide for small business owners",
    description:
      "A guide to AI Employees, defined business Workflows, procedural skills, approved tools, connectors and human review.",
    tag: "Guide",
    date: "2026-09-09",
    readMinutes: 9
  },
  minkowskiHomeWeek: {
    slug: "minkowski-home-day-to-day-operations",
    title: "A week inside Minkowski Home's day-to-day operations on Minkops",
    description:
      "An illustrative workflow sketch for customer enquiries and follow-up. It does not report live integrations or measured results.",
    tag: "Guide",
    date: "2026-09-09",
    readMinutes: 6
  },
  myndralOperations: {
    slug: "myndral-day-to-day-operations",
    title: "How Myndral runs listener support and catalog ops on Minkops",
    description:
      "An illustrative workflow sketch for routing listener questions with context and human review, not a report of live product results.",
    tag: "Guide",
    date: "2026-09-09",
    readMinutes: 7
  },
  autoLeadGeneration: {
    slug: "auto-lead-generation-agent",
    title: "Building an AI sales rep, from target list to booked meetings",
    description:
      "A planning note on the permissions, review steps and verification an outbound lead workflow would need. This is not a shipped capability.",
    tag: "Engineering",
    date: "2026-01-22",
    readMinutes: 14
  }
} as const satisfies Record<string, PostMeta>;

/** Newest first. */
export const POST_INDEX: readonly PostMeta[] = Object.values(POSTS).sort((a, b) =>
  b.date.localeCompare(a.date)
);

export function postPath(post: Pick<PostMeta, "slug">) {
  return `/blogs/${post.slug}`;
}
