/* @ds-bundle: {"format":4,"namespace":"MinkopsDesignSystem_6c27f0","components":[{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Eyebrow","sourcePath":"components/core/Eyebrow.jsx"},{"name":"Icon","sourcePath":"components/core/Icon.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"PriorityPill","sourcePath":"components/core/PriorityPill.jsx"},{"name":"StatusDot","sourcePath":"components/core/StatusDot.jsx"},{"name":"Toggle","sourcePath":"components/core/Toggle.jsx"},{"name":"EmptyState","sourcePath":"components/feedback/EmptyState.jsx"},{"name":"ProgressSteps","sourcePath":"components/feedback/ProgressSteps.jsx"},{"name":"TypingIndicator","sourcePath":"components/feedback/TypingIndicator.jsx"},{"name":"Field","sourcePath":"components/forms/Field.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"OptionRow","sourcePath":"components/forms/OptionRow.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Textarea","sourcePath":"components/forms/Textarea.jsx"},{"name":"AgentRow","sourcePath":"components/product/AgentRow.jsx"},{"name":"AgentTile","sourcePath":"components/product/AgentTile.jsx"},{"name":"FlowNode","sourcePath":"components/product/FlowNode.jsx"},{"name":"FlowArrow","sourcePath":"components/product/FlowNode.jsx"},{"name":"InterruptCard","sourcePath":"components/product/InterruptCard.jsx"},{"name":"MessageBubble","sourcePath":"components/product/MessageBubble.jsx"}],"sourceHashes":{"components/core/Avatar.jsx":"e98c841255c2","components/core/Badge.jsx":"595b8e2aa88d","components/core/Button.jsx":"60c69b70ff3c","components/core/Card.jsx":"1a4b36f3cb48","components/core/Eyebrow.jsx":"42e770519c8a","components/core/Icon.jsx":"72fef4cb1151","components/core/IconButton.jsx":"99569316721e","components/core/PriorityPill.jsx":"4a211ff7bb77","components/core/StatusDot.jsx":"abe3136974a2","components/core/Toggle.jsx":"6708c2c70dfa","components/feedback/EmptyState.jsx":"4c3bae4dae83","components/feedback/ProgressSteps.jsx":"ad940fed8171","components/feedback/TypingIndicator.jsx":"e4ebbe8e0dfe","components/forms/Field.jsx":"1b10436aee57","components/forms/Input.jsx":"2b27ed015983","components/forms/OptionRow.jsx":"394a2d72f00a","components/forms/Select.jsx":"84225b5800a4","components/forms/Textarea.jsx":"a98b1ec3683e","components/product/AgentRow.jsx":"ea42e926303a","components/product/AgentTile.jsx":"2b52dfd058e4","components/product/FlowNode.jsx":"0990c4adc789","components/product/InterruptCard.jsx":"12dc0f849d02","components/product/MessageBubble.jsx":"3c698aabe21a","ui_kits/console/AgentsPane.jsx":"88105ce3bfb5","ui_kits/console/AgentsScreen.jsx":"08982edb396e","ui_kits/console/AttentionQueue.jsx":"2f4685c3007e","ui_kits/console/ConsoleData.jsx":"b15014d5a734","ui_kits/console/ConsoleShell.jsx":"ac88a1d59ddf","ui_kits/console/LoginScreen.jsx":"ee3cc8499811","ui_kits/console/PlaceholderScreen.jsx":"0a0187d2e62a","ui_kits/console/TaskThread.jsx":"cfeaf97a7430","ui_kits/website/AccessSection.jsx":"c206eefb05b1","ui_kits/website/EditorialPages.jsx":"669893372f51","ui_kits/website/Funnel.jsx":"dbb4583c741e","ui_kits/website/Landing.jsx":"b0220575dacf","ui_kits/website/Orchestration.jsx":"4219201d43a1","ui_kits/website/SiteChrome.jsx":"2d1b349897a9"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.MinkopsDesignSystem_6c27f0 = window.MinkopsDesignSystem_6c27f0 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Avatar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function initials(name) {
  return String(name || "?").trim().split(/\s+/).slice(0, 2).map(w => w[0].toUpperCase()).join("");
}
function Avatar({
  name,
  kind = "agent",
  size = 30,
  square = true,
  style,
  ...rest
}) {
  const isAgent = kind === "agent";
  return /*#__PURE__*/React.createElement("span", _extends({
    title: name,
    style: {
      display: "grid",
      placeItems: "center",
      width: size,
      height: size,
      flex: "none",
      borderRadius: square ? "var(--radius-2)" : "50%",
      background: isAgent ? "var(--surface-inverse)" : "var(--surface-inset)",
      color: isAgent ? "var(--text-inverse)" : "var(--text-secondary)",
      border: isAgent ? "1px solid var(--surface-inverse)" : "1px solid var(--border-default)",
      font: "var(--fw-medium) " + Math.max(10, Math.round(size * 0.36)) + "px/1 var(--font-mono)",
      letterSpacing: "0.02em",
      ...style
    }
  }, rest), initials(name));
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TONES = {
  neutral: {
    color: "var(--text-secondary)",
    background: "var(--surface-inset)",
    border: "var(--border-default)"
  },
  approval: {
    color: "var(--brand-rust)",
    background: "var(--ember-tint-08)",
    border: "var(--ember-tint-24)"
  },
  escalation: {
    color: "var(--status-alert)",
    background: "var(--status-alert-fill)",
    border: "rgba(179,38,30,0.22)"
  },
  review: {
    color: "var(--status-info)",
    background: "var(--status-info-fill)",
    border: "var(--border-default)"
  },
  error: {
    color: "var(--status-alert)",
    background: "var(--status-alert-fill)",
    border: "rgba(179,38,30,0.22)"
  },
  ok: {
    color: "var(--status-ok)",
    background: "var(--status-ok-fill)",
    border: "rgba(31,111,69,0.2)"
  },
  warn: {
    color: "var(--status-warn)",
    background: "var(--status-warn-fill)",
    border: "rgba(138,98,18,0.22)"
  }
};
function Badge({
  tone = "neutral",
  mono = true,
  children,
  style,
  ...rest
}) {
  const t = TONES[tone] || TONES.neutral;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "5px",
      height: "20px",
      padding: "0 7px",
      borderRadius: "var(--radius-1)",
      font: mono ? "var(--fw-medium) var(--fs-micro)/1 var(--font-mono)" : "var(--fw-semibold) var(--fs-micro)/1 var(--font-text)",
      letterSpacing: mono ? "var(--ls-wide)" : "var(--ls-normal)",
      textTransform: mono ? "uppercase" : "none",
      color: t.color,
      background: t.background,
      border: "1px solid " + t.border,
      whiteSpace: "nowrap",
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const SIZES = {
  sm: {
    height: "28px",
    padding: "0 10px",
    font: "var(--fw-semibold) var(--fs-xs)/1 var(--font-text)",
    gap: "6px"
  },
  md: {
    height: "36px",
    padding: "0 14px",
    font: "var(--type-button)",
    gap: "8px"
  },
  lg: {
    height: "46px",
    padding: "0 22px",
    font: "var(--fw-semibold) var(--fs-base)/1 var(--font-text)",
    gap: "10px"
  }
};
const VARIANTS = {
  primary: {
    background: "var(--action-primary-bg)",
    color: "var(--action-primary-fg)",
    border: "1px solid var(--action-primary-bg)"
  },
  secondary: {
    background: "var(--action-secondary-bg)",
    color: "var(--action-secondary-fg)",
    border: "1px solid var(--action-secondary-border)"
  },
  ghost: {
    background: "transparent",
    color: "var(--action-ghost-fg)",
    border: "1px solid transparent"
  },
  inverse: {
    background: "var(--n-0)",
    color: "var(--n-900)",
    border: "1px solid var(--n-0)"
  },
  danger: {
    background: "var(--n-0)",
    color: "var(--action-danger-fg)",
    border: "1px solid var(--n-200)"
  }
};
const HOVER = {
  primary: {
    background: "var(--action-primary-bg-hover)",
    borderColor: "var(--action-primary-bg-hover)"
  },
  secondary: {
    background: "var(--action-secondary-bg-hover)",
    borderColor: "var(--border-strong)"
  },
  ghost: {
    background: "var(--action-ghost-bg-hover)",
    color: "var(--text-primary)"
  },
  inverse: {
    background: "var(--n-100)",
    borderColor: "var(--n-100)"
  },
  danger: {
    background: "var(--status-alert-fill)",
    borderColor: "var(--status-alert)"
  }
};
function Button({
  variant = "primary",
  size = "md",
  iconLeft,
  iconRight,
  disabled = false,
  fullWidth = false,
  type = "button",
  children,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const base = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "var(--radius-2)",
    cursor: disabled ? "not-allowed" : "pointer",
    letterSpacing: "var(--ls-tight)",
    whiteSpace: "nowrap",
    textDecoration: "none",
    width: fullWidth ? "100%" : undefined,
    transition: "var(--transition-color)",
    ...SIZES[size],
    ...VARIANTS[variant],
    ...(hover && !disabled ? HOVER[variant] : null),
    ...(disabled ? {
      background: "var(--action-disabled-bg)",
      color: "var(--action-disabled-fg)",
      borderColor: "var(--border-hairline)"
    } : null),
    ...style
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    type: type,
    disabled: disabled,
    style: base,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false)
  }, rest), iconLeft, children, iconRight);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TONES = {
  default: {
    background: "var(--surface-raised)",
    border: "1px solid var(--border-default)",
    color: "var(--text-primary)"
  },
  sunken: {
    background: "var(--surface-sunken)",
    border: "1px solid var(--border-hairline)",
    color: "var(--text-primary)"
  },
  inverse: {
    background: "var(--surface-inverse)",
    border: "1px solid var(--surface-inverse)",
    color: "var(--text-inverse)"
  },
  accent: {
    background: "var(--surface-accent-soft)",
    border: "1px solid var(--ember-tint-24)",
    color: "var(--text-primary)"
  }
};
function Card({
  tone = "default",
  pad = "var(--pad-card)",
  accentEdge = false,
  elevated = false,
  children,
  style,
  ...rest
}) {
  const t = TONES[tone] || TONES.default;
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      borderRadius: "var(--radius-3)",
      padding: pad,
      ...t,
      boxShadow: elevated ? "var(--shadow-pop)" : "none",
      borderLeft: accentEdge ? "2px solid var(--brand-ember)" : t.border,
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Eyebrow.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Eyebrow({
  rule = false,
  children,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("p", _extends({
    style: {
      display: "flex",
      alignItems: "center",
      gap: "10px",
      margin: 0,
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-eyebrow)",
      textTransform: "uppercase",
      color: "var(--text-muted)",
      ...style
    }
  }, rest), children, rule ? /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      height: 1,
      background: "var(--border-hairline)"
    }
  }) : null);
}
Object.assign(__ds_scope, { Eyebrow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Eyebrow.jsx", error: String((e && e.message) || e) }); }

// components/core/Icon.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Path data copied verbatim from the Minkops codebase icon set
   (apps/client-app/web/src/components/icons/index.tsx) and the agent role
   glyphs in apps/corporate-website (AgentRosterCard.tsx). The same files are
   available as standalone SVGs in assets/icons/. */
const UI = {
  home: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M3 9.5L12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M9 21V12h6v9"
  }))],
  agents: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
    x: "3",
    y: "8",
    width: "18",
    height: "12",
    rx: "2"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 8V6a4 4 0 0 1 8 0v2"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "9",
    cy: "14",
    r: "1",
    fill: "currentColor",
    stroke: "none"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "15",
    cy: "14",
    r: "1",
    fill: "currentColor",
    stroke: "none"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M9 17c.667.667 1.333 1 3 1s2.333-.333 3-1"
  }))],
  tasks: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"
  }), /*#__PURE__*/React.createElement("rect", {
    x: "9",
    y: "3",
    width: "6",
    height: "4",
    rx: "1"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M9 12l2 2 4-4"
  }))],
  analytics: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M3 3v18h18"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M7 16l4-6 4 4 4-8"
  }))],
  settings: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "3"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 2v2m0 16v2M4.22 4.22l1.42 1.42m12.72 12.72 1.42 1.42M2 12h2m16 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
  }))],
  chevronLeft: ["2", /*#__PURE__*/React.createElement("path", {
    d: "M15 18l-6-6 6-6"
  })],
  chevronRight: ["2", /*#__PURE__*/React.createElement("path", {
    d: "M9 18l6-6-6-6"
  })],
  send: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("line", {
    x1: "22",
    y1: "2",
    x2: "11",
    y2: "13"
  }), /*#__PURE__*/React.createElement("polygon", {
    points: "22 2 15 22 11 13 2 9 22 2"
  }))],
  bell: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M13.73 21a2 2 0 0 1-3.46 0"
  }))],
  check: ["2.2", /*#__PURE__*/React.createElement("polyline", {
    points: "20 6 9 17 4 12"
  })],
  x: ["2", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("line", {
    x1: "18",
    y1: "6",
    x2: "6",
    y2: "18"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "6",
    y1: "6",
    x2: "18",
    y2: "18"
  }))],
  palette: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
    cx: "13.5",
    cy: "6.5",
    r: "1",
    fill: "currentColor",
    stroke: "none"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "17.5",
    cy: "10.5",
    r: "1",
    fill: "currentColor",
    stroke: "none"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "8.5",
    cy: "7.5",
    r: "1",
    fill: "currentColor",
    stroke: "none"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "6.5",
    cy: "12.5",
    r: "1",
    fill: "currentColor",
    stroke: "none"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 2C6.5 2 2 6.5 2 12a10 10 0 0 0 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"
  }))],
  logout: ["1.8", /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"
  }), /*#__PURE__*/React.createElement("polyline", {
    points: "16 17 21 12 16 7"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "21",
    y1: "12",
    x2: "9",
    y2: "12"
  }))]
};
const AGENT = {
  designer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17 6.5L18 7.5L20.5 5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.25 11.75L20.5 12.75L18.75 15.75L16 14.75Z"
  })),
  social: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.5 8.25H20.5V11.25H18.75L17.5 12.5V8.25Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3.5 10.25H6.5V13.25H4.75L3.5 14.5V10.25Z"
  })),
  writer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M7.5 18.5L8.75 13L12 11.75L15.25 13L16.5 18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M15.75 10.5L19.75 8.75"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17 12.5L20.5 11.75"
  })),
  manager: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 18.5V14.25C8 12.73 9.23 11.5 10.75 11.5H13.25C14.77 11.5 16 12.73 16 14.25V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 11.5V16.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M10.75 13L12 14.25L13.25 13"
  })),
  host: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 11.5V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 12L6 14.75"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 12L18 14.75"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M9.5 18.5H14.5"
  })),
  kitchen: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M8.5 8.25C8.5 6.18 10.18 4.5 12.25 4.5C14.32 4.5 16 6.18 16 8.25V9.5H8.5V8.25Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M9.25 6.75A2.75 2.75 0 1 0 14.75 6.75A2.75 2.75 0 0 0 9.25 6.75Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8.25 18.5V13.5C8.25 11.84 9.59 10.5 11.25 10.5H12.75C14.41 10.5 15.75 11.84 15.75 13.5V18.5"
  })),
  support: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M7 10.5A5 5 0 0 1 17 10.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M6.5 11.5V14"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.5 11.5V14"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.5 14C17.5 15.66 16.16 17 14.5 17H13.75"
  })),
  sales: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 7.25A2.75 2.75 0 1 1 14.75 7.25A2.75 2.75 0 0 1 9.25 7.25Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.5 8.5L20 11L17.5 13.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M20 11H15.75"
  })),
  retail: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.25 9.25H20.5V15.5H17.25Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M18.75 11H19"
  })),
  analyst: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.25 15.5V11.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M19 15.5V9.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M20.75 15.5V13"
  })),
  email: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
    d: "M9.25 6.75A2.75 2.75 0 1 1 14.75 6.75A2.75 2.75 0 0 1 9.25 6.75Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 18.5V14.5C8 12.84 9.34 11.5 11 11.5H13C14.66 11.5 16 12.84 16 14.5V18.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.25 10H20.5V14H17.25Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M17.25 10L18.88 11.5L20.5 10"
  }))
};
function Icon({
  name,
  size = 18,
  strokeWidth,
  style,
  ...rest
}) {
  const isAgent = name in AGENT;
  const entry = isAgent ? ["1.65", AGENT[name]] : UI[name];
  if (!entry) return null;
  return /*#__PURE__*/React.createElement("svg", _extends({
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: strokeWidth ?? entry[0],
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
    style: {
      display: "block",
      flex: "none",
      ...style
    }
  }, rest), entry[1]);
}
Object.assign(__ds_scope, { Icon });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Icon.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function IconButton({
  label,
  size = 32,
  active = false,
  children,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    "aria-label": label,
    title: label,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "inline-grid",
      placeItems: "center",
      width: size,
      height: size,
      background: active ? "var(--surface-selected)" : hover ? "var(--action-ghost-bg-hover)" : "transparent",
      color: active ? "var(--brand-rust)" : hover ? "var(--text-primary)" : "var(--action-ghost-fg)",
      border: "1px solid " + (active ? "var(--ember-tint-24)" : "transparent"),
      borderRadius: "var(--radius-2)",
      cursor: "pointer",
      transition: "var(--transition-color)",
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/PriorityPill.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const LEVELS = {
  critical: {
    color: "var(--status-alert)",
    dot: "var(--status-alert)"
  },
  high: {
    color: "var(--brand-rust)",
    dot: "var(--brand-ember)"
  },
  medium: {
    color: "var(--status-warn)",
    dot: "var(--status-warn)"
  },
  low: {
    color: "var(--text-muted)",
    dot: "var(--n-400)"
  }
};
function PriorityPill({
  level = "low",
  count,
  children,
  style,
  ...rest
}) {
  const l = LEVELS[level] || LEVELS.low;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      height: "22px",
      padding: "0 9px 0 7px",
      borderRadius: "var(--radius-pill)",
      border: "1px solid var(--border-default)",
      background: "var(--surface-raised)",
      font: "var(--fw-medium) var(--fs-xs)/1 var(--font-text)",
      color: l.color,
      whiteSpace: "nowrap",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 6,
      height: 6,
      borderRadius: "50%",
      background: l.dot,
      flex: "none"
    }
  }), count != null ? count + " " : null, children ?? level);
}
Object.assign(__ds_scope, { PriorityPill });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/PriorityPill.jsx", error: String((e && e.message) || e) }); }

// components/core/StatusDot.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const STATES = {
  active: "var(--signal-live)",
  idle: "var(--signal-idle)",
  disabled: "var(--signal-off)",
  error: "var(--status-alert)",
  ok: "var(--status-ok)"
};
function StatusDot({
  status = "idle",
  size = 7,
  pulse = false,
  label,
  style,
  ...rest
}) {
  const color = STATES[status] || STATES.idle;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      width: size,
      height: size,
      borderRadius: "50%",
      background: color,
      flex: "none",
      boxShadow: pulse ? "0 0 0 3px " + (status === "active" ? "var(--ember-tint-14)" : "var(--slate-tint-20)") : "none"
    }
  }), label ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-wide)",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, label) : null);
}
Object.assign(__ds_scope, { StatusDot });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/StatusDot.jsx", error: String((e && e.message) || e) }); }

// components/core/Toggle.jsx
try { (() => {
function Toggle({
  checked = false,
  onChange,
  label,
  disabled = false,
  id,
  style
}) {
  return /*#__PURE__*/React.createElement("label", {
    title: checked ? "Disable" : "Enable",
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "8px",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.5 : 1,
      ...style
    }
  }, /*#__PURE__*/React.createElement("input", {
    id: id,
    type: "checkbox",
    checked: checked,
    disabled: disabled,
    "aria-label": label,
    onChange: e => onChange && onChange(e.target.checked),
    style: {
      position: "absolute",
      opacity: 0,
      width: 1,
      height: 1,
      margin: 0
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      width: 30,
      height: 17,
      flex: "none",
      borderRadius: "var(--radius-pill)",
      background: checked ? "var(--brand-ember)" : "var(--n-200)",
      transition: "background-color var(--dur-fast) var(--ease-out)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      top: 2,
      left: checked ? 15 : 2,
      width: 13,
      height: 13,
      borderRadius: "50%",
      background: "var(--n-0)",
      boxShadow: "0 1px 2px rgba(23,23,27,0.2)",
      transition: "left var(--dur-fast) var(--ease-out)"
    }
  })), label ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-body-sm)",
      color: "var(--text-secondary)"
    }
  }, label) : null);
}
Object.assign(__ds_scope, { Toggle });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Toggle.jsx", error: String((e && e.message) || e) }); }

// components/feedback/EmptyState.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function EmptyState({
  icon,
  headline,
  hint,
  action,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: "grid",
      justifyItems: "center",
      gap: "8px",
      padding: "48px 24px",
      textAlign: "center",
      ...style
    }
  }, rest), icon ? /*#__PURE__*/React.createElement("span", {
    style: {
      display: "grid",
      placeItems: "center",
      width: 36,
      height: 36,
      marginBottom: "4px",
      borderRadius: "var(--radius-2)",
      border: "1px solid var(--border-default)",
      background: "var(--surface-sunken)",
      color: "var(--text-muted)"
    }
  }, icon) : null, /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-h4)",
      color: "var(--text-primary)"
    }
  }, headline), hint ? /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      maxWidth: "34ch",
      font: "var(--type-body-sm)",
      color: "var(--text-muted)"
    }
  }, hint) : null, action ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: "8px"
    }
  }, action) : null);
}
Object.assign(__ds_scope, { EmptyState });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/EmptyState.jsx", error: String((e && e.message) || e) }); }

// components/feedback/ProgressSteps.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function ProgressSteps({
  total = 4,
  current = 0,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    role: "progressbar",
    "aria-valuenow": current + 1,
    "aria-valuemin": 1,
    "aria-valuemax": total,
    style: {
      display: "flex",
      gap: "4px",
      ...style
    }
  }, rest), Array.from({
    length: total
  }).map((_, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      height: 3,
      flex: 1,
      borderRadius: "var(--radius-1)",
      background: i <= current ? "var(--brand-ember)" : "var(--n-100)",
      transition: "background-color var(--dur-base) var(--ease-out)"
    }
  })));
}
Object.assign(__ds_scope, { ProgressSteps });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/ProgressSteps.jsx", error: String((e && e.message) || e) }); }

// components/feedback/TypingIndicator.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function TypingIndicator({
  name = "Agent",
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("style", null, "@keyframes mk-typing{0%,60%,100%{opacity:.25}30%{opacity:1}}"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      gap: "4px",
      padding: "8px 10px",
      border: "1px solid var(--border-hairline)",
      borderRadius: "var(--radius-2)",
      background: "var(--surface-sunken)"
    }
  }, [0, 1, 2].map(i => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      width: 5,
      height: 5,
      borderRadius: "50%",
      background: "var(--brand-ember)",
      animation: "mk-typing 1.2s " + i * 0.16 + "s infinite var(--ease-in-out)"
    }
  }))), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-wide)",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, name, " is working"));
}
Object.assign(__ds_scope, { TypingIndicator });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/TypingIndicator.jsx", error: String((e && e.message) || e) }); }

// components/forms/Field.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Field({
  label,
  htmlFor,
  hint,
  error,
  required = false,
  children,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: "grid",
      gap: "6px",
      ...style
    }
  }, rest), label ? /*#__PURE__*/React.createElement("label", {
    htmlFor: htmlFor,
    style: {
      font: "var(--fw-medium) var(--fs-xs)/1.2 var(--font-text)",
      letterSpacing: "var(--ls-normal)",
      color: "var(--text-secondary)"
    }
  }, label, required ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--brand-ember)"
    }
  }, " *") : null) : null, children, error ? /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body-sm)",
      color: "var(--status-alert)"
    }
  }, error) : hint ? /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--fw-regular) var(--fs-xs)/1.45 var(--font-text)",
      color: "var(--text-muted)"
    }
  }, hint) : null);
}
Object.assign(__ds_scope, { Field });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Field.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Input({
  invalid = false,
  mono = false,
  size = "md",
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("input", _extends({
    onFocus: e => {
      setFocus(true);
      rest.onFocus && rest.onFocus(e);
    },
    onBlur: e => {
      setFocus(false);
      rest.onBlur && rest.onBlur(e);
    }
  }, rest, {
    style: {
      height: size === "sm" ? 30 : 38,
      width: "100%",
      padding: "0 10px",
      background: "var(--surface-raised)",
      color: "var(--text-primary)",
      font: mono ? "var(--fw-regular) var(--fs-sm)/1 var(--font-mono)" : "var(--type-body-sm)",
      border: "1px solid " + (invalid ? "var(--status-alert)" : focus ? "var(--brand-ember)" : "var(--border-default)"),
      borderRadius: "var(--radius-2)",
      outline: "none",
      boxShadow: focus && !invalid ? "0 0 0 3px var(--ember-tint-14)" : "none",
      transition: "var(--transition-color)",
      ...style
    }
  }));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/OptionRow.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function OptionRow({
  label,
  meta,
  selected = false,
  multi = false,
  onSelect,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    role: multi ? "checkbox" : "radio",
    "aria-checked": selected,
    onClick: onSelect,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "flex",
      alignItems: "center",
      gap: "12px",
      width: "100%",
      minHeight: 48,
      padding: "10px 14px",
      textAlign: "left",
      cursor: "pointer",
      background: selected ? "var(--surface-accent-soft)" : hover ? "var(--surface-sunken)" : "var(--surface-raised)",
      border: "1px solid " + (selected ? "var(--brand-ember)" : "var(--border-default)"),
      borderRadius: "var(--radius-2)",
      transition: "var(--transition-color)",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      display: "grid",
      placeItems: "center",
      width: 16,
      height: 16,
      flex: "none",
      borderRadius: multi ? "var(--radius-1)" : "50%",
      border: "1px solid " + (selected ? "var(--brand-ember)" : "var(--border-strong)"),
      background: selected ? "var(--brand-ember)" : "transparent",
      color: "var(--n-0)"
    }
  }, selected ? /*#__PURE__*/React.createElement("svg", {
    width: "10",
    height: "10",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "3.2",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("polyline", {
    points: "20 6 9 17 4 12"
  })) : null), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "grid",
      gap: "2px",
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-body-sm)",
      fontWeight: "var(--fw-medium)",
      color: "var(--text-primary)"
    }
  }, label), meta ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-wide)",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, meta) : null));
}
Object.assign(__ds_scope, { OptionRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/OptionRow.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Select({
  options = [],
  invalid = false,
  style,
  children,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      ...style
    }
  }, /*#__PURE__*/React.createElement("select", _extends({
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false)
  }, rest, {
    style: {
      height: 38,
      width: "100%",
      padding: "0 32px 0 10px",
      appearance: "none",
      background: "var(--surface-raised)",
      color: "var(--text-primary)",
      font: "var(--type-body-sm)",
      border: "1px solid " + (invalid ? "var(--status-alert)" : focus ? "var(--brand-ember)" : "var(--border-default)"),
      borderRadius: "var(--radius-2)",
      outline: "none",
      boxShadow: focus && !invalid ? "0 0 0 3px var(--ember-tint-14)" : "none",
      transition: "var(--transition-color)"
    }
  }), children || options.map(o => /*#__PURE__*/React.createElement("option", {
    key: o.value,
    value: o.value
  }, o.label))), /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "var(--text-muted)",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
    style: {
      position: "absolute",
      right: 11,
      top: "50%",
      transform: "translateY(-50%) rotate(90deg)",
      pointerEvents: "none"
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: "M9 18l6-6-6-6"
  })));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Textarea.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Textarea({
  invalid = false,
  autoGrow = false,
  rows = 4,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const handleInput = e => {
    if (autoGrow) {
      e.target.style.height = "auto";
      e.target.style.height = e.target.scrollHeight + "px";
    }
    rest.onInput && rest.onInput(e);
  };
  return /*#__PURE__*/React.createElement("textarea", _extends({
    rows: rows,
    onFocus: e => {
      setFocus(true);
      rest.onFocus && rest.onFocus(e);
    },
    onBlur: e => {
      setFocus(false);
      rest.onBlur && rest.onBlur(e);
    }
  }, rest, {
    onInput: handleInput,
    style: {
      width: "100%",
      padding: "9px 10px",
      resize: autoGrow ? "none" : "vertical",
      maxHeight: autoGrow ? "var(--composer-max-h)" : undefined,
      background: "var(--surface-raised)",
      color: "var(--text-primary)",
      font: "var(--type-body-sm)",
      border: "1px solid " + (invalid ? "var(--status-alert)" : focus ? "var(--brand-ember)" : "var(--border-default)"),
      borderRadius: "var(--radius-2)",
      outline: "none",
      boxShadow: focus && !invalid ? "0 0 0 3px var(--ember-tint-14)" : "none",
      transition: "var(--transition-color)",
      ...style
    }
  }));
}
Object.assign(__ds_scope, { Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Textarea.jsx", error: String((e && e.message) || e) }); }

// components/product/AgentRow.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function AgentRow({
  name,
  role,
  status = "idle",
  lastActive,
  enabled = true,
  selected = false,
  onToggle,
  onSelect,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", _extends({
    onClick: onSelect,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "flex",
      alignItems: "center",
      gap: "10px",
      padding: "8px 10px",
      borderRadius: "var(--radius-2)",
      cursor: onSelect ? "pointer" : "default",
      background: selected ? "var(--surface-selected)" : hover ? "var(--surface-sunken)" : "transparent",
      boxShadow: selected ? "var(--shadow-inset-active)" : "none",
      opacity: enabled ? 1 : 0.55,
      transition: "var(--transition-color)",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement(__ds_scope.Avatar, {
    name: name,
    kind: "agent",
    size: 30
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "3px",
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      alignItems: "baseline",
      gap: "8px",
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-medium) var(--fs-sm)/1.1 var(--font-display)",
      letterSpacing: "var(--ls-tight)",
      color: "var(--text-primary)"
    }
  }, name), role ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-body-sm)",
      color: "var(--text-muted)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, role) : null), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "8px"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.StatusDot, {
    status: enabled ? status : "disabled",
    label: enabled ? status : "disabled"
  }), lastActive ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-faint)"
    }
  }, lastActive) : null)), onToggle ? /*#__PURE__*/React.createElement(__ds_scope.Toggle, {
    checked: enabled,
    onChange: onToggle,
    label: ""
  }) : null);
}
Object.assign(__ds_scope, { AgentRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/AgentRow.jsx", error: String((e && e.message) || e) }); }

// components/product/AgentTile.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function AgentTile({
  name,
  tool,
  domain,
  glyph = "email",
  status,
  onClick,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const interactive = Boolean(onClick);
  return /*#__PURE__*/React.createElement("article", _extends({
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "grid",
      gap: "10px",
      padding: "16px",
      background: "var(--surface-raised)",
      border: "1px solid " + (hover && interactive ? "var(--brand-ember)" : "var(--border-default)"),
      borderRadius: "var(--radius-3)",
      cursor: interactive ? "pointer" : "default",
      transition: "var(--transition-color)",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "grid",
      placeItems: "center",
      width: 34,
      height: 34,
      borderRadius: "var(--radius-2)",
      background: "var(--surface-inset)",
      border: "1px solid var(--border-hairline)",
      color: "var(--brand-rust)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: glyph,
    size: 22
  })), status ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-wide)",
      textTransform: "uppercase",
      color: "var(--text-faint)"
    }
  }, status) : null), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "grid",
      gap: "3px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-semibold) var(--fs-lg)/1.1 var(--font-display)",
      letterSpacing: "var(--ls-display)",
      color: "var(--text-primary)"
    }
  }, name), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-body-sm)",
      color: "var(--text-secondary)"
    }
  }, tool)), domain ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-muted)",
      paddingTop: "8px",
      borderTop: "1px solid var(--border-hairline)"
    }
  }, domain) : null);
}
Object.assign(__ds_scope, { AgentTile });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/AgentTile.jsx", error: String((e && e.message) || e) }); }

// components/product/FlowNode.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function FlowNode({
  agent,
  role,
  output = false,
  label,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: "grid",
      gap: "4px",
      minWidth: 148,
      padding: "14px 16px",
      background: output ? "var(--surface-inverse)" : "var(--surface-raised)",
      color: output ? "var(--text-inverse)" : "var(--text-primary)",
      border: "1px solid " + (output ? "var(--surface-inverse)" : "var(--border-default)"),
      borderTop: output ? "1px solid var(--surface-inverse)" : "2px solid var(--brand-ember)",
      borderRadius: "var(--radius-3)",
      ...style
    }
  }, rest), output ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-medium) var(--fs-sm)/1.2 var(--font-text)"
    }
  }, label) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-semibold) var(--fs-md)/1.1 var(--font-display)",
      letterSpacing: "var(--ls-display)"
    }
  }, agent), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-wide)",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, role)));
}
function FlowArrow({
  label,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: "grid",
      justifyItems: "center",
      gap: "4px",
      minWidth: 96,
      ...style
    }
  }, rest), label ? /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-muted)",
      textAlign: "center"
    }
  }, label) : null, /*#__PURE__*/React.createElement("svg", {
    width: "72",
    height: "8",
    viewBox: "0 0 72 8",
    fill: "none",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M0 4H66",
    stroke: "var(--border-strong)",
    strokeWidth: "1.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M63 1L67 4L63 7",
    stroke: "var(--border-strong)",
    strokeWidth: "1.5",
    strokeLinecap: "round"
  })));
}
Object.assign(__ds_scope, { FlowNode, FlowArrow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/FlowNode.jsx", error: String((e && e.message) || e) }); }

// components/product/InterruptCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const LABELS = {
  approval: "Approval",
  escalation: "Escalation",
  review: "Review",
  error: "Error"
};
function InterruptCard({
  type = "review",
  priority = "medium",
  status = "pending",
  title,
  description,
  agentName,
  taskTitle,
  suggestedAction,
  time,
  onResolve,
  onAcknowledge,
  onDismiss,
  style,
  ...rest
}) {
  const pending = status === "pending";
  const critical = priority === "critical";
  return /*#__PURE__*/React.createElement("article", _extends({
    style: {
      display: "grid",
      gap: "8px",
      padding: "12px 14px",
      background: "var(--surface-raised)",
      borderRadius: "var(--radius-3)",
      border: "1px solid " + (critical ? "rgba(179,38,30,0.28)" : "var(--border-default)"),
      borderLeft: "2px solid " + (critical ? "var(--status-alert)" : pending ? "var(--brand-ember)" : "var(--border-strong)"),
      opacity: pending ? 1 : 0.72,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "8px"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: type
  }, LABELS[type] || type), critical ? /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: "escalation"
  }, "Critical") : null, /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      font: "var(--type-mono)",
      color: "var(--text-faint)"
    }
  }, time)), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--fw-medium) var(--fs-sm)/1.35 var(--font-text)",
      color: "var(--text-primary)"
    }
  }, title), description ? /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--fw-regular) var(--fs-xs)/1.55 var(--font-text)",
      color: "var(--text-secondary)"
    }
  }, description) : null, agentName || taskTitle ? /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, agentName ? /*#__PURE__*/React.createElement(React.Fragment, null, "Raised by ", /*#__PURE__*/React.createElement("strong", {
    style: {
      color: "var(--text-secondary)",
      fontWeight: "var(--fw-medium)"
    }
  }, agentName)) : null, agentName && taskTitle ? " · " : null, taskTitle) : null, suggestedAction ? /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      padding: "8px 10px",
      background: "var(--surface-sunken)",
      borderLeft: "1px solid var(--border-default)",
      font: "var(--fw-regular) var(--fs-xs)/1.5 var(--font-text)",
      color: "var(--text-secondary)"
    }
  }, suggestedAction) : null, pending ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "6px",
      marginTop: "2px"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Button, {
    size: "sm",
    variant: "primary",
    onClick: onResolve,
    iconLeft: /*#__PURE__*/React.createElement(__ds_scope.Icon, {
      name: "check",
      size: 12
    })
  }, "Resolve"), /*#__PURE__*/React.createElement(__ds_scope.Button, {
    size: "sm",
    variant: "secondary",
    onClick: onAcknowledge
  }, "Acknowledge"), /*#__PURE__*/React.createElement(__ds_scope.Button, {
    size: "sm",
    variant: "danger",
    onClick: onDismiss,
    style: {
      marginLeft: "auto",
      padding: "0 8px"
    },
    "aria-label": "Dismiss"
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "x",
    size: 12
  }))) : null);
}
Object.assign(__ds_scope, { InterruptCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/InterruptCard.jsx", error: String((e && e.message) || e) }); }

// components/product/MessageBubble.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function MessageBubble({
  role = "agent",
  sender,
  content,
  time,
  style,
  ...rest
}) {
  const human = role === "human";
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: "flex",
      gap: "10px",
      flexDirection: human ? "row-reverse" : "row",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement(__ds_scope.Avatar, {
    name: sender,
    kind: human ? "human" : "agent",
    size: 28
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "4px",
      maxWidth: "min(560px, 78%)",
      justifyItems: human ? "end" : "start"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-wide)",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, sender), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      padding: "9px 12px",
      font: "var(--type-body-sm)",
      borderRadius: "var(--radius-3)",
      background: human ? "var(--surface-inverse)" : "var(--surface-sunken)",
      color: human ? "var(--text-inverse)" : "var(--text-primary)",
      border: "1px solid " + (human ? "var(--surface-inverse)" : "var(--border-hairline)"),
      whiteSpace: "pre-wrap"
    }
  }, content), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-faint)"
    }
  }, time)));
}
Object.assign(__ds_scope, { MessageBubble });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/MessageBubble.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/AgentsPane.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  AgentRow,
  Toggle,
  Eyebrow,
  Button,
  Icon,
  Card
} = window.MinkopsDesignSystem_6c27f0;
function AgentsPane({
  agents,
  team,
  selectedId,
  onSelect,
  onToggleAgent,
  onToggleTeam
}) {
  const teamMembers = agents.filter(a => a.team === team.name);
  const standalone = agents.filter(a => !a.team);
  return /*#__PURE__*/React.createElement("section", {
    style: {
      width: "var(--pane-agents-w)",
      flex: "none",
      display: "flex",
      flexDirection: "column",
      borderRight: "1px solid var(--border-hairline)",
      background: "var(--surface-page)",
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(PaneHeader, {
    title: "Your agents",
    action: /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      variant: "ghost"
    }, "+ Browse")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      overflowY: "auto",
      padding: "10px",
      display: "grid",
      gap: "12px",
      alignContent: "start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "6px"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "Teams"), /*#__PURE__*/React.createElement(Card, {
    tone: "sunken",
    pad: "10px",
    style: {
      display: "grid",
      gap: "6px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "8px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-medium) var(--fs-sm)/1.1 var(--font-display)"
    }
  }, team.name), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto"
    }
  }, /*#__PURE__*/React.createElement(Toggle, {
    checked: team.enabled,
    onChange: onToggleTeam,
    label: ""
  }))), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--fw-regular) var(--fs-xs)/1.5 var(--font-text)",
      color: "var(--text-secondary)"
    }
  }, team.description), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, team.members.join(", ")))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "2px"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, team.name), teamMembers.map(a => /*#__PURE__*/React.createElement(AgentRow, _extends({
    key: a.id
  }, a, {
    selected: a.id === selectedId,
    onSelect: () => onSelect(a.id),
    onToggle: v => onToggleAgent(a.id, v)
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "2px"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "Individual"), standalone.map(a => /*#__PURE__*/React.createElement(AgentRow, _extends({
    key: a.id
  }, a, {
    selected: a.id === selectedId,
    onSelect: () => onSelect(a.id),
    onToggle: v => onToggleAgent(a.id, v)
  }))))));
}
Object.assign(window, {
  AgentsPane
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/AgentsPane.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/AgentsScreen.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  AgentTile,
  Eyebrow,
  Button,
  Icon
} = window.MinkopsDesignSystem_6c27f0;
const CATALOGUE = [{
  name: "Imel",
  tool: "Email handler",
  domain: "Generic",
  glyph: "email",
  status: "Hired"
}, {
  name: "Kall",
  tool: "Customer support rep",
  domain: "Generic",
  glyph: "support",
  status: "Hired"
}, {
  name: "Leed",
  tool: "Lead generation caller",
  domain: "Generic",
  glyph: "sales",
  status: "Available"
}, {
  name: "Eko",
  tool: "Social media handler",
  domain: "Generic",
  glyph: "social",
  status: "Available"
}, {
  name: "Floc",
  tool: "Content creator",
  domain: "Generic",
  glyph: "writer",
  status: "Available"
}, {
  name: "Insi",
  tool: "Business analyst",
  domain: "Generic",
  glyph: "analyst",
  status: "Available"
}, {
  name: "Kim",
  tool: "Store manager's assistant",
  domain: "Generic",
  glyph: "retail",
  status: "In build"
}, {
  name: "Ora",
  tool: "Moodboard generator",
  domain: "Interior design",
  glyph: "designer",
  status: "In build"
}, {
  name: "Cruz",
  tool: "Manager's assistant",
  domain: "Fast food",
  glyph: "manager",
  status: "In build"
}, {
  name: "Hosi",
  tool: "Front of house",
  domain: "Fast food",
  glyph: "host",
  status: "In build"
}, {
  name: "Prex",
  tool: "Back of house",
  domain: "Fast food",
  glyph: "kitchen",
  status: "In build"
}];
function AgentsScreen() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: "auto",
      padding: "28px 32px",
      display: "grid",
      gap: "18px",
      alignContent: "start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "8px"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    rule: true
  }, "Roster \xB7 11 agents"), /*#__PURE__*/React.createElement("h2", {
    style: {
      font: "var(--type-h2)"
    }
  }, "Browse & add agents"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      maxWidth: "var(--measure)",
      font: "var(--type-body)",
      color: "var(--text-secondary)"
    }
  }, "Each agent replaces one role, not one task. Hire the ones that match the work you're doing by hand today.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(232px, 1fr))",
      gap: "12px"
    }
  }, CATALOGUE.map(a => /*#__PURE__*/React.createElement(AgentTile, _extends({
    key: a.name
  }, a, {
    onClick: () => {}
  })))));
}
Object.assign(window, {
  AgentsScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/AgentsScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/AttentionQueue.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  InterruptCard,
  PriorityPill,
  EmptyState
} = window.MinkopsDesignSystem_6c27f0;
const ORDER = ["critical", "high", "medium", "low"];
function AttentionQueue({
  interrupts,
  onResolve,
  onAcknowledge,
  onDismiss
}) {
  const pending = interrupts.filter(i => i.status === "pending");
  const counts = ORDER.map(l => [l, pending.filter(i => i.priority === l).length]).filter(([, n]) => n > 0);
  const sorted = [...interrupts].sort((a, b) => ORDER.indexOf(a.priority) - ORDER.indexOf(b.priority) || (a.status === b.status ? 0 : a.status === "pending" ? -1 : 1));
  return /*#__PURE__*/React.createElement("section", {
    style: {
      width: "var(--pane-attention-w)",
      flex: "none",
      display: "flex",
      flexDirection: "column",
      borderLeft: "1px solid var(--border-hairline)",
      background: "var(--surface-sunken)",
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(PaneHeader, {
    title: "Needs attention" + (pending.length ? " (" + pending.length + ")" : "")
  }), counts.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: "6px",
      padding: "10px 12px 0"
    }
  }, counts.map(([l, n]) => /*#__PURE__*/React.createElement(PriorityPill, {
    key: l,
    level: l,
    count: n
  }))) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      overflowY: "auto",
      padding: "10px 12px 14px",
      display: "grid",
      gap: "10px",
      alignContent: "start"
    }
  }, sorted.length === 0 ? /*#__PURE__*/React.createElement(EmptyState, {
    headline: "All clear",
    hint: "No items need your attention right now. Agents are running smoothly."
  }) : sorted.map(i => /*#__PURE__*/React.createElement(InterruptCard, _extends({
    key: i.id
  }, i, {
    onResolve: () => onResolve(i.id),
    onAcknowledge: () => onAcknowledge(i.id),
    onDismiss: () => onDismiss(i.id)
  })))));
}
Object.assign(window, {
  AttentionQueue
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/AttentionQueue.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/ConsoleData.jsx
try { (() => {
const AGENTS = [{
  id: "agent-imel",
  name: "Imel",
  role: "Email handler",
  status: "active",
  lastActive: "4m ago",
  enabled: true,
  team: "CX Response Team"
}, {
  id: "agent-kall",
  name: "Kall",
  role: "Support rep",
  status: "idle",
  lastActive: "22m ago",
  enabled: true,
  team: "CX Response Team"
}, {
  id: "agent-scout",
  name: "Scout",
  role: "Lead research",
  status: "active",
  lastActive: "2m ago",
  enabled: true,
  team: null
}, {
  id: "agent-synapse",
  name: "Synapse",
  role: "Reporting",
  status: "idle",
  lastActive: "3h ago",
  enabled: true,
  team: null
}, {
  id: "agent-aria",
  name: "Aria",
  role: "Scheduling",
  status: "disabled",
  lastActive: "never",
  enabled: false,
  team: null
}];
const TEAM = {
  id: "team-cx",
  name: "CX Response Team",
  description: "Handles end-to-end customer communication and support ticket resolution.",
  members: ["Imel", "Kall"],
  enabled: true
};
const MESSAGES = [{
  id: "m1",
  role: "human",
  sender: "You",
  content: "Imel — the Acme refund thread came back overnight. Draft the reply and flag anything over threshold.",
  time: "14:28"
}, {
  id: "m2",
  role: "agent",
  sender: "Imel",
  content: "Read and classified: refund request, ticket #2847. Drafted a reply approving $3,200. That's over the $1,000 auto-approval threshold, so it's waiting on you in the queue.",
  time: "14:29"
}, {
  id: "m3",
  role: "human",
  sender: "You",
  content: "Scout, pull the NovaBuild contact into the pipeline too.",
  time: "14:31"
}, {
  id: "m4",
  role: "agent",
  sender: "Scout",
  content: "Enriched Marcus Wren (VP Engineering, NovaBuild). Company size and budget signals are at 72% confidence — below auto-qualify, so I've queued it for review.",
  time: "14:32"
}];
const INTERRUPTS = [{
  id: "int-002",
  type: "escalation",
  priority: "critical",
  status: "pending",
  title: "Escalation: repeated SLA breach — TechFlow Inc",
  description: "TechFlow Inc has had 3 tickets breach SLA in 7 days. Kall has exhausted its KB resolution paths. Enterprise tier — manual intervention recommended.",
  agentName: "Kall",
  taskTitle: "TechFlow Inc — SLA breach pattern",
  time: "31m ago",
  suggestedAction: "Contact the TechFlow account manager directly and schedule a call."
}, {
  id: "int-001",
  type: "approval",
  priority: "high",
  status: "pending",
  title: "Approve refund: Acme Corp — $3,200",
  description: "Imel drafted a refund approval for ticket #2847. The amount exceeds the $1,000 auto-approval threshold and requires operator sign-off before sending.",
  agentName: "Imel",
  taskTitle: "Acme Corp refund request #2847",
  time: "8m ago",
  suggestedAction: "Review the drafted email and approve or modify the refund amount."
}, {
  id: "int-003",
  type: "review",
  priority: "medium",
  status: "pending",
  title: "Review scraped lead profile — Marcus Wren, NovaBuild",
  description: "Scout enriched a lead profile for Marcus Wren (VP Engineering, NovaBuild). Confidence on company size and budget signals is 72% — below the auto-qualify threshold.",
  agentName: "Scout",
  taskTitle: "Lead enrichment: Marcus Wren",
  time: "52m ago",
  suggestedAction: "Verify company size on LinkedIn and confirm the budget signal before qualifying."
}, {
  id: "int-004",
  type: "review",
  priority: "low",
  status: "acknowledged",
  title: "Draft blog post ready for review",
  description: "Synapse completed a first draft of the Q1 product update post based on your outline.",
  agentName: "Synapse",
  taskTitle: "Q1 product update blog post",
  time: "2h ago",
  suggestedAction: null
}];
const USER = {
  name: "Kartik Shah",
  role: "Operator",
  tenantName: "Minkowski Home",
  tenantId: "tenant_001"
};
Object.assign(window, {
  AGENTS,
  TEAM,
  MESSAGES,
  INTERRUPTS,
  USER
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/ConsoleData.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/ConsoleShell.jsx
try { (() => {
const {
  Icon,
  IconButton,
  Avatar,
  Badge
} = window.MinkopsDesignSystem_6c27f0;
const NAV = [{
  key: "dashboard",
  label: "Dashboard",
  icon: "home"
}, {
  key: "agents",
  label: "Agents",
  icon: "agents"
}, {
  key: "tasks",
  label: "Tasks",
  icon: "tasks"
}, {
  key: "analytics",
  label: "Analytics",
  icon: "analytics"
}, {
  key: "settings",
  label: "Settings",
  icon: "settings"
}];
function SidebarItem({
  item,
  active,
  collapsed,
  onClick
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    title: collapsed ? item.label : undefined,
    style: {
      display: "flex",
      alignItems: "center",
      gap: "10px",
      width: "100%",
      height: 34,
      padding: collapsed ? "0" : "0 10px",
      justifyContent: collapsed ? "center" : "flex-start",
      background: active ? "var(--surface-selected)" : hover ? "var(--action-ghost-bg-hover)" : "transparent",
      color: active ? "var(--brand-rust)" : hover ? "var(--text-primary)" : "var(--text-secondary)",
      border: "none",
      borderRadius: "var(--radius-2)",
      cursor: "pointer",
      textAlign: "left",
      boxShadow: active ? "var(--shadow-inset-active)" : "none",
      font: "var(--fw-medium) var(--fs-sm)/1 var(--font-text)",
      transition: "var(--transition-color)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: item.icon,
    size: 17
  }), collapsed ? null : item.label);
}
function ConsoleSidebar({
  route,
  onRoute,
  collapsed,
  onCollapse,
  onSignOut
}) {
  return /*#__PURE__*/React.createElement("nav", {
    "aria-label": "Main navigation",
    style: {
      width: collapsed ? "var(--sidebar-w-collapsed)" : "var(--sidebar-w)",
      flex: "none",
      display: "flex",
      flexDirection: "column",
      background: "var(--surface-sunken)",
      borderRight: "1px solid var(--border-hairline)",
      transition: "width var(--dur-base) var(--ease-out)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      height: "var(--header-h)",
      padding: collapsed ? "0 8px" : "0 10px 0 12px",
      borderBottom: "1px solid var(--border-hairline)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      borderRadius: "50%",
      background: "var(--brand-ember)",
      flex: "none"
    }
  }), collapsed ? null : /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-bold) var(--fs-md)/1 var(--font-display)",
      letterSpacing: "var(--ls-wordmark)"
    }
  }, "minkops"), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto"
    }
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: collapsed ? "Expand sidebar" : "Collapse sidebar",
    size: 26,
    onClick: onCollapse
  }, /*#__PURE__*/React.createElement(Icon, {
    name: collapsed ? "chevronRight" : "chevronLeft",
    size: 13
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "2px",
      padding: "10px 8px"
    }
  }, NAV.map(item => /*#__PURE__*/React.createElement(SidebarItem, {
    key: item.key,
    item: item,
    active: route === item.key,
    collapsed: collapsed,
    onClick: () => onRoute(item.key)
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: "auto",
      padding: "10px 8px",
      borderTop: "1px solid var(--border-hairline)",
      display: "grid",
      gap: "6px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "0 2px"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    name: window.USER.name,
    kind: "human",
    size: 28
  }), collapsed ? null : /*#__PURE__*/React.createElement("span", {
    style: {
      display: "grid",
      gap: "1px",
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-medium) var(--fs-xs)/1.2 var(--font-text)",
      color: "var(--text-primary)",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, window.USER.name), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-wide)",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, window.USER.role))), /*#__PURE__*/React.createElement(SidebarItem, {
    item: {
      label: "Sign out",
      icon: "logout"
    },
    collapsed: collapsed,
    onClick: onSignOut
  })));
}
function ConsoleHeader({
  title,
  interruptCount,
  children
}) {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "10px",
      height: "var(--header-h)",
      flex: "none",
      padding: "0 14px",
      background: "var(--surface-page)",
      borderBottom: "1px solid var(--border-hairline)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-medium) var(--fs-md)/1 var(--font-display)",
      letterSpacing: "var(--ls-display)"
    }
  }, title), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      display: "flex",
      alignItems: "center",
      gap: "8px"
    }
  }, children, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "inline-flex"
    }
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: interruptCount + " items need attention"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "bell",
    size: 17
  })), interruptCount > 0 ? /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      top: -2,
      right: -2,
      minWidth: 15,
      height: 15,
      padding: "0 4px",
      display: "grid",
      placeItems: "center",
      borderRadius: "var(--radius-pill)",
      background: "var(--brand-ember)",
      color: "var(--n-0)",
      font: "var(--fw-medium) 9px/1 var(--font-mono)",
      border: "1.5px solid var(--surface-page)"
    }
  }, interruptCount) : null), /*#__PURE__*/React.createElement(Badge, {
    tone: "neutral",
    mono: false
  }, window.USER.tenantName)));
}
function PaneHeader({
  title,
  meta,
  action
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "10px 12px",
      borderBottom: "1px solid var(--border-hairline)",
      flex: "none"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-eyebrow)",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, title), meta, action ? /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto"
    }
  }, action) : null);
}
Object.assign(window, {
  ConsoleSidebar,
  ConsoleHeader,
  PaneHeader,
  CONSOLE_NAV: NAV
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/ConsoleShell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/LoginScreen.jsx
try { (() => {
const {
  Button,
  Field,
  Input
} = window.MinkopsDesignSystem_6c27f0;
function LoginScreen({
  onSignIn
}) {
  const [email, setEmail] = React.useState("kartik@minkowskihome.com");
  const [password, setPassword] = React.useState("••••••••");
  const [busy, setBusy] = React.useState(false);
  const submit = e => {
    e.preventDefault();
    setBusy(true);
    setTimeout(() => {
      setBusy(false);
      onSignIn();
    }, 500);
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100%",
      display: "grid",
      gridTemplateColumns: "1.15fr 1fr",
      background: "var(--surface-page)"
    }
  }, /*#__PURE__*/React.createElement("section", {
    style: {
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      padding: "40px 48px",
      background: "var(--surface-inverse)",
      color: "var(--text-inverse)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "9px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: "50%",
      background: "var(--brand-ember)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-bold) var(--fs-lg)/1 var(--font-display)",
      letterSpacing: "var(--ls-wordmark)"
    }
  }, "minkops")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "12px",
      maxWidth: "22ch"
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      font: "var(--fw-semibold) var(--fs-3xl)/1.08 var(--font-display)",
      letterSpacing: "var(--ls-display)",
      color: "var(--text-inverse)"
    }
  }, "Welcome back"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body)",
      color: "var(--text-inverse-muted)",
      maxWidth: "30ch"
    }
  }, "Sign in to your operator dashboard. Your fleet has been running while you were away.")), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-mono)",
      color: "var(--text-inverse-muted)"
    }
  }, "tenant_001 \xB7 Minkowski Home")), /*#__PURE__*/React.createElement("section", {
    style: {
      display: "grid",
      placeItems: "center",
      padding: "40px"
    }
  }, /*#__PURE__*/React.createElement("form", {
    onSubmit: submit,
    style: {
      width: "min(340px, 100%)",
      display: "grid",
      gap: "14px"
    }
  }, /*#__PURE__*/React.createElement(Field, {
    label: "Email",
    htmlFor: "login-email"
  }, /*#__PURE__*/React.createElement(Input, {
    id: "login-email",
    type: "email",
    value: email,
    onChange: e => setEmail(e.target.value),
    autoComplete: "email"
  })), /*#__PURE__*/React.createElement(Field, {
    label: "Password",
    htmlFor: "login-password"
  }, /*#__PURE__*/React.createElement(Input, {
    id: "login-password",
    type: "password",
    value: password,
    onChange: e => setPassword(e.target.value),
    autoComplete: "current-password"
  })), /*#__PURE__*/React.createElement(Button, {
    type: "submit",
    variant: "primary",
    fullWidth: true,
    disabled: busy
  }, busy ? "Signing in…" : "Sign in"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, "Access is restricted to authorised tenants only."))));
}
Object.assign(window, {
  LoginScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/LoginScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/PlaceholderScreen.jsx
try { (() => {
const {
  Eyebrow,
  Card,
  EmptyState,
  Icon,
  StatusDot,
  Badge
} = window.MinkopsDesignSystem_6c27f0;

/* Analytics and Settings exist as routes in the product but have no designed
   screens in the source codebase. They are left intentionally blank here. */
function PlaceholderScreen({
  route
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: "auto",
      padding: "28px 32px",
      display: "grid",
      gap: "18px",
      alignContent: "start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "6px"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    rule: true
  }, route), /*#__PURE__*/React.createElement("h2", {
    style: {
      font: "var(--type-h2)"
    }
  }, route === "analytics" ? "Analytics" : "Settings")), /*#__PURE__*/React.createElement(Card, {
    tone: "sunken",
    pad: "0"
  }, /*#__PURE__*/React.createElement(EmptyState, {
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: route === "analytics" ? "analytics" : "settings",
      size: 20
    }),
    headline: "Not designed yet",
    hint: "The Minkops codebase routes to /" + route + " but ships no screen for it. Left blank on purpose rather than invented."
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "8px",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "neutral"
  }, "Route present"), /*#__PURE__*/React.createElement(StatusDot, {
    status: "idle",
    label: "no source design"
  })));
}
Object.assign(window, {
  PlaceholderScreen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/PlaceholderScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/TaskThread.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  MessageBubble,
  TypingIndicator,
  Textarea,
  IconButton,
  Icon,
  StatusDot,
  EmptyState
} = window.MinkopsDesignSystem_6c27f0;
function TaskThread({
  messages,
  activeCount,
  onSend
}) {
  const [draft, setDraft] = React.useState("");
  const [working, setWorking] = React.useState(false);
  const listRef = React.useRef(null);
  React.useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, working]);
  const send = () => {
    const content = draft.trim();
    if (!content) return;
    setDraft("");
    onSend(content);
    setWorking(true);
    setTimeout(() => setWorking(false), 1600);
  };
  return /*#__PURE__*/React.createElement("section", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      minWidth: 0,
      minHeight: 0,
      background: "var(--surface-page)"
    }
  }, /*#__PURE__*/React.createElement(PaneHeader, {
    title: "Assign a task",
    meta: /*#__PURE__*/React.createElement("span", {
      style: {
        marginLeft: "6px"
      }
    }, /*#__PURE__*/React.createElement(StatusDot, {
      status: "active",
      pulse: true,
      label: activeCount + " agents active"
    }))
  }), /*#__PURE__*/React.createElement("div", {
    ref: listRef,
    style: {
      flex: 1,
      overflowY: "auto",
      padding: "16px 18px",
      display: "grid",
      gap: "14px",
      alignContent: "start"
    }
  }, messages.length === 0 ? /*#__PURE__*/React.createElement(EmptyState, {
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: "agents",
      size: 20
    }),
    headline: "No tasks yet",
    hint: "Type a task below and your agents will get to work immediately."
  }) : messages.map(m => /*#__PURE__*/React.createElement(MessageBubble, _extends({
    key: m.id
  }, m))), working ? /*#__PURE__*/React.createElement(TypingIndicator, {
    name: "Imel"
  }) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "none",
      padding: "10px 14px 12px",
      borderTop: "1px solid var(--border-hairline)",
      background: "var(--surface-page)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-end",
      gap: "8px"
    }
  }, /*#__PURE__*/React.createElement(Textarea, {
    autoGrow: true,
    rows: 1,
    value: draft,
    placeholder: "Describe a task for your agents\u2026",
    onChange: e => setDraft(e.target.value),
    onKeyDown: e => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    }
  }), /*#__PURE__*/React.createElement(IconButton, {
    label: "Send task",
    size: 38,
    onClick: send,
    style: {
      background: draft.trim() ? "var(--action-primary-bg)" : "var(--action-disabled-bg)",
      color: draft.trim() ? "var(--action-primary-fg)" : "var(--action-disabled-fg)",
      border: "1px solid transparent"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "send",
    size: 15
  }))), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: "6px 0 0",
      font: "var(--type-mono)",
      color: "var(--text-faint)"
    }
  }, "Enter to send \xB7 Shift+Enter for new line")));
}
Object.assign(window, {
  TaskThread
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/TaskThread.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/AccessSection.jsx
try { (() => {
const {
  Button,
  Field,
  Input,
  Select,
  Textarea,
  Card,
  Eyebrow,
  Badge
} = window.MinkopsDesignSystem_6c27f0;
function InterestForm() {
  const [sent, setSent] = React.useState(false);
  return /*#__PURE__*/React.createElement(Card, {
    style: {
      display: "grid",
      gap: "16px",
      alignContent: "start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "6px"
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      font: "var(--type-h3)"
    }
  }, "Request access"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body-sm)",
      color: "var(--text-secondary)"
    }
  }, "Join the waiting list for our autonomous workforce.")), sent ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "8px",
      padding: "20px 0"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "ok"
  }, "Received"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body)"
    }
  }, "Thanks \u2014 we'll be in touch. We read every one of these ourselves.")) : /*#__PURE__*/React.createElement("form", {
    style: {
      display: "grid",
      gap: "12px"
    },
    onSubmit: e => {
      e.preventDefault();
      setSent(true);
    }
  }, /*#__PURE__*/React.createElement(Field, {
    label: "Full name",
    htmlFor: "if-name",
    required: true
  }, /*#__PURE__*/React.createElement(Input, {
    id: "if-name",
    placeholder: "Sarah Connor"
  })), /*#__PURE__*/React.createElement(Field, {
    label: "Work email",
    htmlFor: "if-email",
    required: true
  }, /*#__PURE__*/React.createElement(Input, {
    id: "if-email",
    type: "email",
    placeholder: "sarah@company.com"
  })), /*#__PURE__*/React.createElement(Field, {
    label: "Company",
    htmlFor: "if-co"
  }, /*#__PURE__*/React.createElement(Input, {
    id: "if-co",
    placeholder: "Cyberdyne Systems"
  })), /*#__PURE__*/React.createElement(Field, {
    label: "Primary interest",
    htmlFor: "if-int"
  }, /*#__PURE__*/React.createElement(Select, {
    id: "if-int",
    options: [{
      value: "general",
      label: "General enquiry"
    }, {
      value: "sales",
      label: "Sales & lead gen"
    }, {
      value: "support",
      label: "Customer support"
    }, {
      value: "marketing",
      label: "Marketing & content"
    }, {
      value: "operations",
      label: "Operations & HR"
    }, {
      value: "enterprise",
      label: "Enterprise custom solutions"
    }]
  })), /*#__PURE__*/React.createElement(Field, {
    label: "Message",
    htmlFor: "if-msg",
    hint: "Optional."
  }, /*#__PURE__*/React.createElement(Textarea, {
    id: "if-msg",
    rows: 3,
    placeholder: "Tell us about your needs\u2026"
  })), /*#__PURE__*/React.createElement(Button, {
    type: "submit",
    variant: "primary",
    size: "lg",
    fullWidth: true
  }, "Join waitlist")));
}
function AccessSection() {
  return /*#__PURE__*/React.createElement(Section, {
    eyebrow: "Get access",
    title: "Hire your first agent",
    tone: "sunken",
    lead: "Minkops is pre-sale. Early tenants get their fleet provisioned by hand, by us."
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 420px",
      gap: "24px",
      alignItems: "start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "16px"
    }
  }, [["Built before it's sold", "We run our own company on these agents first. Imel reads our inbox and drafts replies before a human opens it."], ["One agent, one role", "Each agent takes a whole job with disjoint skills — not a workflow step. They talk to each other and share one knowledge graph."], ["Humans stay in the loop", "Anything above an agent's authority threshold lands in your queue with a drafted answer. You approve, modify, or escalate."], ["Runs continuously", "A fleet runs 24×7, not as one-off jobs. Every human correction becomes training signal."]].map(([h, b]) => /*#__PURE__*/React.createElement("div", {
    key: h,
    style: {
      display: "grid",
      gap: "5px",
      paddingLeft: "14px",
      borderLeft: "2px solid var(--brand-ember)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-h4)"
    }
  }, h), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      maxWidth: "var(--measure)",
      font: "var(--type-body)",
      color: "var(--text-secondary)"
    }
  }, b)))), /*#__PURE__*/React.createElement(InterestForm, null)));
}
Object.assign(window, {
  AccessSection,
  InterestForm
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/AccessSection.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/EditorialPages.jsx
try { (() => {
const {
  Eyebrow,
  Card,
  Badge,
  Button,
  Icon
} = window.MinkopsDesignSystem_6c27f0;
const POSTS = [{
  tag: "Product proof",
  title: "Real, not a mockup",
  date: "2026-03-12",
  read: "3 min",
  excerpt: "A lot of AI agent demos are a slide deck wearing a UI skin. Here's the opposite: Imel handed an email it has never seen, start to finish, no cuts."
}, {
  tag: "Founder",
  title: "A five-person team needs leverage, not headcount",
  date: "2026-02-18",
  read: "4 min",
  excerpt: "The moment founders want to move faster, their first move is to hire. We've gone the opposite way — we build the AI employees we're selling, and run our own company on them first."
}, {
  tag: "Engineering",
  title: "Why our agents wait for a human at first",
  date: "2026-02-06",
  read: "5 min",
  excerpt: "Early graphs are deliberately more deterministic: more interrupts, more waiting for feedback. That human interaction data is the training signal."
}];
function BlogPage() {
  return /*#__PURE__*/React.createElement(Section, {
    eyebrow: "Blog",
    title: "Notes from a company that runs on its own product",
    lead: "No invented metrics, no implied customers. We write about what is actually running."
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "12px",
      maxWidth: 860
    }
  }, POSTS.map(p => /*#__PURE__*/React.createElement(Card, {
    key: p.title,
    style: {
      display: "grid",
      gap: "8px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "10px"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "neutral"
  }, p.tag), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      font: "var(--type-mono)",
      color: "var(--text-faint)"
    }
  }, p.date, " \xB7 ", p.read)), /*#__PURE__*/React.createElement("h3", {
    style: {
      font: "var(--type-h3)"
    }
  }, p.title), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      maxWidth: "var(--measure)",
      font: "var(--type-body)",
      color: "var(--text-secondary)"
    }
  }, p.excerpt), /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      font: "var(--type-body-sm)",
      fontWeight: "var(--fw-medium)",
      justifySelf: "start"
    }
  }, "Read the post")))));
}
function AboutPage() {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Section, {
    eyebrow: "About",
    title: "Minkops is under ten people",
    lead: "Most of us are wearing four or five hats before lunch. What makes that possible isn't hustle \u2014 it's that we build the AI employees we're selling before we sell them, and run our own company on them first."
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: "12px"
    }
  }, [["Under 10", "People on the team"], ["2", "Agents running in production"], ["24×7", "How a fleet runs — continuously, not as jobs"]].map(([n, l]) => /*#__PURE__*/React.createElement(Card, {
    key: l,
    tone: "sunken",
    style: {
      display: "grid",
      gap: "6px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-semibold) var(--fs-3xl)/1 var(--font-display)",
      letterSpacing: "var(--ls-display)"
    }
  }, n), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-body-sm)",
      color: "var(--text-secondary)"
    }
  }, l))))), /*#__PURE__*/React.createElement(Section, {
    eyebrow: "Family",
    title: "A product of Minkowski Home",
    tone: "sunken",
    lead: "Minkops sits alongside Myndral and Minkowski Home. Frontends live in apps/, agents and data work in services/ \u2014 the same discipline applies to the brand."
  }));
}
const ROLES = [{
  title: "Agent runtime engineer",
  place: "Toronto / Remote",
  type: "Full-time"
}, {
  title: "Applied AI engineer — evaluation",
  place: "Remote",
  type: "Full-time"
}, {
  title: "Founding designer",
  place: "Toronto / Remote",
  type: "Full-time"
}, {
  title: "Data engineer — knowledge graph",
  place: "Remote",
  type: "Contract"
}];
function CareersPage() {
  return /*#__PURE__*/React.createElement(Section, {
    eyebrow: "Careers",
    title: "Work on the thing that replaces the work",
    lead: "Small team, real responsibility, no hand-holding. Verification and HR enquiries go to hr@minkops.com."
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      border: "1px solid var(--border-default)",
      borderRadius: "var(--radius-3)",
      overflow: "hidden",
      maxWidth: 860
    }
  }, ROLES.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: r.title,
    style: {
      display: "flex",
      alignItems: "center",
      gap: "12px",
      padding: "14px 16px",
      borderTop: i ? "1px solid var(--border-hairline)" : "none"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "grid",
      gap: "3px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-h4)"
    }
  }, r.title), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, r.place, " \xB7 ", r.type)), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm",
    iconRight: /*#__PURE__*/React.createElement(Icon, {
      name: "chevronRight",
      size: 12
    })
  }, "Apply"))))));
}
Object.assign(window, {
  BlogPage,
  AboutPage,
  CareersPage
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/EditorialPages.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Funnel.jsx
try { (() => {
const {
  Button,
  Eyebrow,
  OptionRow,
  ProgressSteps,
  Card,
  Icon,
  Badge
} = window.MinkopsDesignSystem_6c27f0;
const QUESTIONS = [{
  id: "revenue",
  kicker: "Step 01 / Store stage",
  question: "What does your store pull in monthly?",
  subtext: "We use this to surface agents that match your operational scale.",
  type: "single",
  options: [{
    value: "pre",
    label: "Under $2,000",
    meta: "Early stage"
  }, {
    value: "growth",
    label: "$2,000 – $15,000",
    meta: "Growth"
  }, {
    value: "scale",
    label: "$15,000 – $75,000",
    meta: "Scaling"
  }, {
    value: "established",
    label: "$75,000+",
    meta: "Established"
  }]
}, {
  id: "time_sink",
  kicker: "Step 02 / Time audit",
  question: "Where does your week actually disappear?",
  subtext: "Select every area that pulls you away from the store itself.",
  type: "multi",
  options: [{
    value: "support",
    label: "Answering customer support calls & tickets"
  }, {
    value: "leads",
    label: "Following up on leads and abandoned carts"
  }, {
    value: "email",
    label: "Writing and sending email campaigns"
  }, {
    value: "social",
    label: "Creating social media content"
  }, {
    value: "ads",
    label: "Writing ad copy and creative assets"
  }, {
    value: "analytics",
    label: "Pulling reports and making sense of data"
  }]
}, {
  id: "pain",
  kicker: "Step 03 / Biggest bottleneck",
  question: "If you could eliminate one thing tomorrow, what would it be?",
  subtext: "This shapes which agent we recommend as your starting point.",
  type: "single",
  options: [{
    value: "support_calls",
    label: "The volume of inbound support calls"
  }, {
    value: "lead_calls",
    label: "Chasing leads that go cold after browsing"
  }, {
    value: "email_grind",
    label: "The constant grind of email marketing"
  }, {
    value: "social_content",
    label: "Showing up consistently on social media"
  }, {
    value: "ad_copy",
    label: "Writing ad creative that actually converts"
  }, {
    value: "reporting",
    label: "Making sense of performance numbers"
  }]
}, {
  id: "hours",
  kicker: "Step 04 / Weekly hours",
  question: "How many hours a week go into these tasks right now?",
  subtext: "Be honest — this is where your ROI calculation starts.",
  type: "single",
  options: [{
    value: "2",
    label: "Under 2 hours",
    meta: "Light lift"
  }, {
    value: "8",
    label: "2 – 8 hours",
    meta: "A full day"
  }, {
    value: "15",
    label: "8 – 15 hours",
    meta: "Nearly half your week"
  }, {
    value: "20",
    label: "15+ hours",
    meta: "This is a second job"
  }]
}];
const AGENT_MAP = {
  support: {
    name: "Kall",
    role: "Customer support rep",
    glyph: "support",
    desc: "Handles inbound customer calls autonomously — returns, refunds, FAQs, order status — without a single human touchpoint.",
    save: "8–12 hrs / wk"
  },
  leads: {
    name: "Leed",
    role: "Lead generation caller",
    glyph: "sales",
    desc: "Follows up on abandoned carts and browse-abandons via outbound call within minutes.",
    save: "4–7 hrs / wk"
  },
  email: {
    name: "Imel",
    role: "Email handler",
    glyph: "email",
    desc: "Writes, segments, schedules and sends full campaigns. Handles reply triage and follow-up sequences automatically.",
    save: "5–9 hrs / wk"
  },
  social: {
    name: "Eko",
    role: "Social media handler",
    glyph: "social",
    desc: "Generates branded posts, captions and scheduling queues across channels on autopilot.",
    save: "4–6 hrs / wk"
  },
  ads: {
    name: "Floc",
    role: "Content creator",
    glyph: "writer",
    desc: "Produces high-converting ad creative variants and branded content.",
    save: "3–5 hrs / wk"
  },
  analytics: {
    name: "Insi",
    role: "Business analyst",
    glyph: "analyst",
    desc: "Pulls cross-channel metrics into plain-language weekly digests. No dashboards, no spreadsheets — just answers.",
    save: "3–4 hrs / wk"
  }
};
const PRIORITY_MAP = {
  support_calls: "support",
  lead_calls: "leads",
  email_grind: "email",
  social_content: "social",
  ad_copy: "ads",
  reporting: "analytics"
};
const REVENUE_LABELS = {
  pre: "Early stage store",
  growth: "Growth stage store",
  scale: "Scaling store",
  established: "Established brand"
};
function Results({
  answers,
  onAccess,
  onRestart
}) {
  const sinks = answers.time_sink || [];
  const key = PRIORITY_MAP[answers.pain] || sinks[0] || "support";
  const hours = parseInt(answers.hours || "8", 10);
  const min = Math.round(hours * 0.45),
    max = Math.round(hours * 0.7);
  const pct = Math.min(100, Math.round(max / hours * 100));
  const primary = AGENT_MAP[key];
  const secondary = sinks.filter(k => k !== key).slice(0, 2).map(k => AGENT_MAP[k]).filter(Boolean);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "20px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "10px"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "ok"
  }, "Analysis complete"), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, REVENUE_LABELS[answers.revenue] || "Your store")), /*#__PURE__*/React.createElement("h3", {
    style: {
      font: "var(--type-h2)",
      maxWidth: "24ch"
    }
  }, "You're losing ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--brand-rust)"
    }
  }, hours, "+ hours"), " a week to work Minkops can own."), /*#__PURE__*/React.createElement(Card, {
    tone: "sunken",
    style: {
      display: "grid",
      gap: "12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "baseline",
      gap: "10px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-eyebrow)",
      textTransform: "uppercase",
      color: "var(--text-muted)"
    }
  }, "Estimated weekly hours recovered"), /*#__PURE__*/React.createElement("strong", {
    style: {
      marginLeft: "auto",
      font: "var(--fw-semibold) var(--fs-xl)/1 var(--font-display)",
      letterSpacing: "var(--ls-display)"
    }
  }, min, "\u2013", max, " hrs")), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 6,
      background: "var(--n-100)",
      borderRadius: "var(--radius-1)",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: pct + "%",
      height: "100%",
      background: "var(--brand-ember)",
      transition: "width var(--dur-slow) var(--ease-out)"
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, "Current load ", hours, " hrs \xB7 up to ", pct, "% automated")), /*#__PURE__*/React.createElement(Card, {
    accentEdge: true,
    style: {
      display: "grid",
      gap: "10px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "10px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "grid",
      placeItems: "center",
      width: 34,
      height: 34,
      borderRadius: "var(--radius-2)",
      background: "var(--surface-inset)",
      color: "var(--brand-rust)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: primary.glyph,
    size: 22
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "grid",
      gap: "2px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-semibold) var(--fs-lg)/1.1 var(--font-display)",
      letterSpacing: "var(--ls-display)"
    }
  }, primary.name), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-body-sm)",
      color: "var(--text-secondary)"
    }
  }, primary.role)), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      font: "var(--type-mono)",
      color: "var(--brand-rust)"
    }
  }, "Saves ", primary.save)), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body-sm)",
      color: "var(--text-secondary)",
      maxWidth: "var(--measure)"
    }
  }, primary.desc)), secondary.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(" + secondary.length + ", 1fr)",
      gap: "10px"
    }
  }, secondary.map(a => /*#__PURE__*/React.createElement(Card, {
    key: a.name,
    tone: "sunken",
    style: {
      display: "grid",
      gap: "6px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-medium) var(--fs-md)/1.1 var(--font-display)"
    }
  }, a.name), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-body-sm)",
      color: "var(--text-secondary)"
    }
  }, a.role), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, a.save)))) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "12px",
      paddingTop: "4px"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "primary",
    onClick: onAccess
  }, "Request access"), /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "ghost",
    onClick: onRestart
  }, "Start over"), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, "No credit card. No setup fee.")));
}
function Funnel({
  onAccess
}) {
  const [step, setStep] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [selected, setSelected] = React.useState([]);
  const [done, setDone] = React.useState(false);
  const q = QUESTIONS[step];
  const pick = v => setSelected(s => q.type === "multi" ? s.includes(v) ? s.filter(x => x !== v) : [...s, v] : [v]);
  const advance = () => {
    const next = {
      ...answers,
      [q.id]: q.type === "multi" ? selected : selected[0]
    };
    setAnswers(next);
    setSelected([]);
    if (step < QUESTIONS.length - 1) setStep(step + 1);else setDone(true);
  };
  const back = () => {
    setSelected([]);
    setStep(Math.max(0, step - 1));
  };
  const restart = () => {
    setStep(0);
    setAnswers({});
    setSelected([]);
    setDone(false);
  };
  return /*#__PURE__*/React.createElement(Section, {
    eyebrow: "Find your agent stack",
    title: "Tell us about your store. We'll tell you what to automate.",
    lead: "Four honest questions, ninety seconds, a specific answer \u2014 no sales call required to get it."
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 720,
      border: "1px solid var(--border-default)",
      borderRadius: "var(--radius-3)",
      padding: "28px",
      background: "var(--surface-page)"
    }
  }, done ? /*#__PURE__*/React.createElement(Results, {
    answers: answers,
    onAccess: onAccess,
    onRestart: restart
  }) : /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "18px"
    }
  }, /*#__PURE__*/React.createElement(ProgressSteps, {
    total: QUESTIONS.length,
    current: step
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "8px"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, q.kicker), /*#__PURE__*/React.createElement("h3", {
    style: {
      font: "var(--type-h3)",
      fontSize: "var(--fs-xl)"
    }
  }, q.question), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body-sm)",
      color: "var(--text-muted)"
    }
  }, q.subtext, q.type === "multi" ? " Select all that apply." : "")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "8px"
    },
    role: "group",
    "aria-label": q.question
  }, q.options.map(o => /*#__PURE__*/React.createElement(OptionRow, {
    key: o.value,
    label: o.label,
    meta: o.meta,
    multi: q.type === "multi",
    selected: selected.includes(o.value),
    onSelect: () => pick(o.value)
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "10px"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "primary",
    disabled: !selected.length,
    onClick: advance,
    iconRight: /*#__PURE__*/React.createElement(Icon, {
      name: "chevronRight",
      size: 16
    })
  }, step === QUESTIONS.length - 1 ? "Show my results" : "Continue"), step > 0 ? /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    onClick: back,
    iconLeft: /*#__PURE__*/React.createElement(Icon, {
      name: "chevronLeft",
      size: 14
    })
  }, "Back") : null))));
}
Object.assign(window, {
  Funnel
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Funnel.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Landing.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  Button,
  Eyebrow,
  AgentTile,
  Icon,
  StatusDot
} = window.MinkopsDesignSystem_6c27f0;
const ROSTER = [{
  name: "Imel",
  tool: "Email handler",
  domain: "Generic",
  glyph: "email",
  status: "Live"
}, {
  name: "Kall",
  tool: "Customer support rep",
  domain: "Generic",
  glyph: "support",
  status: "Live"
}, {
  name: "Leed",
  tool: "Lead generation caller",
  domain: "Generic",
  glyph: "sales",
  status: "Next"
}, {
  name: "Eko",
  tool: "Social media handler",
  domain: "Generic",
  glyph: "social",
  status: "Next"
}, {
  name: "Floc",
  tool: "Content creator",
  domain: "Generic",
  glyph: "writer",
  status: "Next"
}, {
  name: "Insi",
  tool: "Business analyst",
  domain: "Generic",
  glyph: "analyst",
  status: "In build"
}, {
  name: "Kim",
  tool: "Store manager's assistant",
  domain: "Generic",
  glyph: "retail",
  status: "In build"
}, {
  name: "Ora",
  tool: "Moodboard generator",
  domain: "Interior design",
  glyph: "designer",
  status: "In build"
}, {
  name: "Cruz",
  tool: "Manager's assistant",
  domain: "Fast food",
  glyph: "manager",
  status: "In build"
}, {
  name: "Hosi",
  tool: "Front of house",
  domain: "Fast food",
  glyph: "host",
  status: "In build"
}, {
  name: "Prex",
  tool: "Back of house",
  domain: "Fast food",
  glyph: "kitchen",
  status: "In build"
}];
function Hero({
  onAccess
}) {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: "96px 32px 72px",
      background: "var(--surface-page)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-w)",
      margin: "0 auto",
      display: "grid",
      gap: "32px"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    rule: true
  }, "A suite of AI employees"), /*#__PURE__*/React.createElement("h1", {
    style: {
      font: "var(--fw-semibold) var(--fs-5xl)/1.04 var(--font-display)",
      letterSpacing: "var(--ls-display)",
      maxWidth: "18ch"
    }
  }, "Intelligence, ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--brand-rust)"
    }
  }, "redefined")), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      maxWidth: "var(--measure)",
      font: "var(--type-body-lg)",
      color: "var(--text-secondary)"
    }
  }, "Hire an AI employee the way you'd hire a person \u2014 for a specific role, with real responsibility. Except it starts on day one, works nights and weekends, and never asks for a raise."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "12px",
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "primary",
    onClick: onAccess,
    iconRight: /*#__PURE__*/React.createElement(Icon, {
      name: "chevronRight",
      size: 16
    })
  }, "Request access"), /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "secondary"
  }, "See how they work together"), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "8px"
    }
  }, /*#__PURE__*/React.createElement(StatusDot, {
    status: "active",
    pulse: true,
    label: "Imel and Kall run our own inbox today"
  })))));
}
function RosterGrid({
  onAccess
}) {
  return /*#__PURE__*/React.createElement(Section, {
    eyebrow: "The roster \xB7 11 agents",
    title: "Know your future employees",
    lead: "Each agent replaces one role with disjoint skills, not one task. They intercommunicate and read the same company knowledge a human colleague would.",
    tone: "sunken"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(248px, 1fr))",
      gap: "12px"
    }
  }, ROSTER.map(a => /*#__PURE__*/React.createElement(AgentTile, _extends({
    key: a.name
  }, a, {
    onClick: onAccess
  })))), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-mono)",
      color: "var(--text-muted)"
    }
  }, "Live = running in production today. Next = in active development. In build = designed, not yet shipped."));
}
Object.assign(window, {
  Hero,
  RosterGrid,
  ROSTER
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Landing.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Orchestration.jsx
try { (() => {
const {
  FlowNode,
  FlowArrow,
  Eyebrow,
  Button,
  Icon
} = window.MinkopsDesignSystem_6c27f0;
const FLOWS = [{
  title: "01 · Automated marketing campaign",
  desc: "From idea to published ad copy without human intervention.",
  nodes: [{
    agent: "Floc",
    role: "Copywriter"
  }, {
    arrow: "Drafts copy"
  }, {
    agent: "Ora",
    role: "Visual experience"
  }, {
    arrow: "Generates assets"
  }, {
    output: "Published campaign"
  }]
}, {
  title: "02 · Intelligent social engagement",
  desc: "Handling public perception and private support simultaneously.",
  nodes: [{
    agent: "Eko",
    role: "Social handler"
  }, {
    arrow: "Detects complaint"
  }, {
    agent: "Kall",
    role: "Support rep"
  }, {
    arrow: "Resolves ticket"
  }, {
    agent: "Eko",
    role: "Social handler"
  }]
}, {
  title: "03 · QSR operations",
  desc: "Zero-man fast food store management.",
  nodes: [{
    agent: "Hosi",
    role: "Front of house"
  }, {
    arrow: "Order taken"
  }, {
    agent: "Cruz",
    role: "Store manager"
  }, {
    arrow: "Relays ticket"
  }, {
    agent: "Prex",
    role: "Kitchen staff"
  }]
}];
function OrchestrationPage({
  onAccess
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("section", {
    style: {
      padding: "80px 32px 56px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-w)",
      margin: "0 auto",
      display: "grid",
      gap: "20px"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, {
    rule: true
  }, "Orchestration"), /*#__PURE__*/React.createElement("h1", {
    style: {
      font: "var(--fw-semibold) var(--fs-4xl)/1.06 var(--font-display)",
      letterSpacing: "var(--ls-display)",
      maxWidth: "20ch"
    }
  }, "Orchestrated intelligence"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      maxWidth: "var(--measure)",
      font: "var(--type-body-lg)",
      color: "var(--text-secondary)"
    }
  }, "Agents don't just chat. They work together \u2014 one hands off to the next through a shared knowledge graph and policy model, and a human only steps in above the authority threshold."))), FLOWS.map((flow, i) => /*#__PURE__*/React.createElement("section", {
    key: flow.title,
    style: {
      padding: "48px 32px",
      borderTop: "1px solid var(--border-hairline)",
      background: i % 2 ? "var(--surface-sunken)" : "var(--surface-page)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-w)",
      margin: "0 auto",
      display: "grid",
      gap: "20px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "6px"
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      font: "var(--type-h3)",
      fontSize: "var(--fs-xl)"
    }
  }, flow.title), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body)",
      color: "var(--text-secondary)"
    }
  }, flow.desc)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "4px",
      flexWrap: "wrap"
    }
  }, flow.nodes.map((n, j) => n.arrow ? /*#__PURE__*/React.createElement(FlowArrow, {
    key: j,
    label: n.arrow
  }) : /*#__PURE__*/React.createElement(FlowNode, {
    key: j,
    agent: n.agent,
    role: n.role,
    output: Boolean(n.output),
    label: n.output
  })))))), /*#__PURE__*/React.createElement("section", {
    style: {
      padding: "64px 32px",
      borderTop: "1px solid var(--border-hairline)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-w)",
      margin: "0 auto",
      display: "flex",
      alignItems: "center",
      gap: "20px",
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      font: "var(--type-h2)"
    }
  }, "Build your fleet"), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "primary",
    onClick: onAccess,
    iconRight: /*#__PURE__*/React.createElement(Icon, {
      name: "chevronRight",
      size: 16
    })
  }, "Request access")))));
}
Object.assign(window, {
  OrchestrationPage
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Orchestration.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/SiteChrome.jsx
try { (() => {
const {
  Button,
  Eyebrow
} = window.MinkopsDesignSystem_6c27f0;
const PAGES = [{
  key: "agents",
  label: "Agents"
}, {
  key: "orchestration",
  label: "Orchestration"
}, {
  key: "about",
  label: "About"
}, {
  key: "blog",
  label: "Blog"
}, {
  key: "careers",
  label: "Careers"
}];
function SiteNav({
  route,
  onRoute
}) {
  return /*#__PURE__*/React.createElement("nav", {
    style: {
      position: "sticky",
      top: 0,
      zIndex: 5,
      display: "flex",
      alignItems: "center",
      gap: "8px",
      height: "var(--site-nav-h)",
      padding: "0 32px",
      background: "var(--surface-page)",
      borderBottom: "1px solid var(--border-hairline)"
    }
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => onRoute("agents"),
    style: {
      display: "flex",
      alignItems: "center",
      gap: "9px",
      background: "none",
      border: "none",
      padding: 0,
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: "50%",
      background: "var(--brand-ember)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-bold) var(--fs-lg)/1 var(--font-display)",
      letterSpacing: "var(--ls-wordmark)",
      color: "var(--text-primary)"
    }
  }, "minkops")), /*#__PURE__*/React.createElement("div", {
    style: {
      marginLeft: "auto",
      display: "flex",
      alignItems: "center",
      gap: "4px"
    }
  }, PAGES.map(p => /*#__PURE__*/React.createElement("button", {
    key: p.key,
    type: "button",
    onClick: () => onRoute(p.key),
    style: {
      padding: "7px 11px",
      background: "none",
      border: "none",
      cursor: "pointer",
      borderRadius: "var(--radius-2)",
      font: "var(--fw-medium) var(--fs-sm)/1 var(--font-text)",
      color: route === p.key ? "var(--text-primary)" : "var(--text-secondary)",
      boxShadow: route === p.key ? "inset 0 -2px 0 var(--brand-ember)" : "none"
    }
  }, p.label)), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "10px"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "md",
    onClick: () => onRoute("access")
  }, "Get access"))));
}
const FOOTER_COLS = [{
  head: "Platform",
  links: ["Agents", "Orchestration", "Pricing"]
}, {
  head: "Company",
  links: ["About us", "Careers", "Blog", "info@minkops.com", "hr@minkops.com", "LinkedIn"]
}, {
  head: "More from the family",
  links: ["Myndral", "Minkowski Home"]
}];
function SiteFooter() {
  return /*#__PURE__*/React.createElement("footer", {
    style: {
      background: "var(--surface-inverse)",
      color: "var(--text-inverse)",
      padding: "56px 32px 24px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-w)",
      margin: "0 auto",
      display: "grid",
      gridTemplateColumns: "1.4fr repeat(3, 1fr)",
      gap: "32px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "12px",
      alignContent: "start"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "9px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: "50%",
      background: "var(--brand-ember)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--fw-bold) var(--fs-lg)/1 var(--font-display)",
      letterSpacing: "var(--ls-wordmark)"
    }
  }, "minkops")), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body-sm)",
      color: "var(--text-inverse-muted)"
    }
  }, "Operating system for zero-man companies"), /*#__PURE__*/React.createElement("address", {
    style: {
      font: "var(--type-mono)",
      color: "var(--text-inverse-muted)",
      fontStyle: "normal",
      lineHeight: 1.7
    }
  }, "375 University Avenue Suite 3215", /*#__PURE__*/React.createElement("br", null), "Toronto, ON M5G 2J5", /*#__PURE__*/React.createElement("br", null), "Canada")), FOOTER_COLS.map(c => /*#__PURE__*/React.createElement("div", {
    key: c.head,
    style: {
      display: "grid",
      gap: "9px",
      alignContent: "start"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      font: "var(--type-eyebrow)",
      letterSpacing: "var(--ls-eyebrow)",
      textTransform: "uppercase",
      color: "var(--text-inverse-muted)"
    }
  }, c.head), c.links.map(l => /*#__PURE__*/React.createElement("a", {
    key: l,
    href: "#",
    style: {
      font: "var(--type-body-sm)",
      color: "var(--text-inverse)",
      borderBottom: "none"
    }
  }, l))))), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-w)",
      margin: "40px auto 0",
      paddingTop: "16px",
      borderTop: "1px solid var(--border-inverse)",
      display: "flex",
      gap: "16px",
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-mono)",
      color: "var(--text-inverse-muted)"
    }
  }, "\xA9 2026 Minkops. A product of Minkowski Home. All rights reserved."), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      display: "flex",
      gap: "16px"
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      font: "var(--type-mono)",
      color: "var(--text-inverse-muted)",
      borderBottom: "none"
    }
  }, "Privacy policy"), /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      font: "var(--type-mono)",
      color: "var(--text-inverse-muted)",
      borderBottom: "none"
    }
  }, "Terms of service"))));
}
function Section({
  eyebrow,
  title,
  lead,
  children,
  tone = "page"
}) {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: "var(--pad-section)",
      background: tone === "sunken" ? "var(--surface-sunken)" : "var(--surface-page)",
      borderTop: "1px solid var(--border-hairline)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--container-w)",
      margin: "0 auto",
      display: "grid",
      gap: "28px"
    }
  }, eyebrow || title ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "12px",
      maxWidth: "var(--measure)"
    }
  }, eyebrow ? /*#__PURE__*/React.createElement(Eyebrow, {
    rule: true
  }, eyebrow) : null, title ? /*#__PURE__*/React.createElement("h2", {
    style: {
      font: "var(--type-h1)"
    }
  }, title) : null, lead ? /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      font: "var(--type-body-lg)",
      color: "var(--text-secondary)"
    }
  }, lead) : null) : null, children));
}
Object.assign(window, {
  SiteNav,
  SiteFooter,
  Section,
  SITE_PAGES: PAGES
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/SiteChrome.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Eyebrow = __ds_scope.Eyebrow;

__ds_ns.Icon = __ds_scope.Icon;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.PriorityPill = __ds_scope.PriorityPill;

__ds_ns.StatusDot = __ds_scope.StatusDot;

__ds_ns.Toggle = __ds_scope.Toggle;

__ds_ns.EmptyState = __ds_scope.EmptyState;

__ds_ns.ProgressSteps = __ds_scope.ProgressSteps;

__ds_ns.TypingIndicator = __ds_scope.TypingIndicator;

__ds_ns.Field = __ds_scope.Field;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.OptionRow = __ds_scope.OptionRow;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Textarea = __ds_scope.Textarea;

__ds_ns.AgentRow = __ds_scope.AgentRow;

__ds_ns.AgentTile = __ds_scope.AgentTile;

__ds_ns.FlowNode = __ds_scope.FlowNode;

__ds_ns.FlowArrow = __ds_scope.FlowArrow;

__ds_ns.InterruptCard = __ds_scope.InterruptCard;

__ds_ns.MessageBubble = __ds_scope.MessageBubble;

})();
