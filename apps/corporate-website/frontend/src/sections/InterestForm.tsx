import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import type { WorkArea } from "../content/funnel";
import { SITE } from "../content/site";
import { Field, Input, Select, Textarea } from "../ui/forms";
import { Badge, Button, Card } from "../ui/primitives";

const PUBLIC_PRODUCTION_INTEREST_API_URL =
  "https://minkops-interest-api-330283498133.us-central1.run.app/api/interest";
const CANONICAL_PRODUCTION_HOSTS = new Set(["minkops.com", "www.minkops.com"]);
const configuredInterestApiUrl = import.meta.env.VITE_INTEREST_API_URL?.trim();
const currentHost = typeof window === "undefined" ? "" : window.location.hostname;
const INTEREST_API_URL =
  configuredInterestApiUrl ||
  (import.meta.env.DEV
    ? "/api/interest"
    : CANONICAL_PRODUCTION_HOSTS.has(currentHost)
      ? PUBLIC_PRODUCTION_INTEREST_API_URL
      : undefined);

/*
 * Waitlist form. The API returns acceptance only after the configured email
 * provider accepts the submission; see the API README for delivery limits.
 */

type InterestValue =
  | "unsure"
  | "email"
  | "support"
  | "sales"
  | "marketing"
  | "operations"
  | "custom";

const INTEREST_OPTIONS: ReadonlyArray<{ value: InterestValue; label: string }> = [
  { value: "unsure", label: "Not sure yet, that's partly why I'm here" },
  { value: "email", label: "Email and the inbox" },
  { value: "support", label: "Customer support" },
  { value: "sales", label: "Sales and lead follow-up" },
  { value: "marketing", label: "Marketing, social and content" },
  { value: "operations", label: "Reporting and operations" },
  { value: "custom", label: "Something bigger. Let's talk." }
];

/** Maps a funnel recommendation onto the closest form option. */
const AREA_TO_INTEREST: Record<WorkArea, InterestValue> = {
  support: "support",
  leads: "sales",
  email: "email",
  social: "marketing",
  ads: "marketing",
  analytics: "operations"
};

type FormState = {
  name: string;
  email: string;
  company: string;
  interest: InterestValue;
  message: string;
  website: string;
};

type Errors = Partial<Record<"name" | "email", string>>;

class InterestApiUnavailableError extends Error {}

const EMPTY: FormState = {
  name: "",
  email: "",
  company: "",
  interest: "unsure",
  message: "",
  website: ""
};

// Deliberately permissive: the browser's own check plus "something@something.tld".
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validate(state: FormState): Errors {
  const errors: Errors = {};
  if (!state.name.trim()) errors.name = "We'd love to know what to call you.";
  if (!state.email.trim()) {
    errors.email = "We need an email to reach you. Nothing else goes to it.";
  } else if (!EMAIL_PATTERN.test(state.email.trim())) {
    errors.email = "That email doesn't look quite right. Mind checking it?";
  }
  return errors;
}

/** Sends the visitor's request and requires explicit provider acceptance. */
async function submitInterest(payload: FormState): Promise<void> {
  if (!INTEREST_API_URL) {
    throw new InterestApiUnavailableError();
  }

  const response = await fetch(INTEREST_API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok) throw new Error("The request was not accepted");
  const result: unknown = await response.json();
  if (
    typeof result !== "object" ||
    result === null ||
    !("status" in result) ||
    result.status !== "accepted"
  ) {
    throw new Error("The delivery service did not confirm acceptance");
  }
}

export default function InterestForm({ suggestedArea }: { suggestedArea?: WorkArea }) {
  const [state, setState] = useState<FormState>(EMPTY);
  const [errors, setErrors] = useState<Errors>({});
  const [status, setStatus] = useState<
    "idle" | "submitting" | "sent" | "failed" | "unavailable"
  >("idle");

  // When the visitor finishes the funnel, pre-select what it recommended,
  // unless they've already chosen something themselves.
  useEffect(() => {
    if (!suggestedArea) return;
    setState((current) =>
      current.interest === "unsure"
        ? { ...current, interest: AREA_TO_INTEREST[suggestedArea] }
        : current
    );
  }, [suggestedArea]);

  const update =
    (key: keyof FormState) =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const value = event.target.value;
      setState((current) => ({ ...current, [key]: value }));
      if (key in errors) setErrors((current) => ({ ...current, [key]: undefined }));
    };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors = validate(state);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      const firstInvalid = nextErrors.name ? "interest-name" : "interest-email";
      document.getElementById(firstInvalid)?.focus();
      return;
    }

    setStatus("submitting");
    try {
      await submitInterest(state);
      setStatus("sent");
    } catch (error) {
      setStatus(error instanceof InterestApiUnavailableError ? "unavailable" : "failed");
    }
  };

  const firstName = state.name.trim().split(/\s+/)[0];

  if (status === "sent") {
    return (
      <Card className="mk-interest mk-interest--sent" aria-live="polite">
        <Badge tone="ok">You're on the list</Badge>
        <h3 className="mk-interest__title">Thanks, {firstName}.</h3>
        <p className="mk-interest__body">
          Our email service accepted your note for delivery. We can&apos;t confirm when it
          reaches the inbox, but you&apos;ve given us a way to follow up.
        </p>
        <p className="mk-interest__body">
          Can't wait? Write to{" "}
          <a href={`mailto:${SITE.emails.general}`}>{SITE.emails.general}</a>. One of us
          will reply.
        </p>
      </Card>
    );
  }

  return (
    <Card className="mk-interest">
      <div className="mk-interest__head">
        <h3 className="mk-interest__title">Get on the list</h3>
        <p className="mk-interest__body">
          Tell us a little about your business and where the hours go. Two fields are
          required; the rest just helps us come prepared.
        </p>
      </div>

      <form className="mk-interest__form" onSubmit={onSubmit} noValidate>
        <div className="mk-interest__trap" aria-hidden="true">
          <label htmlFor="interest-website">Website</label>
          <input
            id="interest-website"
            name="website"
            value={state.website}
            onChange={update("website")}
            autoComplete="off"
            tabIndex={-1}
          />
        </div>
        <Field label="Your name" htmlFor="interest-name" required error={errors.name}>
          <Input
            id="interest-name"
            name="name"
            autoComplete="name"
            value={state.name}
            onChange={update("name")}
            invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? "interest-name-error" : undefined}
            required
          />
        </Field>

        <Field label="Work email" htmlFor="interest-email" required error={errors.email}>
          <Input
            id="interest-email"
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            placeholder="you@yourstore.com"
            value={state.email}
            onChange={update("email")}
            invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? "interest-email-error" : undefined}
            required
          />
        </Field>

        <Field label="Store or company" htmlFor="interest-company">
          <Input
            id="interest-company"
            name="company"
            autoComplete="organization"
            value={state.company}
            onChange={update("company")}
          />
        </Field>

        <Field label="What would you hand off first?" htmlFor="interest-area">
          <Select
            id="interest-area"
            name="interest"
            value={state.interest}
            onChange={update("interest")}
            options={INTEREST_OPTIONS}
          />
        </Field>

        <Field
          label="Anything else we should know?"
          htmlFor="interest-message"
          hint="Optional. The messier your week sounds, the more useful it is to us."
        >
          <Textarea
            id="interest-message"
            name="message"
            rows={3}
            placeholder="The job I'd hand off first is…"
            value={state.message}
            onChange={update("message")}
            aria-describedby="interest-message-hint"
          />
        </Field>

        {status === "unavailable" ? (
          <p className="mk-interest__error" role="alert">
            This form isn't connected on this site yet. Please email us instead: {" "}
            <a href={`mailto:${SITE.emails.general}`}>{SITE.emails.general}</a>.
          </p>
        ) : null}

        {status === "failed" ? (
          <p className="mk-interest__error" role="alert">
            We couldn't confirm whether your note went through. Please email us and we'll
            check before you try again: {" "}
            <a href={`mailto:${SITE.emails.general}`}>{SITE.emails.general}</a>.
          </p>
        ) : null}

        <Button
          type="submit"
          variant="primary"
          size="lg"
          fullWidth
          disabled={status === "submitting"}
        >
          {status === "submitting" ? "Sending…" : "Put me on the list"}
        </Button>
      </form>
    </Card>
  );
}
