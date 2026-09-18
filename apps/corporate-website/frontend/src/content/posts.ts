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
      "AI employee, AI agent, AI tool. The words get used interchangeably, but they mean different things. Here's the one question that tells them apart, and how to size one up before you hire it.",
    tag: "Guide",
    date: "2026-09-09",
    readMinutes: 9
  },
  minkowskiHomeWeek: {
    slug: "minkowski-home-day-to-day-operations",
    title: "A week inside Minkowski Home's day-to-day operations on Minkops",
    description:
      "Not a launch story. The ordinary week. How Minkowski Home handles inbox triage, customer support and lead follow-up with a small team of Minkops employees instead of a growing support team.",
    tag: "Case study",
    date: "2026-09-09",
    readMinutes: 6
  },
  myndralOperations: {
    slug: "myndral-day-to-day-operations",
    title: "How Myndral runs listener support and catalog ops on Minkops",
    description:
      "A curated music label with two dozen artists and nobody whose full-time job is the inbox. Here's how Myndral keeps up with listener email and catalog questions using Minkops employees.",
    tag: "Case study",
    date: "2026-09-09",
    readMinutes: 7
  },
  autoLeadGeneration: {
    slug: "auto-lead-generation-agent",
    title: "Building an AI sales rep, from target list to booked meetings",
    description:
      "How we're designing an AI sales rep that works by the rules, can source, validate, personalise and run compliant outreach, and learn from every reply along the way.",
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
