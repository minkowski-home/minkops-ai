import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import type { WorkArea } from "../content/funnel";
import type { Team } from "../content/team";
import { SITE } from "../content/site";
import { Field, Input, Select, Textarea } from "../ui/forms";
import { Badge, Button, Card } from "../ui/primitives";

/*
 * Waitlist form.
 *
 * KNOWN LIMITATION: submissions are not persisted or sent anywhere yet. There
 * is no form backend for the marketing site (see apps/corporate-website/README.md,
 * "Known limitations"). The form validates, then shows its confirmation state.
 * When a backend lands, replace `submitInterest` with the real request; the
 * component already models submitting / error states around it.
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
};

type Errors = Partial<Record<"name" | "email", string>>;

const EMPTY: FormState = {
  name: "",
  email: "",
  company: "",
  interest: "unsure",
  message: ""
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

/**
 * Placeholder transport. See the KNOWN LIMITATION note at the top of this file.
 * The payload already carries the team built on the roster, so a real backend
 * receives everything the visitor chose.
 */
async function submitInterest(payload: FormState & { team: Team }): Promise<void> {
  void payload;
}

export default function InterestForm({
  suggestedArea,
  team = []
}: {
  suggestedArea?: WorkArea;
  team?: Team;
}) {
  const [state, setState] = useState<FormState>(EMPTY);
  const [errors, setErrors] = useState<Errors>({});
  const [status, setStatus] = useState<"idle" | "submitting" | "sent" | "failed">("idle");

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
      await submitInterest({ ...state, team });
      setStatus("sent");
    } catch {
      setStatus("failed");
    }
  };

  const firstName = state.name.trim().split(/\s+/)[0];

  if (status === "sent") {
    return (
      <Card className="mk-interest mk-interest--sent" aria-live="polite">
        <Badge tone="ok">You're on the list</Badge>
        <h3 className="mk-interest__title">Thanks, {firstName}.</h3>
        <p className="mk-interest__body">
          We're opening Minkops a few businesses at a time, and we set each one up by
          hand. When it's your turn, you'll hear from a person, not a drip campaign.
        </p>
        <p className="mk-interest__body">
          Can't wait? Write to{" "}
          <a href={`mailto:${SITE.emails.general}`}>{SITE.emails.general}</a>. Imel will
          read it first, and one of us will reply.
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

        {team.length > 0 ? (
          <div className="mk-interest__team">
            <p className="mk-field__label">Your shortlist</p>
            <p className="mk-interest__team-list">{team.join(" · ")}</p>
            <p className="mk-field__hint">
              We&apos;ll come to the conversation ready to talk about these {team.length}.
              Change them in the roster above.
            </p>
          </div>
        ) : null}

        {status === "failed" ? (
          <p className="mk-interest__error" role="alert">
            That didn't go through on our side. Please try again, or write to{" "}
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
          {status === "submitting"
            ? "Sending…"
            : team.length > 0
              ? "Book a conversation"
              : "Put me on the list"}
        </Button>
      </form>
    </Card>
  );
}
