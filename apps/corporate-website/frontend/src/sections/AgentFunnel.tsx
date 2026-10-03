import { useRef, useState } from "react";
import {
  QUESTIONS,
  buildResult,
  type FunnelAnswers,
  type FunnelResult
} from "../content/funnel";
import { ACCESS_HREF, ANCHORS } from "../content/site";
import { Section } from "../layout/Section";
import { Icon } from "../ui/Icon";
import { OptionRow, ProgressSteps } from "../ui/forms";
import { Badge, Button, ButtonLink, Card, Eyebrow } from "../ui/primitives";

function selectionFor(answers: FunnelAnswers, index: number): string[] {
  const question = QUESTIONS[index];
  const previous = answers[question.id];
  if (Array.isArray(previous)) return previous;
  return previous ? [previous] : [];
}

function Results({ result, onRestart }: { result: FunnelResult; onRestart: () => void }) {
  const { primary, supporting } = result;

  return (
    <div className="mk-funnel__results mk-enter" aria-live="polite">
      <div className="mk-funnel__results-head">
        <Badge tone="review">Illustrative workflow</Badge>
        <span className="mk-funnel__stage">{result.businessLabel}</span>
      </div>

      <h3 className="mk-funnel__results-title">
        A workflow outline for <span className="mk-accent">{primary.name.toLowerCase()}</span>
      </h3>

      <Card as="article" className="mk-funnel__primary">
        <Eyebrow>Example steps to scope</Eyebrow>
        <h4 className="mk-funnel__workflow-name">{primary.name}</h4>
        <p className="mk-funnel__pitch">{primary.description}</p>
        <p className="mk-funnel__honest">
          This is an example outline, not a live integration or a promise of time saved.
          Actual access, tools and approval rules depend on your process.
        </p>
      </Card>

      {supporting.length > 0 ? (
        <div className="mk-funnel__supporting">
          <Eyebrow>Other workflow areas you selected</Eyebrow>
          <ul className="mk-funnel__supporting-list">
            {supporting.map((item) => (
              <li key={item.name}>
                <Card tone="sunken" className="mk-funnel__support-card">
                  <span className="mk-funnel__support-name">{item.name}</span>
                  <span className="mk-funnel__support-meta">Example workflow area</span>
                  <span className="mk-funnel__pitch">{item.description}</span>
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

export default function AgentFunnel() {
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
      eyebrow="Find a workflow starting point"
      title="Four questions. One straight answer."
      lead="Tell us about the process you want to improve, the work it involves and the tools you use. We’ll show an illustrative workflow outline; it is not a live integration or a time-saved estimate."
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
                {isLast ? "Show me a workflow outline" : "Next question"}
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
