import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// Cascade order matters: tokens, then element defaults, then components, then compositions.
import "./styles/tokens.css";
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
