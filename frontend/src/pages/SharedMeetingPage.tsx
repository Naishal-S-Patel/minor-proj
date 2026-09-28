import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import type { Meeting } from "../api/client";
import { api } from "../api/client";
import { InsightsPanel } from "../components/insights/InsightsPanel";

export function SharedMeetingPage() {
  const { token } = useParams<{ token: string }>();
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.getSharedMeeting(token)
      .then(setMeeting)
      .catch(() => setError("This link is no longer active"))
      .finally(() => setIsLoading(false));
  }, [token]);

  if (isLoading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: "40px", height: "40px", border: "3px solid var(--color-surface-2)", borderTopColor: "var(--color-accent)", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <nav style={{
        padding: "0.75rem 1.5rem",
        background: "rgba(10, 15, 30, 0.8)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--color-border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}>
        <Link to="/" style={{ display: "flex", alignItems: "center", gap: "0.625rem", textDecoration: "none", color: "var(--color-text)", fontWeight: 700, fontSize: "1.125rem" }}>
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: "32px", height: "32px", borderRadius: "8px",
            background: "linear-gradient(135deg, var(--color-accent), var(--color-purple))", fontSize: "1rem",
          }}>M</span>
          MeetingAI
        </Link>
        <span style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)" }}>
          View only &middot; <Link to="/login">Sign in</Link> to create your own
        </span>
      </nav>

      <div className="container">
        {error ? (
          <div className="empty-state">
            <div className="empty-state-icon">&#128274;</div>
            <h3 style={{ fontSize: "1.125rem", marginBottom: "0.5rem" }}>Link no longer active</h3>
            <p>This shared meeting link has been revoked or doesn't exist.</p>
            <Link to="/" style={{ marginTop: "1rem", display: "inline-block" }}>Go to MeetingAI</Link>
          </div>
        ) : meeting ? (
          <>
            <div style={{ marginBottom: "1.5rem" }}>
              <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>{meeting.title}</h1>
              <p style={{ marginTop: "0.5rem", color: "var(--color-text-muted)", fontSize: "0.8125rem" }}>
                Shared meeting &middot; {new Date(meeting.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
              </p>
            </div>
            <InsightsPanel meeting={meeting} />
          </>
        ) : null}
      </div>
    </div>
  );
}
