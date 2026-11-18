import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSelector, useDispatch } from "react-redux";
import type { AppDispatch } from "../store";
import {
  type MeetingStatus,
  IN_PROGRESS_STATUSES,
  POLL_INTERVAL_MS,
  api,
} from "../api/client";
import { selectMeetingDetail, fetchMeeting, clearSelectedMeeting } from "../store/meetingsSlice";
import { Navbar } from "../components/Navbar";
import { InsightsPanel } from "../components/insights/InsightsPanel";
import { ShareModal } from "../components/ShareModal";

const PIPELINE_STEPS: { key: MeetingStatus; label: string; icon: string }[] = [
  { key: "uploaded", label: "Uploaded", icon: "📁" },
  { key: "transcribing", label: "Transcribing (Live)", icon: "🎙️" },
  { key: "cleaning", label: "Cleaning", icon: "🧹" },
  { key: "analyzing", label: "AI Analysis", icon: "✨" },
  { key: "processed", label: "Done", icon: "✓" },
];

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function getStepState(
  stepKey: MeetingStatus,
  currentStatus: MeetingStatus,
): "done" | "active" | "pending" {
  const stepOrder = PIPELINE_STEPS.map((s) => s.key);
  const currentIdx = stepOrder.indexOf(currentStatus);
  const stepIdx = stepOrder.indexOf(stepKey);

  if (currentStatus === "failed") {
    return stepIdx <= currentIdx ? "done" : "pending";
  }
  if (currentStatus === "processed") return "done";
  if (stepIdx < currentIdx) return "done";
  if (stepIdx === currentIdx) return "active";
  return "pending";
}

function StatusStepper({ status }: { status: MeetingStatus }) {
  return (
    <div
      className="glass-card"
      style={{
        display: "flex",
        gap: "1.25rem",
        padding: "1rem 1.25rem",
        marginBottom: "1.5rem",
        flexWrap: "wrap",
        alignItems: "center",
      }}
    >
      {PIPELINE_STEPS.map((step) => {
        const state = getStepState(step.key, status);
        return (
          <div
            key={step.key}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              opacity: state === "pending" ? 0.35 : 1,
            }}
          >
            <span
              style={{
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.75rem",
                fontWeight: "bold",
                flexShrink: 0,
                backgroundColor:
                  state === "done"
                    ? "var(--color-success)"
                    : state === "active"
                      ? "var(--color-warning)"
                      : "var(--color-surface-2)",
                color: state === "pending" ? "var(--color-text-muted)" : "white",
                boxShadow:
                  state === "active" ? "0 0 14px rgba(245, 158, 11, 0.5)" : "none",
              }}
            >
              {state === "done" ? "✓" : state === "active" ? "↻" : step.icon}
            </span>
            <span style={{ fontSize: "0.8125rem", fontWeight: state === "active" ? 700 : 500 }}>
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function LiveAudioVisualizer() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "3px", height: "18px" }}>
      {[0.4, 0.8, 0.5, 1.0, 0.7, 0.3, 0.9, 0.6].map((h, i) => (
        <span
          key={i}
          style={{
            width: "3px",
            height: `${h * 100}%`,
            background: "var(--color-accent)",
            borderRadius: "99px",
            animation: `pulse 0.8s ease-in-out infinite alternate`,
            animationDelay: `${i * 0.12}s`,
          }}
        />
      ))}
    </div>
  );
}

export function MeetingDetail() {
  const { id } = useParams<{ id: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const { selected: meeting, selectedStatus, selectedError } = useSelector(selectMeetingDetail);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamEndRef = useRef<HTMLDivElement>(null);
  const [isShareModalOpen, setIsShareModalOpen] = useState(false);
  const [copiedId, setCopiedId] = useState(false);

  useEffect(() => {
    if (!id) return;

    const poll = () => {
      dispatch(fetchMeeting(id) as any)
        .unwrap()
        .then((data: any) => {
          if (IN_PROGRESS_STATUSES.includes(data.status)) {
            timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
          }
        })
        .catch(() => {});
    };

    poll();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      dispatch(clearSelectedMeeting());
    };
  }, [id, dispatch]);

  // Auto-scroll live streaming transcript
  useEffect(() => {
    if (meeting?.status === "transcribing" && streamEndRef.current) {
      streamEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [meeting?.live_transcript_lines]);

  const copyMeetingId = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  const isLoading = selectedStatus === "loading" || selectedStatus === "idle";
  const error = selectedStatus === "failed" ? selectedError : null;

  if (isLoading) {
    return (
      <>
        <Navbar />
        <div className="container">
          <div className="skeleton" style={{ height: "32px", width: "320px", marginBottom: "1rem" }} />
          <div className="skeleton" style={{ height: "18px", width: "220px", marginBottom: "2rem" }} />
          <div className="skeleton" style={{ height: "64px", width: "100%", marginBottom: "1.5rem" }} />
          <div className="skeleton" style={{ height: "260px", width: "100%" }} />
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Navbar />
        <div className="container">
          <div className="error-card">
            <p style={{ marginBottom: "1rem" }}>{error}</p>
            <Link to="/" className="btn btn-secondary" style={{ fontSize: "0.8125rem" }}>
              Back to Dashboard
            </Link>
          </div>
        </div>
      </>
    );
  }

  if (!meeting) {
    return (
      <>
        <Navbar />
        <div className="container">
          <div className="empty-state">
            <div className="empty-state-icon">🔍</div>
            <p>Meeting not found.</p>
            <Link to="/" style={{ marginTop: "1rem", display: "inline-block" }}>
              Back to Dashboard
            </Link>
          </div>
        </div>
      </>
    );
  }

  const isInProgress = IN_PROGRESS_STATUSES.includes(meeting.status);
  const isProcessed = meeting.status === "processed";
  const liveLines = meeting.live_transcript_lines || [];

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingBottom: "4rem" }}>
        <Link to="/" className="back-link">
          &larr; Back to Dashboard
        </Link>

        {/* Top Header Card */}
        <div
          className="glass-card"
          style={{
            marginBottom: "1.5rem",
            padding: "1.5rem",
            background: "linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(108, 99, 255, 0.05) 100%)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
            <div style={{ flex: 1, minWidth: "280px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
                {meeting.platform && (
                  <span
                    style={{
                      background: "rgba(108, 99, 255, 0.15)",
                      color: "var(--color-accent)",
                      border: "1px solid rgba(108, 99, 255, 0.3)",
                      borderRadius: "999px",
                      padding: "0.15rem 0.6rem",
                      fontSize: "0.75rem",
                      fontWeight: 700,
                    }}
                  >
                    📹 {meeting.platform}
                  </span>
                )}

                {meeting.meeting_id_code && (
                  <button
                    type="button"
                    onClick={() => copyMeetingId(meeting.meeting_id_code!)}
                    style={{
                      background: "rgba(255, 255, 255, 0.08)",
                      border: "1px solid var(--color-border)",
                      color: "var(--color-text)",
                      borderRadius: "999px",
                      padding: "0.15rem 0.65rem",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.3rem",
                    }}
                    title="Click to copy Meeting ID"
                  >
                    <span>ID: {meeting.meeting_id_code}</span>
                    <span style={{ opacity: 0.7 }}>{copiedId ? "✓" : "📋"}</span>
                  </button>
                )}

                {(meeting.detected_language || meeting.language) && (
                  <span
                    style={{
                      background: "rgba(168, 85, 247, 0.15)",
                      color: "var(--color-purple)",
                      borderRadius: "999px",
                      padding: "0.15rem 0.6rem",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}
                  >
                    🌐 {meeting.detected_language ? meeting.detected_language.toUpperCase() : meeting.language}
                  </span>
                )}
              </div>

              <h1 style={{ fontSize: "1.625rem", fontWeight: 800, letterSpacing: "-0.01em" }}>
                {meeting.title}
              </h1>

              <p style={{ marginTop: "0.5rem", color: "var(--color-text-muted)", fontSize: "0.8125rem" }}>
                Created {formatDate(meeting.created_at)}
                {meeting.updated_at !== meeting.created_at && (
                  <> &middot; Updated {formatDate(meeting.updated_at)}</>
                )}
                {meeting.audio_duration_seconds && (
                  <> &middot; ⏱️ Duration {formatDuration(meeting.audio_duration_seconds)}</>
                )}
                {meeting.audio_filename && (
                  <> &middot; 🎵 {meeting.audio_filename}</>
                )}
              </p>
            </div>

            {/* Actions & Status Pill */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
              {isProcessed && (
                <div className="export-btn-group" style={{ display: "flex", gap: "0.375rem" }}>
                  <button
                    onClick={() => api.exportMeeting(meeting.id, "pdf")}
                    className="btn btn-secondary"
                    style={{ fontSize: "0.75rem", padding: "0.4rem 0.75rem" }}
                  >
                    📥 PDF
                  </button>
                  <button
                    onClick={() => api.exportMeeting(meeting.id, "csv")}
                    className="btn btn-secondary"
                    style={{ fontSize: "0.75rem", padding: "0.4rem 0.75rem" }}
                  >
                    📊 CSV
                  </button>
                  {meeting.calendar_events && meeting.calendar_events.length > 0 && (
                    <button
                      onClick={() => api.downloadCalendarIcs(meeting.id)}
                      className="btn btn-secondary"
                      style={{ fontSize: "0.75rem", padding: "0.4rem 0.75rem" }}
                      title="Download .ics Calendar Events"
                    >
                      📅 Calendar (.ics)
                    </button>
                  )}
                  <button
                    onClick={() => setIsShareModalOpen(true)}
                    className="btn btn-secondary"
                    style={{ fontSize: "0.75rem", padding: "0.4rem 0.75rem" }}
                  >
                    🔗 Share
                  </button>
                </div>
              )}

              <span
                className="status-pill"
                style={{
                  background:
                    meeting.status === "processed"
                      ? "rgba(34,197,94,0.15)"
                      : meeting.status === "failed"
                        ? "rgba(239,68,68,0.15)"
                        : meeting.status === "transcribing"
                          ? "rgba(245,158,11,0.15)"
                          : "rgba(168,85,247,0.15)",
                  color:
                    meeting.status === "processed"
                      ? "var(--color-success)"
                      : meeting.status === "failed"
                        ? "var(--color-error)"
                        : meeting.status === "transcribing"
                          ? "var(--color-warning)"
                          : "var(--color-purple)",
                  fontWeight: 700,
                  fontSize: "0.8125rem",
                  padding: "0.35rem 0.85rem",
                }}
              >
                {meeting.status === "transcribing" ? "🎙️ Transcribing..." : meeting.status}
              </span>
            </div>
          </div>
        </div>

        {isInProgress && <StatusStepper status={meeting.status} />}

        {/* Real-time Line-by-Line Transcription Stream Studio (Requirement 1) */}
        {meeting.status === "transcribing" && (
          <div
            className="glass-card animate-fade-in"
            style={{
              marginBottom: "1.5rem",
              padding: "1.25rem 1.5rem",
              border: "1px solid rgba(245, 158, 11, 0.4)",
              background: "linear-gradient(180deg, rgba(245, 158, 11, 0.05) 0%, rgba(10, 15, 30, 0.6) 100%)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem", flexWrap: "wrap", gap: "0.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.35rem",
                    background: "rgba(239, 68, 68, 0.2)",
                    color: "#f87171",
                    padding: "0.2rem 0.65rem",
                    borderRadius: "999px",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                  }}
                >
                  <span
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: "#ef4444",
                      animation: "pulse 1s infinite alternate",
                    }}
                  />
                  LIVE STREAMING TRANSCRIPTION
                </span>
                <LiveAudioVisualizer />
              </div>

              <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                {liveLines.length > 0
                  ? `⚡ Recognized ${liveLines.length} spoken line${liveLines.length > 1 ? "s" : ""} in real time`
                  : "Audio chunks processing with Whisper..."}
              </span>
            </div>

            {/* Line-by-Line Stream Terminal */}
            <div
              style={{
                background: "rgba(0, 0, 0, 0.45)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                borderRadius: "var(--radius)",
                padding: "1rem",
                maxHeight: "300px",
                overflowY: "auto",
                fontFamily: "monospace",
                fontSize: "0.8125rem",
                lineHeight: 1.7,
              }}
            >
              {liveLines.length === 0 ? (
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--color-text-muted)" }}>
                  <span className="dot" style={{ animation: "pulse 1s infinite" }}>●</span>
                  <span>Audio engine initialized. Decoding first speech segment...</span>
                </div>
              ) : (
                liveLines.map((line, idx) => (
                  <div
                    key={idx}
                    className="animate-fade-in"
                    style={{
                      marginBottom: "0.35rem",
                      color: idx === liveLines.length - 1 ? "#38bdf8" : "var(--color-text)",
                      borderLeft: idx === liveLines.length - 1 ? "2px solid #38bdf8" : "2px solid transparent",
                      paddingLeft: "0.5rem",
                      wordBreak: "break-word",
                    }}
                  >
                    {line}
                  </div>
                ))
              )}
              <div ref={streamEndRef} />
            </div>

            <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginTop: "0.5rem", margin: 0 }}>
              💡 Spoken sentences appear line-by-line as recognized. Full structured extraction & calendar scheduling will follow.
            </p>
          </div>
        )}

        {meeting.error_message && (
          <div className="error-card" style={{ marginBottom: "1.5rem" }}>
            <strong>Error:</strong> {meeting.error_message}
          </div>
        )}

        {isProcessed && <InsightsPanel meeting={meeting} />}

        {/* Full Transcript Box */}
        {meeting.cleaned_transcript && (
          <div style={{ marginTop: "1.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <h3
                style={{
                  fontSize: "0.8125rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "var(--color-text-muted)",
                  margin: 0,
                }}
              >
                Transcript
                {meeting.speakers && meeting.speakers.length > 0 && (
                  <span
                    style={{
                      marginLeft: "0.75rem",
                      background: "rgba(168,85,247,0.15)",
                      color: "var(--color-purple, #a855f7)",
                      borderRadius: "999px",
                      padding: "0.15rem 0.6rem",
                      fontSize: "0.7rem",
                      fontWeight: 500,
                      textTransform: "none",
                      letterSpacing: 0,
                    }}
                  >
                    {meeting.speakers.length} participant{meeting.speakers.length > 1 ? "s" : ""}
                  </span>
                )}
              </h3>

              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(meeting.cleaned_transcript || "");
                  alert("Transcript copied to clipboard!");
                }}
                className="btn btn-secondary"
                style={{ fontSize: "0.75rem", padding: "0.25rem 0.65rem" }}
              >
                📋 Copy Transcript
              </button>
            </div>

            <div
              className="glass-card"
              style={{
                fontSize: "0.8125rem",
                lineHeight: 1.75,
                maxHeight: "480px",
                overflowY: "auto",
                padding: "1.25rem",
              }}
            >
              {meeting.cleaned_transcript.includes("[Speaker ") || meeting.cleaned_transcript.includes("[")
                ? meeting.cleaned_transcript.split("\n").map((line, i) => {
                    const speakerMatch = line.match(/^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*)?(?:\[?([A-Za-z0-9_\s\.\-]+?)\]?):\s*(.*)/);
                    if (speakerMatch) {
                      const time = speakerMatch[1];
                      const speaker = speakerMatch[2];
                      const text = speakerMatch[3];
                      return (
                        <div key={i} style={{ display: "flex", gap: "0.75rem", marginBottom: "0.6rem", alignItems: "flex-start" }}>
                          <span
                            style={{
                              flexShrink: 0,
                              background: "rgba(108, 99, 255, 0.15)",
                              color: "var(--color-accent)",
                              borderRadius: "6px",
                              padding: "0.15rem 0.55rem",
                              fontSize: "0.7rem",
                              fontWeight: 700,
                              marginTop: "0.2rem",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {time && <span style={{ opacity: 0.7, marginRight: "0.3rem" }}>{time}</span>}
                            {speaker}
                          </span>
                          <span style={{ color: "var(--color-text)", wordBreak: "break-word" }}>{text}</span>
                        </div>
                      );
                    }
                    return line.trim() ? (
                      <p key={i} style={{ marginBottom: "0.4rem", color: "var(--color-text)" }}>{line}</p>
                    ) : (
                      <br key={i} />
                    );
                  })
                : (
                  <pre style={{ fontFamily: "monospace", whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0 }}>
                    {meeting.cleaned_transcript}
                  </pre>
                )}
            </div>
          </div>
        )}

        {isProcessed && !meeting.cleaned_transcript && (
          <p style={{ color: "var(--color-text-muted)", marginTop: "1.5rem" }}>
            No transcript available.
          </p>
        )}
      </div>

      {isShareModalOpen && (
        <ShareModal
          meetingId={meeting.id}
          meetingTitle={meeting.title}
          onClose={() => setIsShareModalOpen(false)}
        />
      )}
    </>
  );
}
