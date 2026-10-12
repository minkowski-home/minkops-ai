import type { ReactNode } from "react";

export function Spinner() {
  return <span className="activity-spinner" aria-hidden="true" />;
}

export function LoadingIndicator({ children }: { children: ReactNode }) {
  return <p className="loading-feedback" role="status"><Spinner />{children}</p>;
}

export function RetryMessage({ children, onRetry }: { children: ReactNode; onRetry: () => void }) {
  return <div className="retry-feedback"><p role="alert" className="form-message">{children}</p>
    <button type="button" className="button button-ghost" onClick={onRetry}>Retry now</button></div>;
}
