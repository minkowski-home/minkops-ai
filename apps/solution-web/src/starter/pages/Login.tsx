import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { solution } from "@minkops/solution-manifest";
import { resolveStarterUi } from "../config";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("operator@acmecorp.com");
  const [password, setPassword] = useState("password");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const ui = resolveStarterUi(solution);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    await login(email, password);
    navigate("/dashboard", { replace: true });
  }

  return <main className="login-screen">
    <section className="login-story"><div className="login-wordmark"><span className="wordmark-dot" />{ui.productName}</div><div><h1>Welcome back</h1><p>Sign in to your operator dashboard. Your fleet has been running while you were away.</p></div><small>{solution.displayName}</small></section>
    <section className="login-form-panel"><form onSubmit={submit}><div><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} /></div><div><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></div><button className="button button-primary" type="submit" disabled={isSubmitting}>{isSubmitting ? "Signing in…" : "Sign in"}</button><p>Access is restricted to authorised tenants only.</p></form></section>
  </main>;
}
