import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useSelector, useDispatch } from "react-redux";
import type { AppDispatch } from "../store";
import { selectMeetingsList, selectSearch, fetchMeetings } from "../store/meetingsSlice";
import { MeetingCard } from "../components/MeetingCard";
import { Navbar } from "../components/Navbar";
import { SearchBar } from "../components/SearchBar";
import { SearchResults } from "../components/SearchResults";

export function Dashboard() {
  const dispatch = useDispatch<AppDispatch>();
  const { list: meetings, listStatus, listError } = useSelector(selectMeetingsList);
  const { searchQuery } = useSelector(selectSearch);
  const [filterPlatform, setFilterPlatform] = useState<string>("all");

  useEffect(() => {
    dispatch(fetchMeetings());
  }, [dispatch]);

  const isLoading = listStatus === "loading" || listStatus === "idle";
  const error = listStatus === "failed" ? listError : null;
  const isSearching = searchQuery.trim().length > 0;

  // Aggregate all calendar events across all meetings
  const allUpcomingEvents = useMemo(() => {
    const list: {
      meetingId: string;
      meetingTitle: string;
      title: string;
      date: string;
      relative: string;
      days: number | null | undefined;
      speaker: string | null | undefined;
    }[] = [];

    meetings.forEach((m) => {
      if (m.calendar_events && m.calendar_events.length > 0) {
        m.calendar_events.forEach((ev) => {
          list.push({
            meetingId: m.id,
            meetingTitle: m.title,
            title: ev.title,
            date: ev.formatted_date || ev.event_date,
            relative: ev.relative_time,
            days: ev.days_from_now,
            speaker: ev.speaker,
          });
        });
      }
    });
    return list;
  }, [meetings]);

  // Aggregate metrics
  const totalTasks = useMemo(() => {
    return meetings.reduce(
      (acc, m) => acc + (m.action_items ? m.action_items.filter((a) => !a.done).length : 0),
      0
    );
  }, [meetings]);

  const filteredMeetings = useMemo(() => {
    if (filterPlatform === "all") return meetings;
    return meetings.filter(
      (m) => (m.platform || "Meeting").toLowerCase() === filterPlatform.toLowerCase()
    );
  }, [meetings, filterPlatform]);

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingBottom: "4rem" }}>
        {/* Hero Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1rem",
            marginBottom: "1.75rem",
          }}
        >
          <div>
            <h1 style={{ fontSize: "1.875rem", fontWeight: 800, letterSpacing: "-0.02em", margin: 0 }}>
              Meeting Intelligence Workspace
            </h1>
            <p style={{ color: "var(--color-text-muted)", fontSize: "0.875rem", marginTop: "0.25rem" }}>
              Audio transcription, speaker dialogue breakdowns, Zoom meetings, and calendar scheduling.
            </p>
          </div>

          <Link
            to="/upload"
            className="btn btn-primary"
            style={{
              padding: "0.65rem 1.25rem",
              fontSize: "0.875rem",
              fontWeight: 600,
              boxShadow: "0 4px 15px rgba(108, 99, 255, 0.35)",
            }}
          >
            + New Meeting
          </Link>
        </div>

        {/* Quick Stats Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            gap: "1rem",
            marginBottom: "1.75rem",
          }}
        >
          <div
            className="glass-card"
            style={{
              padding: "1.1rem",
              background: "rgba(255, 255, 255, 0.03)",
              border: "1px solid var(--color-border)",
            }}
          >
            <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase" }}>
              Total Meetings
            </div>
            <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--color-text)", marginTop: "0.25rem" }}>
              {meetings.length}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--color-success)", marginTop: "0.15rem" }}>
              {meetings.filter((m) => m.status === "processed").length} processed
            </div>
          </div>

          <div
            className="glass-card"
            style={{
              padding: "1.1rem",
              background: "rgba(245, 158, 11, 0.04)",
              border: "1px solid rgba(245, 158, 11, 0.25)",
            }}
          >
            <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-warning)", textTransform: "uppercase" }}>
              📅 Scheduled Tests & Events
            </div>
            <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--color-warning)", marginTop: "0.25rem" }}>
              {allUpcomingEvents.length}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginTop: "0.15rem" }}>
              From meeting dialogue
            </div>
          </div>

          <div
            className="glass-card"
            style={{
              padding: "1.1rem",
              background: "rgba(56, 189, 248, 0.04)",
              border: "1px solid rgba(56, 189, 248, 0.25)",
            }}
          >
            <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>
              Pending Tasks
            </div>
            <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "#38bdf8", marginTop: "0.25rem" }}>
              {totalTasks}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginTop: "0.15rem" }}>
              Action items to complete
            </div>
          </div>

          <div
            className="glass-card"
            style={{
              padding: "1.1rem",
              background: "rgba(168, 85, 247, 0.04)",
              border: "1px solid rgba(168, 85, 247, 0.25)",
            }}
          >
            <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-purple)", textTransform: "uppercase" }}>
              Multi-Language AI
            </div>
            <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--color-purple)", marginTop: "0.25rem" }}>
              Active
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginTop: "0.15rem" }}>
              Whisper + Smart Engine
            </div>
          </div>
        </div>

        {/* Upcoming Calendar Events Highlight (Requirement 5) */}
        {allUpcomingEvents.length > 0 && !isSearching && (
          <div
            className="glass-card"
            style={{
              marginBottom: "1.75rem",
              padding: "1.25rem",
              background: "linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(108, 99, 255, 0.05) 100%)",
              border: "1px solid rgba(245, 158, 11, 0.3)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "1.25rem" }}>📅</span>
                <h3 style={{ fontSize: "0.9375rem", fontWeight: 700, margin: 0, color: "var(--color-text)" }}>
                  Upcoming Scheduled Events & Tests
                </h3>
              </div>
              <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                Detected from meeting discussions
              </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "0.75rem" }}>
              {allUpcomingEvents.slice(0, 3).map((ev, i) => (
                <Link
                  key={i}
                  to={`/meetings/${ev.meetingId}`}
                  style={{ textDecoration: "none", color: "inherit" }}
                >
                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.25)",
                      border: "1px solid var(--color-border)",
                      borderRadius: "var(--radius)",
                      padding: "0.75rem 1rem",
                      transition: "transform 0.15s ease",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                      <span style={{ fontWeight: 700, fontSize: "0.875rem", color: "var(--color-warning)" }}>
                        ⏰ {ev.title}
                      </span>
                      <span
                        style={{
                          fontSize: "0.7rem",
                          background: "rgba(245, 158, 11, 0.2)",
                          color: "var(--color-warning)",
                          padding: "0.1rem 0.45rem",
                          borderRadius: "999px",
                          fontWeight: 700,
                        }}
                      >
                        {ev.relative}
                      </span>
                    </div>
                    <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--color-text)" }}>
                      Target: <strong>{ev.date}</strong>
                    </p>
                    <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                      In: {ev.meetingTitle}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Search Bar */}
        <SearchBar />

        {isSearching ? (
          <SearchResults />
        ) : (
          <>
            {/* Filter Pills */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                margin: "1.25rem 0 1rem",
                overflowX: "auto",
                paddingBottom: "0.25rem",
              }}
            >
              <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase" }}>
                Filter:
              </span>
              {[
                { id: "all", label: `All (${meetings.length})` },
                { id: "zoom", label: "Zoom Meetings" },
                { id: "google meet", label: "Google Meet" },
                { id: "audio recording", label: "Audio Files" },
              ].map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFilterPlatform(f.id)}
                  style={{
                    background: filterPlatform === f.id ? "var(--color-accent)" : "var(--color-surface)",
                    color: filterPlatform === f.id ? "white" : "var(--color-text-muted)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "999px",
                    padding: "0.25rem 0.75rem",
                    fontSize: "0.75rem",
                    fontWeight: filterPlatform === f.id ? 700 : 500,
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {[1, 2, 3].map((i) => (
                  <div key={i} className="skeleton" style={{ height: "96px", width: "100%" }} />
                ))}
              </div>
            )}

            {!isLoading && error && (
              <div className="error-card">
                <p>{error}</p>
              </div>
            )}

            {!isLoading && !error && filteredMeetings.length === 0 && (
              <div className="empty-state">
                <div className="empty-state-icon">📁</div>
                <h3 style={{ fontSize: "1.125rem", marginBottom: "0.5rem" }}>
                  {filterPlatform === "all" ? "No meetings uploaded yet" : "No meetings match this filter"}
                </h3>
                <p style={{ marginBottom: "1.5rem" }}>
                  Upload a Zoom recording, audio file, or transcript to get started.
                </p>
                <Link to="/upload" className="btn btn-primary">
                  Upload your first meeting
                </Link>
              </div>
            )}

            {!isLoading && !error && filteredMeetings.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                {filteredMeetings.map((meeting) => (
                  <MeetingCard key={meeting.id} meeting={meeting} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
