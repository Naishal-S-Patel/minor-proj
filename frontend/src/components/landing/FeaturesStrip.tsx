import { useRef } from "react";
import { useIntersectionObserver } from "../../hooks/useIntersectionObserver";

const FEATURES = [
  { icon: "\uD83C\uDF99\uFE0F", title: "Audio Transcription", desc: "Upload any MP3/MP4/WAV. Local Whisper converts speech to text in minutes." },
  { icon: "\uD83D\uDCCB", title: "Smart Summaries", desc: "Ollama extracts a concise 2-4 sentence summary of every meeting instantly." },
  { icon: "\u2705", title: "Action Items", desc: "Every task, owner, and deadline extracted and trackable with checkboxes." },
  { icon: "\uD83C\uDFAF", title: "Key Decisions", desc: "Decisions are separated from discussion — never lose context again." },
  { icon: "\uD83D\uDCAC", title: "Ask Your Meeting", desc: 'Chat with any meeting. Ask "Who owns the API work?" and get an exact answer.' },
  { icon: "\uD83D\uDCCA", title: "Analytics", desc: "Sentiment trends, keyword frequency, and pending tasks — across all meetings." },
];

export function FeaturesStrip() {
  const ref = useRef<HTMLDivElement>(null);
  const isVisible = useIntersectionObserver(ref);

  return (
    <section id="features" className="landing-section" ref={ref}>
      <div className="landing-section-header">
        <span className="eyebrow-chip">FEATURES</span>
        <h2 style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontWeight: 700, marginTop: "1rem" }}>
          Everything your meetings produce, organized automatically
        </h2>
        <p style={{ color: "var(--color-text-muted)", marginTop: "0.75rem", maxWidth: "520px", marginInline: "auto" }}>
          From raw audio to structured insights — no manual note-taking required.
        </p>
      </div>

      <div className="features-grid">
        {FEATURES.map((f, i) => (
          <div
            key={f.title}
            className={`feature-tile ${isVisible ? "visible" : ""}`}
            style={{ animationDelay: `${i * 0.08}s` }}
          >
            <div className="feature-icon-ring">{f.icon}</div>
            <div>
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, marginBottom: "0.375rem" }}>{f.title}</h3>
              <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)", lineHeight: 1.55 }}>{f.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
