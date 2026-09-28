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

const PIPELINE_STEPS: { key: MeetingStatus; label: string }[] = [
  { key: "uploaded", label: "Uploaded" },
  { key: "transcribing", label: "Transcribing" },
  { key: "cleaning", label: "Cleaning" },
  { key: "analyzing", label: "Analyzing" },
  { key: "processed", label: "Done" },
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
        gap: "1.5rem",
        padding: "1rem 1.25rem",
        marginBottom: "1.5rem",
        flexWrap: "wrap",
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
              opacity: state === "pending" ? 0.4 : 1,
            }}
          >
            <span
              style={{
                width: "26px",
                height: "26px",
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
                  state === "active" ? "0 0 12px rgba(245, 158, 11, 0.4)" : "none",
              }}
            >
              {state === "done" ? "\u2713" : state === "active" ? "\u21BB" : ""}
            </span>
            <span style={{ fontSize: "0.8125rem", fontWeight: state === "active" ? 600 : 400 }}>
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <>
      <Navbar />
      <div className="container">
        <div className="skeleton" style={{ height: "28px", width: "300px", marginBottom: "1rem" }} />
        <div className="skeleton" style={{ height: "16px", width: "200px", marginBottom: "2rem" }} />
        <div className="skeleton" style={{ height: "60px", width: "100%", marginBottom: "1.5rem" }} />
        <div className="skeleton" style={{ height: "200px", width: "100%" }} />
      </div>
    </>
  );
}

export function MeetingDetail() {
  const { id } = useParams<{ id: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const { selected: meeting, selectedStatus, selectedError } = useSelector(selectMeetingDetail);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isShareModalOpen, setIsShareModalOpen] = useState(false);

  useEffect(() => {
    if (!id) return;

    const poll = () => {
      dispatch(fetchMeeting(id) as any).unwrap().then((data: any) => {
        if (IN_PROGRESS_STATUSES.includes(data.status)) {
          timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        }
      }).catch(() => {});
    };

    poll();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      dispatch(clearSelectedMeeting());
    };
  }, [id, dispatch]);

  const isLoading = selectedStatus === "loading" || selectedStatus === "idle";
  const error = selectedStatus === "failed" ? selectedError : null;

  if (isLoading) return <LoadingSkeleton />;

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
            <div className="empty-state-icon">&#128269;</div>
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

  return (
    <>
      <Navbar />
      <div className="container">
        <Link to="/" className="back-link">
          &larr; Back to Dashboard
        </Link>

        <div style={{ marginBottom: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.75rem" }}>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>{meeting.title}</h1>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
              {isProcessed && (
                <div className="export-btn-group" style={{ display: "flex", gap: "0.375rem" }}>
                  <button onClick={() => api.exportMeeting(meeting.id, "pdf")} className="btn btn-secondary" style={{ fontSize: "0.75rem", padding: "0.375rem 0.75rem" }}>
                    &#8595; PDF
                  </button>
                  <button onClick={() => api.exportMeeting(meeting.id, "csv")} className="btn btn-secondary" style={{ fontSize: "0.75rem", padding: "0.375rem 0.75rem" }}>
                    &#8595; CSV
                  </button>
                  <button onClick={() => setIsShareModalOpen(true)} className="btn btn-secondary" style={{ fontSize: "0.75rem", padding: "0.375rem 0.75rem" }}>
                    &#128279; Share
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
                        : meeting.status === "analyzing"
                          ? "rgba(168,85,247,0.15)"
                          : "var(--color-surface-2)",
                  color:
                    meeting.status === "processed"
                      ? "var(--color-success)"
                      : meeting.status === "failed"
                        ? "var(--color-error)"
                        : meeting.status === "analyzing"
                          ? "var(--color-purple)"
                          : "var(--color-text-muted)",
                }}
              >
                {meeting.status}
              </span>
            </div>
          </div>
          <p style={{ marginTop: "0.5rem", color: "var(--color-text-muted)", fontSize: "0.8125rem" }}>
            Created {formatDate(meeting.created_at)}
            {meeting.updated_at !== meeting.created_at && (
              <> &middot; Updated {formatDate(meeting.updated_at)}</>
            )}
            {meeting.audio_duration_seconds && (
              <> &middot; Duration {formatDuration(meeting.audio_duration_seconds)}</>
            )}
          </p>
        </div>

        {isInProgress && <StatusStepper status={meeting.status} />}

        {meeting.error_message && (
          <div className="error-card" style={{ marginBottom: "1.5rem" }}>
            <strong>Error:</strong> {meeting.error_message}
          </div>
        )}

        {isProcessed && <InsightsPanel meeting={meeting} />}

        {meeting.cleaned_transcript && (
          <div style={{ marginTop: "1.5rem" }}>
            <h3
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                color: "var(--color-text-muted)",
                marginBottom: "0.75rem",
              }}
            >
              Cleaned Transcript
            </h3>
            <pre
              className="glass-card"
              style={{
                fontFamily: "monospace",
                fontSize: "0.8125rem",
                lineHeight: 1.65,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                maxHeight: "500px",
                overflowY: "auto",
              }}
            >
              {meeting.cleaned_transcript}
            </pre>
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
