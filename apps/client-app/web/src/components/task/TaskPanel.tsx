/**
 * TaskPanel — center pane of the dashboard.
 *
 * Provides a chat interface for assigning tasks to agents. The human
 * types a task description and sends it; agents respond inline.
 *
 * Current implementation is fully local with mock history. When the
 * backend is ready, replace the local state updates with:
 *   POST /api/tasks          — create a new task, returns { taskId }
 *   POST /api/tasks/:id/messages — send a message in an existing task
 *   GET  /api/tasks/:id/messages — poll or SSE-stream agent responses
 *
 * The textarea auto-expands up to a CSS-capped max-height, then scrolls.
 * Shift+Enter inserts a newline; Enter alone submits the message.
 */

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type KeyboardEvent,
  type ChangeEvent
} from "react";
import type { ChatMessage } from "../../types/task";
import { MOCK_TASKS } from "../../mock/tasks";
import { useAuth } from "../../contexts/AuthContext";
import { IconSend, IconAgents } from "../icons";
import "./TaskPanel.css";

/** Formats an ISO timestamp to a short human-readable time. */
function formatTime(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Auto-resize a textarea to fit its content. */
function autoResize(el: HTMLTextAreaElement) {
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

export default function TaskPanel() {
  const { user } = useAuth();

  // Seed with the first mock task's history; in reality this would be fetched
  const [messages, setMessages] = useState<ChatMessage[]>(
    MOCK_TASKS[0]?.messages ?? []
  );
  const [draft, setDraft] = useState("");
  const [isAgentTyping, setIsAgentTyping] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom whenever messages update
  useEffect(() => {
    const el = messageListRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, isAgentTyping]);

  const handleInput = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    setDraft(e.target.value);
    autoResize(e.target);
  }, []);

  const sendMessage = useCallback(() => {
    const content = draft.trim();
    if (!content) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: "human",
      content,
      timestamp: new Date().toISOString(),
      agentId: null,
      agentName: null
    };

    setMessages((prev) => [...prev, userMessage]);
    setDraft("");

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    // Simulate agent typing delay — replace with real SSE/polling
    setIsAgentTyping(true);
    const timer = setTimeout(() => {
      setIsAgentTyping(false);
      const agentReply: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        role: "agent",
        content: "I've received your task and I'm working on it. I'll update you shortly with results.",
        timestamp: new Date().toISOString(),
        agentId: "agent-synapse",
        agentName: "Synapse"
      };
      setMessages((prev) => [...prev, agentReply]);
    }, 1800);

    // TODO: POST /api/tasks/:id/messages { content }
    return () => clearTimeout(timer);
  }, [draft]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Enter submits; Shift+Enter inserts newline
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    },
    [sendMessage]
  );

  const userInitials = user?.name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("") ?? "?";

  return (
    <div className="task-panel">
      {/* Header */}
      <div className="task-panel-header">
        <div>
          <div className="task-panel-title">Assign a Task</div>
          <div className="task-panel-subtitle">
            Describe what you need — agents pick it up automatically.
          </div>
        </div>
        <div className="task-panel-agent-badge">
          <span className="task-panel-agent-dot" aria-hidden="true" />
          3 agents active
        </div>
      </div>

      {/* Message history */}
      {messages.length === 0 ? (
        <div className="task-empty-state">
          <div className="task-empty-icon">
            <IconAgents size={22} />
          </div>
          <div className="task-empty-headline">No tasks yet</div>
          <div className="task-empty-hint">
            Type a task below and your agents will get to work immediately.
          </div>
        </div>
      ) : (
        <div className="task-message-list" ref={messageListRef}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} userInitials={userInitials} />
          ))}

          {isAgentTyping && (
            <div className="typing-indicator">
              <div className="message-avatar" aria-hidden="true">S</div>
              <div className="typing-dots" aria-label="Agent is typing">
                <span /><span /><span />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Input area */}
      <div className="task-input-area">
        <div className="task-input-row">
          <textarea
            ref={textareaRef}
            className="task-textarea"
            placeholder="Describe a task for your agents…"
            value={draft}
            rows={1}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            aria-label="Task input"
          />
          <button
            className="task-send-btn"
            onClick={sendMessage}
            disabled={!draft.trim() || isAgentTyping}
            aria-label="Send task"
            title="Send (Enter)"
          >
            <IconSend size={15} />
          </button>
        </div>
        <p className="task-input-hint">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
  userInitials: string;
}

function MessageBubble({ message, userInitials }: MessageBubbleProps) {
  const isHuman = message.role === "human";
  const senderLabel = isHuman ? "You" : message.agentName ?? "Agent";
  const avatarLabel = isHuman
    ? userInitials
    : (message.agentName ?? "A").slice(0, 1).toUpperCase();

  return (
    <div className={`message-row${isHuman ? " human" : ""}`}>
      <div className={`message-avatar${isHuman ? " human-avatar" : ""}`} aria-hidden="true">
        {avatarLabel}
      </div>

      <div className="message-body">
        <div className="message-sender">{senderLabel}</div>
        <div className="message-bubble">{message.content}</div>
        <div className="message-time">{formatTime(message.timestamp)}</div>
      </div>
    </div>
  );
}
