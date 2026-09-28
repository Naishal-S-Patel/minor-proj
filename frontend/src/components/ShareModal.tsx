import { useState, useEffect, useCallback } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { AppDispatch } from "../store";
import { selectShareUrl, shareMeeting, unshareMeeting } from "../store/meetingsSlice";
import type { RootState } from "../store";

interface ShareModalProps {
  meetingId: string;
  meetingTitle: string;
  onClose: () => void;
}

export function ShareModal({ meetingId, meetingTitle, onClose }: ShareModalProps) {
  const dispatch = useDispatch<AppDispatch>();
  const shareUrl = useSelector((state: RootState) => selectShareUrl(state, meetingId));
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    await dispatch(shareMeeting(meetingId));
    setLoading(false);
  }, [dispatch, meetingId]);

  const handleRevoke = useCallback(async () => {
    setLoading(true);
    await dispatch(unshareMeeting(meetingId));
    setLoading(false);
  }, [dispatch, meetingId]);

  const handleCopy = useCallback(async () => {
    if (shareUrl) {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [shareUrl]);

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.6)",
        backdropFilter: "blur(8px)",
      }}
    >
      <div
        className="glass-card modal"
        style={{
          maxWidth: "440px",
          width: "90%",
          padding: "2rem",
          animation: "scaleIn 0.2s ease",
        }}
      >
        <h2 style={{ fontSize: "1.125rem", fontWeight: 600, marginBottom: "0.5rem" }}>Share Meeting</h2>
        <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)", marginBottom: "1.5rem" }}>
          {meetingTitle}
        </p>

        {!shareUrl ? (
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="btn btn-primary"
            style={{ width: "100%" }}
          >
            {loading ? "Generating..." : "Generate share link"}
          </button>
        ) : (
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)", display: "block", marginBottom: "0.5rem" }}>
              Share URL
            </label>
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
              <input
                readOnly
                value={shareUrl}
                className="input"
                style={{ flex: 1, fontSize: "0.8125rem", fontFamily: "monospace" }}
              />
              <button onClick={handleCopy} className="btn btn-secondary" style={{ fontSize: "0.8125rem", padding: "0.5rem 1rem", flexShrink: 0 }}>
                {copied ? "\u2713 Copied" : "Copy"}
              </button>
            </div>
            <button
              onClick={handleRevoke}
              disabled={loading}
              className="btn btn-secondary"
              style={{ width: "100%", fontSize: "0.8125rem", color: "var(--color-error)" }}
            >
              {loading ? "Revoking..." : "Revoke link"}
            </button>
          </div>
        )}

        <button
          onClick={onClose}
          className="btn btn-secondary"
          style={{ width: "100%", marginTop: "1rem", fontSize: "0.8125rem" }}
        >
          Close
        </button>
      </div>
      <style>{`@keyframes scaleIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }`}</style>
    </div>
  );
}
