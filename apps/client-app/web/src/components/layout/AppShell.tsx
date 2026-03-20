import { useState, useRef, useCallback } from "react";
import { useAuth } from "../../contexts/AuthContext";
import Sidebar from "./Sidebar";
import { IconBell } from "../icons";
import "./AppShell.css";

interface AppShellProps {
  /** Left pane content — agent list. */
  leftPane?: React.ReactNode;
  /** Center pane content — task/chat area. */
  centerPane?: React.ReactNode;
  /** Right pane content — human interrupt queue. */
  rightPane?: React.ReactNode;
  /** Controls injected into the header right slot (e.g. ThemeSelector). */
  headerRight?: React.ReactNode;
  /** Page title shown in the header breadcrumb area. */
  pageTitle?: string;
  /** Number of pending interrupts to show on the bell badge. */
  interruptCount?: number;
}

/** Initial and boundary widths (px) for the resizable side panes. */
const PANE_LEFT_INIT  = 288;
const PANE_RIGHT_INIT = 320;
const PANE_LEFT_MIN   = 180;
const PANE_LEFT_MAX   = 520;
const PANE_RIGHT_MIN  = 200;
const PANE_RIGHT_MAX  = 520;

const clamp = (v: number, min: number, max: number) =>
  Math.min(max, Math.max(min, v));

type DragState = {
  handle: "left" | "right";
  startX: number;
  startWidth: number;
};

export default function AppShell({
  leftPane,
  centerPane,
  rightPane,
  headerRight,
  pageTitle = "Dashboard",
  interruptCount = 0
}: AppShellProps) {
  const { user } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const [leftW,  setLeftW]  = useState(PANE_LEFT_INIT);
  const [rightW, setRightW] = useState(PANE_RIGHT_INIT);
  const [isDragging, setIsDragging] = useState(false);

  /**
   * dragRef holds ephemeral drag state that must not trigger re-renders on
   * every mousemove. We only call setState for the width values.
   */
  const dragRef = useRef<DragState | null>(null);

  /**
   * Initiates a drag on the given handle. Pointer capture ensures that
   * pointermove / pointerup events are routed to this element even when the
   * cursor leaves it, giving smooth, uninterrupted resizing.
   */
  const startDrag = useCallback(
    (e: React.PointerEvent<HTMLDivElement>, handle: "left" | "right") => {
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      dragRef.current = {
        handle,
        startX: e.clientX,
        startWidth: handle === "left" ? leftW : rightW,
      };
      setIsDragging(true);
    },
    [leftW, rightW]
  );

  const onDragMove = useCallback((e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    const delta = e.clientX - drag.startX;
    if (drag.handle === "left") {
      setLeftW(clamp(drag.startWidth + delta, PANE_LEFT_MIN, PANE_LEFT_MAX));
    } else {
      // Right handle: dragging right shrinks the right pane.
      setRightW(clamp(drag.startWidth - delta, PANE_RIGHT_MIN, PANE_RIGHT_MAX));
    }
  }, []);

  const endDrag = useCallback(() => {
    dragRef.current = null;
    setIsDragging(false);
  }, []);

  return (
    <div className={`app-shell${isDragging ? " is-dragging" : ""}`}>
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
      />

      <div className="app-shell-main">
        <header className="app-shell-header glass-toolbar soft-enter">
          <div className="app-shell-header-left">
            <span className="app-shell-page-title">{pageTitle}</span>
          </div>

          <div className="app-shell-header-right">
            <div className="header-bell-wrap">
              <button
                className="header-icon-btn glass-pill"
                aria-label={`${interruptCount} items need attention`}
                title="Human interrupt queue"
              >
                <IconBell size={18} />
              </button>
              {interruptCount > 0 && (
                <span className="header-badge" aria-hidden="true">
                  {interruptCount > 99 ? "99+" : interruptCount}
                </span>
              )}
            </div>

            {/* Tenant name chip */}
            {user?.tenantName && (
              <span className="header-tenant-chip glass-pill">{user.tenantName}</span>
            )}

            {headerRight}
          </div>
        </header>

        <div
          className="app-shell-content"
          style={{
            "--pane-left-w":  `${leftW}px`,
            "--pane-right-w": `${rightW}px`,
          } as React.CSSProperties}
        >
          <section className="app-pane app-pane-secondary glass-panel-vibrant soft-enter">
            {leftPane}
          </section>

          <div
            className="pane-resize-handle"
            onPointerDown={(e) => startDrag(e, "left")}
            onPointerMove={onDragMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            aria-hidden="true"
          />

          <section className="app-pane app-pane-primary glass-panel-vibrant soft-enter">
            {centerPane}
          </section>

          <div
            className="pane-resize-handle"
            onPointerDown={(e) => startDrag(e, "right")}
            onPointerMove={onDragMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            aria-hidden="true"
          />

          <section className="app-pane app-pane-secondary glass-panel-vibrant soft-enter">
            {rightPane}
          </section>
        </div>
      </div>
    </div>
  );
}
