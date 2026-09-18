/** Site-wide facts. Anything a visitor might copy (emails, address) lives here once. */
export const SITE = {
  name: "Minkops",
  url: "https://minkops.com",
  emails: {
    general: "info@minkops.com",
    hr: "hr@minkops.com"
  },
  address: [
    "Minkops AI",
    "375 University Avenue Suite 3273",
    "Toronto, ON M5G 2J5",
    "Canada"
  ],
  links: {
    linkedin: "https://linkedin.com/company/minkops",
    myndral: "https://app.myndral.com",
    minkowskiHome: "https://minkowskihome.com"
  }
} as const;

/** In-page anchors shared between the nav, the funnel and the access section. */
export const ANCHORS = {
  access: "access",
  funnel: "find-your-stack",
  roster: "roster"
} as const;

export const ACCESS_HREF = `/#${ANCHORS.access}`;
export const FUNNEL_HREF = `/#${ANCHORS.funnel}`;
