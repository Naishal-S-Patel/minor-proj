import { Link } from "react-router-dom";
import type { Meeting } from "../api/client";

const STATUS_COLORS: Record<Meeting["status"], { bg: string; color: string; dot: string }> = {
  uploaded: { bg: "var(--color-surface-2)", color: "var(--color-text-muted)", dot: "var(--color-text-muted)" },
  transcribing: { bg: "rgba(245,158,11,0.15)", color: "var(--color-warning)", dot: "var(--color-warning)" },
  cleaning: { bg: "rgba(99,102,241,0.15)", color: "#818cf8", dot: "#818cf8" },
  analyzing: { bg: "rgba(168,85,247,0.15)", color: "var(--color-purple)", dot: "var(--color-purple)" },
  processed: { bg: "rgba(34,197,94,0.15)", color: "var(--color-success)", dot: "var(--color-success)" },
  failed: { bg: "rgba(239,68,68,0.15)", color: "var(--color-error)", dot: "var(--color-error)" },
};

const SENTIMENT_EMOJI: Record<string, string> = {
  positive: "😊",
  neutral: "😐",
  negative: "😟",
};

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function MeetingCard({ meeting }: { meeting: Meeting }) {
  const sc = STATUS_COLORS[meeting.status];
  const calendarCount = meeting.calendar_events?.length || 0;
  const firstEvent = meeting.calendar_events?.[0];

  return (
    <Link
      to={`/meetings/${meeting.id}`}
      style={{ textDecoration: "none", color: "inherit" }}
    >
      <div
        className="glass-card"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "1rem",
          transition: "all 0.2s ease",
          cursor: "pointer",
          borderRadius: "var(--radius-lg)",
          padding: "1.25rem",
          background: "rgba(255, 255, 255, 0.04)",
          border: "1px solid var(--color-border)",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "translateY(-3px)";
          e.currentTarget.style.borderColor = "var(--color-accent)";
          e.currentTarget.style.boxShadow = "0 10px 28px rgba(0,0,0,0.35)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "translateY(0)";
          e.currentTarget.style.borderColor = "var(--color-border)";
          e.currentTarget.style.boxShadow = "none";
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Top badges: platform, Zoom ID, language */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.4rem" }}>
            {meeting.platform && (
              <span
                style={{
                  fontSize: "0.6875rem",
                  fontWeight: 700,
                  color: "var(--color-accent)",
                  background: "rgba(108, 99, 255, 0.12)",
                  padding: "0.1rem 0.5rem",
                  borderRadius: "999px",
                }}
              >
                {meeting.platform}
              </span>
            )}

            {meeting.meeting_id_code && (
              <span
                style={{
                  fontSize: "0.6875rem",
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  background: "rgba(255, 255, 255, 0.06)",
                  padding: "0.1rem 0.5rem",
                  borderRadius: "999px",
                }}
              >
                ID: {meeting.meeting_id_code}
              </span>
            )}

            {meeting.detected_language && meeting.detected_language !== "en" && (
              <span
                style={{
                  fontSize: "0.6875rem",
                  fontWeight: 600,
                  color: "var(--color-purple)",
                  background: "rgba(168, 85, 247, 0.12)",
                  padding: "0.1rem 0.5rem",
                  borderRadius: "999px",
                }}
              >
                🌐 {meeting.detected_language.toUpperCase()}
              </span>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.375rem" }}>
            <span style={{ fontWeight: 700, fontSize: "1.0625rem", color: "var(--color-text)" }}>
              {meeting.title}
            </span>
            {meeting.status === "processed" && meeting.sentiment && (
              <span style={{ fontSize: "0.9375rem" }}>{SENTIMENT_EMOJI[meeting.sentiment] ?? ""}</span>
            )}
          </div>

          {meeting.status === "processed" && meeting.summary && (
            <p
              style={{
                fontSize: "0.8125rem",
                color: "var(--color-text-muted)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                marginBottom: "0.5rem",
              }}
            >
              {meeting.summary}
            </p>
          )}

          {/* Bottom metadata tags */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.65rem", flexWrap: "wrap", fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
            <span>📅 {formatDate(meeting.created_at)}</span>

            {meeting.speakers && meeting.speakers.length > 0 && (
              <span>👥 {meeting.speakers.length} speaker{meeting.speakers.length > 1 ? "s" : ""}</span>
            )}

            {meeting.action_items && meeting.action_items.length > 0 && (
              <span style={{ color: "#38bdf8" }}>
                ✅ {meeting.action_items.filter((a) => !a.done).length} pending
              </span>
            )}

            {calendarCount > 0 && firstEvent && (
              <span
                style={{
                  background: "rgba(245, 158, 11, 0.12)",
                  color: "var(--color-warning)",
                  padding: "0.1rem 0.5rem",
                  borderRadius: "999px",
                  fontWeight: 700,
                }}
              >
                ⏰ {firstEvent.title} ({firstEvent.relative_time})
              </span>
            )}
          </div>
        </div>

        <span
          className="status-pill"
          style={{
            background: sc.bg,
            color: sc.color,
            flexShrink: 0,
            fontSize: "0.75rem",
            fontWeight: 700,
          }}
        >
          <span
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: sc.dot,
            }}
          />
          {meeting.status === "transcribing" ? "Transcribing..." : meeting.status}
        </span>
      </div>
    </Link>
  );
}
