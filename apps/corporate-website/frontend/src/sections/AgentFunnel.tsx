import { useRef, useState } from "react";
import {
  QUESTIONS,
  RECOVERY_BAND,
  buildResult,
  type FunnelAnswers,
  type FunnelResult,
  type WorkArea
} from "../content/funnel";
import { ACCESS_HREF, ANCHORS } from "../content/site";
import { Section } from "../layout/Section";
import { Icon } from "../ui/Icon";
import { OptionRow, ProgressSteps } from "../ui/forms";
import { Badge, Button, ButtonLink, Card, Eyebrow } from "../ui/primitives";

type Props = {
  /** Lets the access form pre-select the area the visitor cares about most. */
  onRecommendation?: (area: WorkArea) => void;
};

function selectionFor(answers: FunnelAnswers, index: number): string[] {
  const question = QUESTIONS[index];
  const previous = answers[question.id];
  if (Array.isArray(previous)) return previous;
  return previous ? [previous] : [];
}

function Results({ result, onRestart }: { result: FunnelResult; onRestart: () => void }) {
  const { primary, supporting } = result;
  const fillPercent = Math.round((result.recovered.high / result.reportedHours) * 100);

  return (
    <div className="mk-funnel__results mk-enter" aria-live="polite">
      <div className="mk-funnel__results-head">
        <Badge tone="ok">Your answer</Badge>
        <span className="mk-funnel__stage">{result.stageLabel}</span>
      </div>

      <h3 className="mk-funnel__results-title">
        That's <span className="mk-accent">{result.recoveredLabel}</span> a week you could
        have back.
      </h3>

      <Card tone="sunken" className="mk-funnel__recovery">
        <div className="mk-funnel__recovery-row">
          <Eyebrow>Estimated hours back each week</Eyebrow>
          <strong className="mk-funnel__recovery-figure">
            {result.recovered.low === result.recovered.high
              ? `${result.recovered.high} hr`
              : `${result.recovered.low}–${result.recovered.high} hrs`}
          </strong>
        </div>
        <div className="mk-funnel__bar" aria-hidden="true">
          <span style={{ width: `${fillPercent}%` }} />
        </div>
        <p className="mk-funnel__basis">
          You told us {result.reportedBand} a week. We worked from {result.reportedHours}{" "}
          and assumed an AI employee takes on {Math.round(RECOVERY_BAND.low * 100)}–
          {Math.round(RECOVERY_BAND.high * 100)}% of it. We&apos;d rather under-promise.
        </p>
      </Card>

      <Card as="article" className="mk-funnel__primary">
        <div className="mk-funnel__agent-head">
          <span className="mk-glyph-tile">
            <Icon name={primary.agent.glyph} size={22} />
          </span>
          <span className="mk-funnel__agent-id">
            <Eyebrow>Who we'd hire first</Eyebrow>
            <span className="mk-funnel__agent-name">{primary.agent.name}</span>
            <span className="mk-funnel__agent-role">{primary.agent.role}</span>
          </span>
          <Badge tone="approval" className="mk-funnel__agent-status">
            Ready for work
          </Badge>
        </div>
        <p className="mk-funnel__pitch">{primary.pitch}</p>
        <p className="mk-funnel__saving">Typically {primary.typicalSaving}</p>
        <p className="mk-funnel__honest">
          {primary.agent.name} doesn&apos;t work alone. Whatever it can&apos;t decide goes
          to the teammate who can, and only the calls above everyone&apos;s authority come
          to you.
        </p>
      </Card>

      {supporting.length > 0 ? (
        <div className="mk-funnel__supporting">
          <Eyebrow>Then, when you're ready</Eyebrow>
          <ul className="mk-funnel__supporting-list">
            {supporting.map((item) => (
              <li key={item.agent.name}>
                <Card tone="sunken" className="mk-funnel__support-card">
                  <span className="mk-funnel__support-name">{item.agent.name}</span>
                  <span className="mk-funnel__agent-role">{item.agent.role}</span>
                  <span className="mk-funnel__support-meta">
                    {item.agent.department} · {item.typicalSaving}
                  </span>
                </Card>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mk-funnel__actions">
        <ButtonLink to={ACCESS_HREF} size="lg" variant="primary">
          Save me a spot
        </ButtonLink>
        <Button size="lg" variant="ghost" onClick={onRestart}>
          Start over
        </Button>
        <span className="mk-funnel__note">
          Free to join. No sales call unless you ask.
        </span>
      </div>
    </div>
  );
}

export default function AgentFunnel({ onRecommendation }: Props) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<FunnelAnswers>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<FunnelResult | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const question = QUESTIONS[step];
  const isLast = step === QUESTIONS.length - 1;

  const goTo = (index: number, nextAnswers: FunnelAnswers) => {
    setStep(index);
    setSelected(selectionFor(nextAnswers, index));
    // Keep the question in view on small screens, where the panel is taller than the viewport.
    panelRef.current?.scrollIntoView({ block: "nearest" });
  };

  const toggle = (value: string) => {
    setSelected((current) => {
      if (question.kind === "single") return [value];
      return current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value];
    });
  };

  const advance = () => {
    const value = question.kind === "multi" ? selected : selected[0];
    const nextAnswers = { ...answers, [question.id]: value };
    setAnswers(nextAnswers);

    if (!isLast) {
      goTo(step + 1, nextAnswers);
      return;
    }

    const computed = buildResult(nextAnswers);
    setResult(computed);
    onRecommendation?.(computed.primaryArea);
    panelRef.current?.scrollIntoView({ block: "nearest" });
  };

  const restart = () => {
    setAnswers({});
    setResult(null);
    goTo(0, {});
  };

  return (
    <Section
      id={ANCHORS.funnel}
      eyebrow="Find your first hire"
      title="Four questions. One straight answer."
      lead="Tell us where your hours leak and we'll tell you who we'd hire first, and roughly what you'd get back. It takes about ninety seconds, and nobody will call you afterwards. Worst case, it tells you Minkops isn't the right fit yet."
    >
      <div className="mk-funnel" ref={panelRef}>
        {result ? (
          <Results result={result} onRestart={restart} />
        ) : (
          <div className="mk-funnel__step" key={question.id}>
            <ProgressSteps
              total={QUESTIONS.length}
              current={step}
              label={`Question ${step + 1} of ${QUESTIONS.length}`}
            />
            <div className="mk-funnel__question">
              <Eyebrow>{question.kicker}</Eyebrow>
              <h3 className="mk-funnel__question-title" id={`q-${question.id}`}>
                {question.question}
              </h3>
              <p className="mk-funnel__subtext">
                {question.subtext}
                {question.kind === "multi" ? " Choose as many as you like." : ""}
              </p>
            </div>

            <div
              className="mk-funnel__options"
              role={question.kind === "multi" ? "group" : "radiogroup"}
              aria-labelledby={`q-${question.id}`}
            >
              {question.options.map((option) => (
                <OptionRow
                  key={option.value}
                  label={option.label}
                  meta={option.meta}
                  multi={question.kind === "multi"}
                  selected={selected.includes(option.value)}
                  onSelect={() => toggle(option.value)}
                />
              ))}
            </div>

            <div className="mk-funnel__nav">
              <Button
                size="lg"
                variant="primary"
                disabled={selected.length === 0}
                onClick={advance}
                iconRight={<Icon name="chevronRight" size={16} />}
              >
                {isLast ? "Show me who to hire" : "Next question"}
              </Button>
              {step > 0 ? (
                <Button
                  variant="ghost"
                  size="lg"
                  onClick={() => goTo(step - 1, answers)}
                  iconLeft={<Icon name="chevronLeft" size={14} />}
                >
                  Back
                </Button>
              ) : null}
              <span className="mk-funnel__count">
                {step + 1} / {QUESTIONS.length}
              </span>
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}
