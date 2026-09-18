import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes
} from "react";
import { cx } from "./primitives";

/* Form controls from design/components/forms, styled via ui.css. */

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required = false,
  children
}: {
  label: string;
  htmlFor: string;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="mk-field">
      <label className="mk-field__label" htmlFor={htmlFor}>
        {label}
        {required ? (
          <span className="mk-field__required" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p className="mk-field__error" id={`${htmlFor}-error`} role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="mk-field__hint" id={`${htmlFor}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function Input({
  invalid = false,
  className,
  ...rest
}: { invalid?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx("mk-control", invalid && "is-invalid", className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
}

export function Textarea({
  invalid = false,
  className,
  rows = 4,
  ...rest
}: { invalid?: boolean } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      rows={rows}
      className={cx(
        "mk-control",
        "mk-control--textarea",
        invalid && "is-invalid",
        className
      )}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
}

export function Select({
  options,
  className,
  ...rest
}: {
  options: ReadonlyArray<{ value: string; label: string }>;
} & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={cx("mk-select", className)}>
      <select className="mk-control mk-control--select" {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <svg
        className="mk-select__chevron"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M6 9l6 6 6-6" />
      </svg>
    </div>
  );
}

/**
 * One answer in a questionnaire. Rendered as a real checkbox/radio role so
 * screen readers announce state; the visual indicator mirrors it.
 */
export function OptionRow({
  label,
  meta,
  selected,
  multi,
  onSelect
}: {
  label: string;
  meta?: string;
  selected: boolean;
  multi: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role={multi ? "checkbox" : "radio"}
      aria-checked={selected}
      onClick={onSelect}
      className={cx("mk-option", selected && "is-selected")}
    >
      <span
        className={cx(
          "mk-option__mark",
          multi ? "mk-option__mark--square" : "mk-option__mark--round"
        )}
        aria-hidden="true"
      >
        {selected ? (
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="3.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : null}
      </span>
      <span className="mk-option__text">
        <span className="mk-option__label">{label}</span>
        {meta ? <span className="mk-option__meta">{meta}</span> : null}
      </span>
    </button>
  );
}

export function ProgressSteps({
  total,
  current,
  label
}: {
  total: number;
  current: number;
  label: string;
}) {
  return (
    <div
      className="mk-steps"
      role="progressbar"
      aria-label={label}
      aria-valuenow={current + 1}
      aria-valuemin={1}
      aria-valuemax={total}
    >
      {Array.from({ length: total }, (_, index) => (
        <span
          key={index}
          className={cx("mk-steps__seg", index <= current && "is-done")}
        />
      ))}
    </div>
  );
}
