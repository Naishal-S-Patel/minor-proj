import type { CalendarEvent } from "../../api/client";

interface CalendarEventsSectionProps {
  events: CalendarEvent[] | undefined;
  meetingTitle: string;
  meetingId: string;
}

export function CalendarEventsSection({
  events,
  meetingTitle,
  meetingId,
}: CalendarEventsSectionProps) {
  if (!events || events.length === 0) {
    return (
      <div className="empty-state" style={{ padding: "2.5rem 1rem" }}>
        <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>📅</div>
        <p style={{ fontWeight: 600, color: "var(--color-text)" }}>No Scheduled Events Found</p>
        <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)", margin: "0.25rem 0 0" }}>
          No future dates, exams, or relative deadlines (like "test after 3 days") were mentioned in this transcript.
        </p>
      </div>
    );
  }

  const buildGoogleCalendarUrl = (ev: CalendarEvent) => {
    // Format date YYYYMMDD
    const dateStr = ev.event_date.replace(/-/g, "");
    const title = encodeURIComponent(`${ev.title} (${meetingTitle})`);
    const details = encodeURIComponent(
      `Context: ${ev.context}\nAnnounced by: ${ev.speaker || "Meeting Participant"}\nOrigin: AI Meeting Intelligence`
    );
    // All day event: dates=YYYYMMDD/YYYYMMDD
    return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${title}&dates=${dateStr}/${dateStr}&details=${details}`;
  };

  const getCategoryBadge = (cat: string) => {
    const isExam = cat.toLowerCase().includes("exam") || cat.toLowerCase().includes("test");
    if (isExam) {
      return {
        bg: "rgba(239, 68, 68, 0.15)",
        color: "#f87171",
        border: "rgba(239, 68, 68, 0.3)",
        label: "📝 Test / Exam",
      };
    }
    return {
      bg: "rgba(59, 130, 246, 0.15)",
      color: "#60a5fa",
      border: "rgba(59, 130, 246, 0.3)",
      label: "📌 Deadline / Event",
    };
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.5rem" }}>
        <div>
          <h3 style={{ fontSize: "0.9375rem", fontWeight: 700, margin: 0 }}>
            Scheduled Events & Deadlines
          </h3>
          <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", margin: "0.15rem 0 0" }}>
            Extracted from spoken dialogues & commitments
          </p>
        </div>

        <a
          href={`/api/meetings/${meetingId}/calendar/ics`}
          download
          className="btn btn-secondary"
          style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem" }}
        >
          📥 Download All (.ics)
        </a>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
        {events.map((ev, i) => {
          const badge = getCategoryBadge(ev.category || "general");
          const daysText =
            ev.days_from_now !== null && ev.days_from_now !== undefined
              ? ev.days_from_now === 1
                ? "Tomorrow"
                : `In ${ev.days_from_now} days`
              : ev.relative_time;

          return (
            <div
              key={ev.id || i}
              style={{
                background: "rgba(255, 255, 255, 0.03)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-lg)",
                padding: "1rem 1.25rem",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                flexWrap: "wrap",
                gap: "1rem",
                transition: "all 0.2s ease",
              }}
            >
              <div style={{ flex: 1, minWidth: "260px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.375rem" }}>
                  <span
                    style={{
                      background: badge.bg,
                      color: badge.color,
                      border: `1px solid ${badge.border}`,
                      borderRadius: "999px",
                      padding: "0.15rem 0.55rem",
                      fontSize: "0.7rem",
                      fontWeight: 700,
                    }}
                  >
                    {badge.label}
                  </span>
                  <span
                    style={{
                      background: "rgba(245, 158, 11, 0.15)",
                      color: "var(--color-warning)",
                      borderRadius: "999px",
                      padding: "0.15rem 0.55rem",
                      fontSize: "0.7rem",
                      fontWeight: 700,
                    }}
                  >
                    ⏰ {daysText}
                  </span>
                </div>

                <h4 style={{ fontSize: "1.0625rem", fontWeight: 700, margin: "0.25rem 0" }}>
                  {ev.title}
                </h4>

                <p style={{ fontSize: "0.8125rem", color: "var(--color-text)", margin: "0.25rem 0" }}>
                  📅 Target Date: <strong>{ev.formatted_date || ev.event_date}</strong>
                  {ev.speaker && (
                    <span style={{ color: "var(--color-text-muted)" }}>
                      {" "}&bull; Announced by: <strong>{ev.speaker}</strong>
                    </span>
                  )}
                </p>

                {ev.context && (
                  <p
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--color-text-muted)",
                      background: "rgba(0, 0, 0, 0.25)",
                      padding: "0.4rem 0.65rem",
                      borderRadius: "var(--radius)",
                      margin: "0.5rem 0 0",
                      borderLeft: "2px solid var(--color-accent)",
                      fontStyle: "italic",
                    }}
                  >
                    "{ev.context}"
                  </p>
                )}
              </div>

              {/* Action Buttons */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", minWidth: "150px" }}>
                <a
                  href={buildGoogleCalendarUrl(ev)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-primary"
                  style={{
                    fontSize: "0.75rem",
                    padding: "0.45rem 0.75rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.35rem",
                  }}
                >
                  <span>📅</span> Add to Google Cal
                </a>
                <a
                  href={`/api/meetings/${meetingId}/calendar/ics`}
                  download
                  className="btn btn-secondary"
                  style={{
                    fontSize: "0.75rem",
                    padding: "0.4rem 0.75rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.35rem",
                  }}
                >
                  <span>💻</span> Outlook / Apple (.ics)
                </a>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

