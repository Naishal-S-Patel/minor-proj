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
  "📅 When is the test or next deadline?",
  "💡 What key decisions were finalized?",
  "✅ Who owns the action items?",
  "🗣️ Who spoke and what did they say?",
  "📝 Give me an executive summary",
];

export function ChatPanel({ meetingId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
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

  const copyToClipboard = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
      {/* Suggestions Bar */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            className="chip"
            style={{
              background: "rgba(255, 255, 255, 0.05)",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              cursor: "pointer",
              fontSize: "0.75rem",
              padding: "0.3rem 0.65rem",
              borderRadius: "999px",
            }}
            onClick={() => sendMessage(s)}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Chat History */}
      <div
        className="chat-history"
        ref={historyRef}
        style={{
          minHeight: "180px",
          maxHeight: "420px",
          overflowY: "auto",
          padding: "0.75rem",
          background: "rgba(0, 0, 0, 0.2)",
          borderRadius: "var(--radius)",
          border: "1px solid var(--color-border)",
        }}
      >
        {messages.length === 0 && !isLoading && (
          <div className="chat-empty-state" style={{ padding: "2.5rem 1rem" }}>
            <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>💬</div>
            <p style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--color-text)" }}>
              Context-Aware Meeting Intelligence Chat
            </p>
            <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)", maxWidth: "420px", margin: "0.25rem auto 0" }}>
              Ask anything about dates, tests, dialogues, decisions, or attendees. Answers are generated directly from the verified meeting transcript.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={msg.role === "user" ? "chat-bubble-user" : "chat-bubble-assistant"}
            style={{ position: "relative" }}
          >
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{msg.text}</div>
            {msg.role === "assistant" && (
              <button
                type="button"
                onClick={() => copyToClipboard(msg.text, i)}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.25rem",
                  marginTop: "0.5rem",
                  background: "none",
                  border: "none",
                  color: "var(--color-text-muted)",
                  fontSize: "0.7rem",
                  cursor: "pointer",
                  padding: 0,
                }}
              >
                {copiedIdx === i ? "✓ Copied" : "📋 Copy response"}
              </button>
            )}
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

      {/* Input row */}
      <div className="chat-input-row" style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <textarea
          ref={textareaRef}
          className="input"
          placeholder="Ask a question about this meeting (e.g. When is the test?)..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          style={{ resize: "none", flex: 1, padding: "0.65rem 0.875rem" }}
          disabled={isLoading}
        />
        <button
          className="btn btn-primary"
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || isLoading}
          style={{ padding: "0.65rem 1.25rem", flexShrink: 0, fontWeight: 600 }}
        >
          {isLoading ? "Thinking..." : "Ask AI"}
        </button>
      </div>
    </div>
  );
}
