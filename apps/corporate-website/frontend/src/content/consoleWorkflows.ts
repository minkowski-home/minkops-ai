/*
 * Illustrative console workflows for the landing page.
 *
 * Every business, person and figure here is invented, and the page labels it
 * as an illustration. Each workflow shows the same product shape from a
 * different industry: agents report finished work in plain sentences, and turn
 * anything above their authority into one question with the answers already
 * worked out. Nothing in the console asks the operator to type.
 *
 * Agent names must exist in the roster (content/agents.ts); the console looks
 * up their glyphs there and will throw on an unknown name.
 */

export type BadgeTone = "neutral" | "approval" | "ok" | "warn";

/** One hop in the "how work moves" strip: where work comes from, who handles it, where it lands. */
export type PipelineStep =
  | { kind: "source"; label: string }
  | { kind: "agent"; agent: string }
  | { kind: "destination"; label: string };

export type Metric = {
  value: string;
  label: string;
  /** Optional 0–100 fill, drawn as the flat Ember progress bar. */
  bar?: number;
};

export type LogEntry = {
  id: string;
  agent: string;
  time: string;
  text: string;
  outcome: { label: string; tone: BadgeTone };
  /** Files the agent read or produced: photos, delivery notes, sheets. */
  attachments?: readonly string[];
};

export type Choice = { label: string; suggested?: boolean; result: string };

export type Decision = {
  id: string;
  agent: string;
  context: string;
  question: string;
  why: string;
  /** The log entry that flagged this. It flips to "Resolved" once the visitor decides. */
  flaggedEntryId: string;
  choices: readonly Choice[];
};

export type Workflow = {
  id: string;
  /** Sidebar label: what the workflow is, in two or three words. */
  name: string;
  business: string;
  descriptor: string;
  tenant: string;
  agents: readonly string[];
  pipeline: readonly PipelineStep[];
  metrics: readonly Metric[];
  log: readonly LogEntry[];
  decisions: readonly Decision[];
  /** Shown once every decision is made. */
  allClear: string;
};

const WAITING = { label: "Waiting on you", tone: "approval" } as const;

export const WORKFLOWS: readonly Workflow[] = [
  {
    id: "store",
    name: "Store operations",
    business: "Northfield Home",
    descriptor: "Shopify homeware store · team of three",
    tenant: "northfield-home",
    agents: ["Imel", "Kall", "Leed"],
    pipeline: [
      { kind: "source", label: "Shopify" },
      { kind: "source", label: "Inbox" },
      { kind: "agent", agent: "Imel" },
      { kind: "agent", agent: "Kall" },
      { kind: "agent", agent: "Leed" },
      { kind: "destination", label: "Orders saved" }
    ],
    metrics: [
      { value: "38", label: "emails answered" },
      { value: "7", label: "tickets closed" },
      { value: "$1,240", label: "in carts recovered" }
    ],
    log: [
      {
        id: "carts",
        agent: "Leed",
        time: "08:52",
        text: "Called five customers who left carts overnight. Three finished checking out while we talked.",
        outcome: { label: "Recovered $1,240", tone: "ok" }
      },
      {
        id: "tracking",
        agent: "Imel",
        time: "08:31",
        text: "Answered 11 “where's my order” emails, each with that customer's real tracking link.",
        outcome: { label: "Sent", tone: "ok" }
      },
      {
        id: "swap",
        agent: "Kall",
        time: "07:58",
        text: "Swapped a wrong-size duvet cover for Ahmed and emailed him a prepaid return label.",
        outcome: { label: "Closed", tone: "ok" }
      },
      {
        id: "discount-call",
        agent: "Leed",
        time: "07:20",
        text: "A caller wants a bigger discount on the full dining set. Held it for you.",
        outcome: WAITING
      },
      {
        id: "late-return",
        agent: "Kall",
        time: "01:40",
        text: "A return came in 41 days after delivery, outside your policy. Held it for you.",
        outcome: WAITING
      }
    ],
    decisions: [
      {
        id: "late-return",
        agent: "Kall",
        context: "Ticket 1182",
        question: "Dana wants to return a lamp 41 days after delivery.",
        why: "Your policy allows 30 days. She's ordered from you four times this year.",
        flaggedEntryId: "late-return",
        choices: [
          {
            label: "Offer $180 in store credit",
            suggested: true,
            result:
              "Offered Dana $180 in store credit for the lamp, with a note that you approved it yourself."
          },
          {
            label: "Refund her in full",
            result:
              "Refunded Dana $180 for the lamp and logged it as a one-off exception."
          },
          {
            label: "Decline, kindly",
            result:
              "Declined Dana's late return gently, and sent her the care guide for the lamp."
          }
        ]
      },
      {
        id: "discount-call",
        agent: "Leed",
        context: "Call with Priya M.",
        question: "Priya will buy the full dining set today at 20% off.",
        why: "Your discount rule stops at 10% under $3,000. This order is $2,860.",
        flaggedEntryId: "discount-call",
        choices: [
          {
            label: "10% off plus free delivery",
            suggested: true,
            result:
              "Called Priya back with 10% off and free delivery. She took it: $2,574, paid."
          },
          {
            label: "Allow 20% this once",
            result:
              "Called Priya back with 20% off. Order placed at $2,288, flagged as an exception."
          },
          {
            label: "Hold the price",
            result:
              "Told Priya the price stands, and set a reminder to call her before the autumn sale."
          }
        ]
      }
    ],
    allClear: "Two calls made, and the store took care of the rest."
  },
  {
    id: "construction",
    name: "Site to books",
    business: "Ridgeline Builders",
    descriptor: "Residential builder · three live sites",
    tenant: "ridgeline-builders",
    agents: ["Sito", "Tali", "Insi"],
    pipeline: [
      { kind: "source", label: "WhatsApp groups" },
      { kind: "source", label: "Site photos" },
      { kind: "agent", agent: "Sito" },
      { kind: "agent", agent: "Tali" },
      { kind: "destination", label: "Tally · Excel" },
      { kind: "agent", agent: "Insi" },
      { kind: "destination", label: "Dashboards · invoices" }
    ],
    metrics: [
      { value: "212", label: "site messages read" },
      { value: "46", label: "photos turned into records" },
      { value: "78%", label: "of Site B budget used", bar: 78 }
    ],
    log: [
      {
        id: "pour",
        agent: "Sito",
        time: "07:12",
        text: "Read 64 messages in the Site B group. Logged the Level 2 slab pour as complete and filed the photos against it.",
        outcome: { label: "Logged", tone: "ok" },
        attachments: ["IMG_4471.jpg", "IMG_4472.jpg", "+10 more"]
      },
      {
        id: "delivery-note",
        agent: "Sito",
        time: "07:40",
        text: "Turned a photo of a crumpled delivery note into a line item: 40 bags of cement, $620, Site A.",
        outcome: { label: "Extracted", tone: "ok" },
        attachments: ["delivery-note.jpg"]
      },
      {
        id: "invoice",
        agent: "Tali",
        time: "08:05",
        text: "Raised progress invoice #218 to the Hendersons for the Level 2 slab, with the sign-off photos attached.",
        outcome: { label: "Sent · $18,400", tone: "ok" },
        attachments: ["INV-218.pdf"]
      },
      {
        id: "dashboards",
        agent: "Insi",
        time: "08:20",
        text: "Updated all three site dashboards. Site B is 78% through its budget and 64% through the work.",
        outcome: { label: "Heads up", tone: "warn" }
      },
      {
        id: "timber",
        agent: "Tali",
        time: "08:26",
        text: "Matched 18 supplier bills against site records in Tally. One doesn't add up. Held it for you.",
        outcome: WAITING
      },
      {
        id: "variation",
        agent: "Sito",
        time: "08:34",
        text: "The plumber on Site C mentioned extra work the client asked for. Held it for you.",
        outcome: WAITING,
        attachments: ["voice-note.m4a"]
      }
    ],
    decisions: [
      {
        id: "timber",
        agent: "Tali",
        context: "Apex Timber · bill 5531",
        question: "Apex billed 120 studs. Site A only logged 96.",
        why: "Tuesday's photo from the site shows one pallet. The difference is $310.",
        flaggedEntryId: "timber",
        choices: [
          {
            label: "Pay for 96, query the rest",
            suggested: true,
            result:
              "Paid Apex for 96 studs and sent them Tuesday's photo asking about the other 24."
          },
          {
            label: "Pay the full bill",
            result: "Paid Apex in full and noted the 24-stud gap against Site A in Tally."
          },
          {
            label: "Ask the foreman first",
            result:
              "Asked Mike in the Site A group to count the studs on site. The bill waits on his reply."
          }
        ]
      },
      {
        id: "variation",
        agent: "Sito",
        context: "Site C · 14 Harbour Rd",
        question: "The client asked the plumber for an extra bathroom point.",
        why: "It isn't in the contract. At your rates it's about $450 in labour and parts.",
        flaggedEntryId: "variation",
        choices: [
          {
            label: "Raise a $450 variation",
            suggested: true,
            result:
              "Sent the client a $450 variation to approve, and told the plumber to wait for sign-off."
          },
          {
            label: "Absorb it this time",
            result:
              "Told the plumber to go ahead and logged it as a goodwill extra on Site C."
          },
          {
            label: "I'll call the client",
            result:
              "Put the client's number at the top of your day and paused the extra work until you've spoken."
          }
        ]
      }
    ],
    allClear: "The sites, the books and the dashboards all agree with each other."
  },
  {
    id: "staffing",
    name: "Shifts and cover",
    business: "Brightside Care",
    descriptor: "Home care staffing · 140 carers, 9 sites",
    tenant: "brightside-care",
    agents: ["Kall", "Rota", "Insi"],
    pipeline: [
      { kind: "source", label: "Calls & texts" },
      { kind: "agent", agent: "Kall" },
      { kind: "agent", agent: "Rota" },
      { kind: "destination", label: "UKG · Excel" },
      { kind: "agent", agent: "Insi" },
      { kind: "destination", label: "Payroll" }
    ],
    metrics: [
      { value: "3", label: "sick calls handled" },
      { value: "212", label: "shifts scheduled" },
      { value: "98%", label: "of next week filled", bar: 98 }
    ],
    log: [
      {
        id: "sick-call",
        agent: "Kall",
        time: "05:12",
        text: "Took a sick call from Priya for her 7am shift at Maple House and logged it in UKG as unplanned leave.",
        outcome: { label: "Logged", tone: "ok" }
      },
      {
        id: "cover",
        agent: "Rota",
        time: "05:19",
        text: "Texted four qualified carers about Priya's shift. Marcus said yes at 05:19 and is on the rota.",
        outcome: { label: "Covered", tone: "ok" }
      },
      {
        id: "publish",
        agent: "Rota",
        time: "06:00",
        text: "Published next week's schedule: 212 shifts across nine sites, nobody over 48 hours.",
        outcome: { label: "Published", tone: "ok" },
        attachments: ["rota-week-39.xlsx"]
      },
      {
        id: "swaps",
        agent: "Rota",
        time: "06:30",
        text: "Approved two shift swaps that met your rules and updated the timesheets.",
        outcome: { label: "Updated", tone: "neutral" }
      },
      {
        id: "night-shift",
        agent: "Rota",
        time: "06:41",
        text: "Tonight's 10pm shift at Elm Court is still open. Held it for you.",
        outcome: WAITING
      },
      {
        id: "pattern",
        agent: "Insi",
        time: "06:55",
        text: "Spotted a pattern in this month's absences. Held it for you.",
        outcome: WAITING
      }
    ],
    decisions: [
      {
        id: "night-shift",
        agent: "Rota",
        context: "Elm Court · 22:00–07:00",
        question: "Nobody has taken tonight's 10pm shift yet.",
        why: "Five carers declined. Jo is qualified, but this would take her to 52 hours, over your 48-hour limit.",
        flaggedEntryId: "night-shift",
        choices: [
          {
            label: "Book an agency carer",
            suggested: true,
            result:
              "Booked an agency carer for Elm Court tonight and sent her the site notes and door code."
          },
          {
            label: "Offer Jo overtime",
            result:
              "Offered Jo the shift at time and a half. She accepted, and the overtime is flagged for payroll."
          },
          {
            label: "I'll sort it myself",
            result:
              "Left the shift open with you, and will remind you at 4pm if it's still empty."
          }
        ]
      },
      {
        id: "pattern",
        agent: "Insi",
        context: "Absence report · September",
        question: "Sam has called in sick three Mondays in a row.",
        why: "Your policy suggests a return-to-work chat after three absences in a month.",
        flaggedEntryId: "pattern",
        choices: [
          {
            label: "Book a chat with Sam's manager",
            suggested: true,
            result:
              "Booked a 15-minute check-in for Sam and his manager on Thursday, framed as support."
          },
          {
            label: "Log it, no action yet",
            result:
              "Logged the pattern on Sam's record. I'll mention it again only if it continues."
          },
          {
            label: "I'll talk to Sam",
            result:
              "Added a note to your Thursday to catch Sam, with his last three rotas attached."
          }
        ]
      }
    ],
    allClear: "Every shift for the next week has a name next to it."
  },
  {
    id: "social",
    name: "Social and content",
    business: "Loop & Linen",
    descriptor: "Shopify textile brand · founder-run",
    tenant: "loop-and-linen",
    agents: ["Ora", "Floc", "Eko", "Insi"],
    pipeline: [
      { kind: "source", label: "Shopify catalog" },
      { kind: "agent", agent: "Ora" },
      { kind: "agent", agent: "Floc" },
      { kind: "agent", agent: "Eko" },
      { kind: "destination", label: "Instagram · TikTok · Pinterest" },
      { kind: "agent", agent: "Insi" }
    ],
    metrics: [
      { value: "9", label: "posts scheduled" },
      { value: "126", label: "comments answered" },
      { value: "3×", label: "reels vs photos, last week" }
    ],
    log: [
      {
        id: "product-pages",
        agent: "Floc",
        time: "07:05",
        text: "Wrote product pages for the three new throws in your voice, with care instructions from the supplier sheet.",
        outcome: { label: "Published", tone: "ok" }
      },
      {
        id: "moodboard",
        agent: "Ora",
        time: "07:30",
        text: "Built this week's moodboard around rust, oat and morning light. Twelve images are ready for posts.",
        outcome: { label: "Ready", tone: "ok" },
        attachments: ["autumn-board.png", "+11 more"]
      },
      {
        id: "comments",
        agent: "Eko",
        time: "08:10",
        text: "Replied to 126 comments overnight and passed two delivery complaints to Kall.",
        outcome: { label: "Answered", tone: "ok" }
      },
      {
        id: "plan",
        agent: "Insi",
        time: "08:25",
        text: "Reels beat photos three to one last week, so next week's plan leans into reels.",
        outcome: { label: "Plan updated", tone: "neutral" }
      },
      {
        id: "creator",
        agent: "Eko",
        time: "08:38",
        text: "A creator asked for a free throw in exchange for a review. Held it for you.",
        outcome: WAITING
      },
      {
        id: "caption",
        agent: "Floc",
        time: "08:44",
        text: "Friday's launch caption is down to two options. Held it for you.",
        outcome: WAITING
      }
    ],
    decisions: [
      {
        id: "caption",
        agent: "Floc",
        context: "Friday · autumn launch",
        question: "Which of these sounds more like you?",
        why: "Both are written from your last 40 posts. The first matches your best-performing tone.",
        flaggedEntryId: "caption",
        choices: [
          {
            label: "“Slow mornings, softer linen.”",
            suggested: true,
            result:
              "Locked in “Slow mornings, softer linen.” for Friday, paired with Ora's oat throw reel."
          },
          {
            label: "“Our softest linen yet, in three new colours.”",
            result:
              "Locked in the product-led caption for Friday and moved the moodboard reel to Sunday."
          },
          {
            label: "Show me a third",
            result:
              "Wrote a third option and slotted it into Friday for you to glance at over coffee."
          }
        ]
      },
      {
        id: "creator",
        agent: "Eko",
        context: "DM from @thesoftedit · 48k followers",
        question: "A creator wants a free throw in exchange for a review.",
        why: "Her audience looks like your buyers. Your gifting budget has $220 left this month.",
        flaggedEntryId: "creator",
        choices: [
          {
            label: "Send the oat throw",
            suggested: true,
            result:
              "Sent @thesoftedit the oat throw with a handwritten-style note, and set a reminder to share her review."
          },
          {
            label: "Offer a 30% code instead",
            result:
              "Offered @thesoftedit a 30% code for her audience. She accepted, and it's tracked in Shopify."
          },
          {
            label: "Politely pass",
            result: "Thanked @thesoftedit warmly and said you're not gifting this season."
          }
        ]
      }
    ],
    allClear: "The week's feed is full, and it all sounds like you."
  }
];
