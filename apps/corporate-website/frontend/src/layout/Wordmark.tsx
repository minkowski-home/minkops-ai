import { cx } from "../ui/primitives";

/**
 * The Minkops lockup. There is no logo artwork: the brand is the type-set
 * lowercase wordmark (Readex Pro 700, -0.05em), optionally preceded by the
 * Ember dot, the only companion element the system permits.
 */
export default function Wordmark({
  inverse = false,
  withDot = true
}: {
  inverse?: boolean;
  withDot?: boolean;
}) {
  return (
    <span className={cx("mk-wordmark", inverse && "mk-wordmark--inverse")}>
      {withDot ? <span className="mk-wordmark__dot" aria-hidden="true" /> : null}
      <span className="mk-wordmark__text">minkops</span>
    </span>
  );
}
