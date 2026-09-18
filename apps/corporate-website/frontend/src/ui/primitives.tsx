import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  HTMLAttributes,
  ReactNode
} from "react";
import { Link, type LinkProps } from "react-router-dom";

/*
 * Core primitives from the Minkops design system (design/components/core),
 * rebuilt as typed components that style through classes in ui.css rather
 * than inline objects. That keeps hover/press/focus in CSS, where the
 * system's colour-only interaction rules can be expressed without JS state.
 */

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* ---- Button ------------------------------------------------------------ */

export type ButtonVariant = "primary" | "secondary" | "ghost" | "inverse";
export type ButtonSize = "sm" | "md" | "lg";

type ButtonStyleProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
  fullWidth?: boolean;
};

function buttonClass({
  variant = "primary",
  size = "md",
  fullWidth = false,
  className
}: ButtonStyleProps & { className?: string }) {
  return cx(
    "mk-btn",
    `mk-btn--${variant}`,
    `mk-btn--${size}`,
    fullWidth && "mk-btn--full",
    className
  );
}

export function Button({
  variant,
  size,
  iconLeft,
  iconRight,
  fullWidth,
  className,
  type = "button",
  children,
  ...rest
}: ButtonStyleProps & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      className={buttonClass({ variant, size, fullWidth, className })}
      {...rest}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
}

/**
 * A link that looks like a button. Internal routes go through react-router;
 * anything with a scheme (mailto:, https:) or a same-page hash renders a
 * plain anchor so the browser handles it natively.
 */
export function ButtonLink({
  to,
  variant,
  size,
  iconLeft,
  iconRight,
  fullWidth,
  className,
  children,
  ...rest
}: ButtonStyleProps & { to: string } & Omit<
    AnchorHTMLAttributes<HTMLAnchorElement>,
    "href"
  >) {
  const classes = buttonClass({ variant, size, fullWidth, className });
  const content = (
    <>
      {iconLeft}
      {children}
      {iconRight}
    </>
  );

  if (/^[a-z]+:/i.test(to)) {
    return (
      <a href={to} className={classes} {...rest}>
        {content}
      </a>
    );
  }

  return (
    <Link to={to} className={classes} {...(rest as Omit<LinkProps, "to">)}>
      {content}
    </Link>
  );
}

/* ---- Eyebrow ----------------------------------------------------------- */

/** The uppercase mono kicker: the brand's signature small-type device. */
export function Eyebrow({
  rule = false,
  inverse = false,
  className,
  children,
  ...rest
}: { rule?: boolean; inverse?: boolean } & HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cx("mk-eyebrow", inverse && "mk-eyebrow--inverse", className)}
      {...rest}
    >
      {children}
      {rule ? <span className="mk-eyebrow__rule" aria-hidden="true" /> : null}
    </p>
  );
}

/* ---- Badge ------------------------------------------------------------- */

export type BadgeTone = "neutral" | "approval" | "ok" | "warn" | "review";

export function Badge({
  tone = "neutral",
  className,
  children,
  ...rest
}: { tone?: BadgeTone } & HTMLAttributes<HTMLSpanElement>) {
  return (
    <span className={cx("mk-badge", `mk-badge--${tone}`, className)} {...rest}>
      {children}
    </span>
  );
}

/* ---- Card -------------------------------------------------------------- */

export type CardTone = "default" | "sunken" | "inverse";

/**
 * Hairline-bordered panel, 4px radius, no shadow. `accentEdge` (the 2px Ember
 * left edge) means "a human is needed here" and should be used for nothing else.
 */
export function Card({
  tone = "default",
  accentEdge = false,
  as: Tag = "div",
  className,
  children,
  ...rest
}: {
  tone?: CardTone;
  accentEdge?: boolean;
  as?: "div" | "article" | "section" | "aside" | "li";
} & HTMLAttributes<HTMLElement>) {
  return (
    <Tag
      className={cx(
        "mk-card",
        `mk-card--${tone}`,
        accentEdge && "mk-card--accent-edge",
        className
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/* ---- StatusDot --------------------------------------------------------- */

export type DotStatus = "active" | "idle" | "ok";

export function StatusDot({
  status = "idle",
  halo = false,
  label,
  className
}: {
  status?: DotStatus;
  /** A static halo ring. The system allows no looping animation on status. */
  halo?: boolean;
  label?: ReactNode;
  className?: string;
}) {
  return (
    <span className={cx("mk-status", className)}>
      <span
        className={cx("mk-status__dot", `mk-status__dot--${status}`, halo && "is-halo")}
        aria-hidden="true"
      />
      {label ? <span className="mk-status__label">{label}</span> : null}
    </span>
  );
}

/* ---- Avatar ------------------------------------------------------------ */

function initials(name: string) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
}

/** Agents get a graphite square; humans get a pale circle. */
export function Avatar({
  name,
  kind = "agent",
  size = 30
}: {
  name: string;
  kind?: "agent" | "human";
  size?: number;
}) {
  return (
    <span
      className={cx("mk-avatar", `mk-avatar--${kind}`)}
      style={{
        width: size,
        height: size,
        fontSize: Math.max(10, Math.round(size * 0.36))
      }}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}
