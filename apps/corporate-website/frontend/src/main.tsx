import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// Cascade order matters: tokens, then element defaults, then components, then compositions.
// Tokens come straight from the design system; webfonts load from index.html and
// the site uses the default (unthemed) palette, so fonts.css and themes.css stay out.
import "@minkops/design/tokens/colors.css";
import "@minkops/design/tokens/typography.css";
import "@minkops/design/tokens/spacing.css";
import "@minkops/design/tokens/surfaces.css";
import "@minkops/design/tokens/motion.css";
import "@minkops/design/tokens/layout.css";
import "./styles/base.css";
import "./ui/ui.css";
import "./layout/layout.css";
import "./sections/landing.css";
import "./pages/pages.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
