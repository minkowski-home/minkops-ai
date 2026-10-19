import type { SVGProps } from "react";

// Active website glyphs follow design/components/core/Icon.jsx's 24px grid.
const GLYPHS = {
  chevronLeft: { stroke: 2, body: <path d="M15 18l-6-6 6-6" /> },
  chevronRight: { stroke: 2, body: <path d="M9 18l6-6-6-6" /> },
  check: { stroke: 2.2, body: <polyline points="20 6 9 17 4 12" /> }
};

type IconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: keyof typeof GLYPHS;
  size?: number;
};

/** Decorative by default (aria-hidden); pair with visible text for meaning. */
export function Icon({ name, size = 18, strokeWidth, className, ...rest }: IconProps) {
  const { stroke, body } = GLYPHS[name];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth ?? stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={["mk-icon", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {body}
    </svg>
  );
}
