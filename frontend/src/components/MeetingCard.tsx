import { Link } from "react-router-dom";
import type { Meeting } from "../api/client";

const STATUS_COLORS: Record<Meeting["status"], { bg: string; color: string; dot: string }> = {
  uploaded: { bg: "var(--color-surface-2)", color: "var(--color-text-muted)", dot: "var(--color-text-muted)" },
  transcribing: { bg: "rgba(245,158,11,0.12)", color: "var(--color-warning)", dot: "var(--color-warning)" },
  cleaning: { bg: "rgba(99,102,241,0.12)", color: "#818cf8", dot: "#818cf8" },
  analyzing: { bg: "rgba(168,85,247,0.12)", color: "var(--color-purple)", dot: "var(--color-purple)" },
  processed: { bg: "rgba(34,197,94,0.12)", color: "var(--color-success)", dot: "var(--color-success)" },
  failed: { bg: "rgba(239,68,68,0.12)", color: "var(--color-error)", dot: "var(--color-error)" },
};

const SENTIMENT_EMOJI: Record<string, string> = {
  positive: "\u{1F60A}",
  neutral: "\u{1F610}",
  negative: "\u{1F61F}",
};

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function MeetingCard({ meeting }: { meeting: Meeting }) {
  const sc = STATUS_COLORS[meeting.status];

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
          transition: "transform 0.2s, box-shadow 0.2s",
          cursor: "pointer",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "translateY(-2px)";
          e.currentTarget.style.boxShadow = "0 8px 24px rgba(0,0,0,0.3)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "translateY(0)";
          e.currentTarget.style.boxShadow = "none";
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.375rem" }}>
            <span style={{ fontWeight: 600, fontSize: "1rem", color: "var(--color-text)" }}>
              {meeting.title}
            </span>
            {meeting.status === "processed" && meeting.sentiment && (
              <span style={{ fontSize: "0.875rem" }}>{SENTIMENT_EMOJI[meeting.sentiment] ?? ""}</span>
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
                marginBottom: "0.375rem",
              }}
            >
              {meeting.summary.length > 80 ? meeting.summary.slice(0, 80) + "\u2026" : meeting.summary}
            </p>
          )}

          <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
            {formatDate(meeting.created_at)}
          </p>
        </div>

        <span
          className="status-pill"
          style={{
            background: sc.bg,
            color: sc.color,
            flexShrink: 0,
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
          {meeting.status}
        </span>
      </div>
    </Link>
  );
}
