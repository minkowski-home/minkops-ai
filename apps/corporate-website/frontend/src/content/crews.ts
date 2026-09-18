import { getAgent } from "./agents";

/**
 * Crews: ready-made teams built around a role a business would otherwise
 * hire a person for. They're the second way to hire on the roster, next to
 * picking employees one by one. A crew is only a named group of roster
 * members; hiring one adds its members to the visitor's team.
 */
export type Crew = {
  id: string;
  name: string;
  /** The hire this crew stands in for, finishing the sentence "Does the job of…". */
  replaces: string;
  pitch: string;
  members: readonly string[];
  /** Three concrete things the crew takes off your plate. */
  covers: readonly string[];
};

export const CREWS: readonly Crew[] = [
  {
    id: "front-desk",
    name: "Front desk crew",
    replaces: "a receptionist and a support rep",
    pitch: "The inbox and the support queue, handled before you've had your coffee.",
    members: ["Imel", "Kall"],
    covers: [
      "Every email read, sorted, and answered or drafted",
      "Support tickets and calls resolved start to finish",
      "Returns and refunds handled inside your policy"
    ]
  },
  {
    id: "online-store",
    name: "Online store crew",
    replaces: "an e-commerce operations manager",
    pitch: "Everything a Shopify store needs between the order and the five-star review.",
    members: ["Imel", "Kall", "Leed", "Kim"],
    covers: [
      "Order questions answered with the real tracking link",
      "Abandoned carts called back within minutes",
      "Stock counted and reorders flagged before you run out"
    ]
  },
  {
    id: "social-media",
    name: "Social media crew",
    replaces: "a social media manager",
    pitch: "A feed that stays full and sounds like you, without you writing a word.",
    members: ["Ora", "Floc", "Eko", "Insi"],
    covers: [
      "Visuals and captions planned a week ahead",
      "Comments answered, complaints passed to support",
      "A Monday note on what worked and what to do more of"
    ]
  },
  {
    id: "staffing-desk",
    name: "Staffing desk",
    replaces: "a staffing clerk",
    pitch: "Rotas built, sick calls covered, and the timesheets already match.",
    members: ["Kall", "Rota", "Insi"],
    covers: [
      "Sick calls taken and logged at 5am, not 9am",
      "Open shifts filled from qualified staff, inside your hour limits",
      "UKG, spreadsheets and payroll kept in step"
    ]
  },
  {
    id: "site-office",
    name: "Site office crew",
    replaces: "a site administrator and a bookkeeper",
    pitch: "From the site WhatsApp group to the books, without anyone retyping a thing.",
    members: ["Sito", "Tali", "Insi"],
    covers: [
      "Site messages and photos turned into proper records",
      "Supplier bills checked against what actually arrived",
      "Budgets, dashboards and progress invoices kept current"
    ]
  },
  {
    id: "restaurant",
    name: "Restaurant crew",
    replaces: "your shift manager's busiest hours",
    pitch: "Counter, pass and kitchen in step from open to close.",
    members: ["Hosi", "Cruz", "Prex"],
    covers: [
      "Orders taken and sent straight to the kitchen",
      "Rush forecasts and prep lists ready before service",
      "Every ticket tracked until it leaves the pass"
    ]
  }
];

// Fail loudly at load time if a crew names someone who isn't on the roster.
CREWS.forEach((crew) => crew.members.forEach((name) => getAgent(name)));
