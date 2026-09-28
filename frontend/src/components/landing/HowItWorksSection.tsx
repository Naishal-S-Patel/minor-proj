import { useRef } from "react";
import { useIntersectionObserver } from "../../hooks/useIntersectionObserver";

const STEPS = [
  { num: "1", title: "Upload", desc: "Drag-and-drop a .txt transcript or .mp3/.mp4 audio file (up to 25MB, 2hrs)." },
  { num: "2", title: "Process", desc: "Local AI transcribes audio with Whisper, then Ollama extracts summary, action items, decisions, keywords, and sentiment." },
  { num: "3", title: "Insights", desc: "Your dashboard shows everything. Export as PDF/CSV. Share a link. Ask follow-up questions." },
];

export function HowItWorksSection() {
  const ref = useRef<HTMLDivElement>(null);
  const isVisible = useIntersectionObserver(ref);

  return (
    <section id="how-it-works" className="landing-section" ref={ref}>
      <div className="landing-section-header">
        <span className="eyebrow-chip">HOW IT WORKS</span>
        <h2 style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontWeight: 700, marginTop: "1rem" }}>
          Three steps to meeting clarity
        </h2>
      </div>

      <div className="hiw-steps">
        {STEPS.map((step, i) => (
          <div
            key={step.num}
            className={`hiw-step ${isVisible ? "visible" : ""}`}
            style={{ animationDelay: `${i * 0.2}s` }}
          >
            <div className="hiw-number">{step.num}</div>
            <h3 style={{ fontSize: "1rem", fontWeight: 600, marginTop: "1rem", marginBottom: "0.5rem" }}>{step.title}</h3>
            <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)", lineHeight: 1.6 }}>{step.desc}</p>
          </div>
        ))}
      </div>

      {/* Connector line */}
      <svg className={`hiw-connector-svg ${isVisible ? "drawn" : ""}`} viewBox="0 0 600 4" preserveAspectRatio="none">
        <line x1="0" y1="2" x2="600" y2="2" stroke="url(#lineGrad)" strokeWidth="2" strokeLinecap="round" />
        <defs>
          <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--color-accent)" />
            <stop offset="100%" stopColor="var(--color-purple)" />
          </linearGradient>
        </defs>
      </svg>
    </section>
  );
}
