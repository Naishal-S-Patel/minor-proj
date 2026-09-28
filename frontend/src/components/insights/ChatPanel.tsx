import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { api } from "../../api/client";

interface ChatPanelProps {
  meetingId: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

const SUGGESTIONS = [
  "Who owns the action items?",
  "What was the main decision?",
  "What are the key topics discussed?",
];

export function ChatPanel({ meetingId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const sendMessage = async (question: string) => {
    if (!question.trim() || isLoading) return;

    const userMsg: ChatMessage = { role: "user", text: question.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setError(null);
    setIsLoading(true);

    try {
      const { answer } = await api.chatMeeting(meetingId, question.trim());
      setMessages((prev) => [...prev, { role: "assistant", text: answer }]);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to get answer";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {messages.length === 0 && !isLoading && (
        <div className="chat-empty-state">
          <p style={{ fontSize: "0.9375rem", marginBottom: "0.75rem" }}>
            Ask anything about this meeting
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                className="chip"
                style={{
                  background: "var(--color-surface-2)",
                  color: "var(--color-text-muted)",
                  border: "1px solid var(--color-border)",
                  cursor: "pointer",
                  fontSize: "0.8125rem",
                }}
                onClick={() => sendMessage(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {messages.length > 0 && (
        <div className="chat-history" ref={historyRef}>
          {messages.map((msg, i) => (
            <div
              key={i}
              className={msg.role === "user" ? "chat-bubble-user" : "chat-bubble-assistant"}
            >
              {msg.text}
            </div>
          ))}
          {isLoading && (
            <div className="chat-bubble-assistant chat-typing">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          )}
        </div>
      )}

      {error && (
        <div
          style={{
            padding: "0.625rem 0.875rem",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "var(--radius)",
            color: "#fca5a5",
            fontSize: "0.8125rem",
          }}
        >
          {error}
        </div>
      )}

      <div className="chat-input-row">
        <textarea
          ref={textareaRef}
          className="input"
          placeholder="Ask a question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          style={{ resize: "none", flex: 1 }}
          disabled={isLoading}
        />
        <button
          className="btn btn-primary"
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || isLoading}
          style={{ padding: "0.625rem 1rem", flexShrink: 0 }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
