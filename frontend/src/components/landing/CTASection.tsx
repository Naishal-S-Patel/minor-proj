import { Link } from "react-router-dom";

interface CTASectionProps {
  isAuthed: boolean;
}

export function CTASection({ isAuthed }: CTASectionProps) {
  return (
    <section className="cta-section landing-section">
      <h2 style={{ fontSize: "clamp(1.5rem, 3.5vw, 2.25rem)", fontWeight: 700, maxWidth: "600px", marginInline: "auto" }}>
        Stop losing meeting insights. Start in 60 seconds.
      </h2>
      <p style={{ color: "var(--color-text-muted)", marginTop: "1rem", maxWidth: "480px", marginInline: "auto" }}>
        No credit card. No cloud upload. Everything runs on your machine.
      </p>

      <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginTop: "2rem", flexWrap: "wrap" }}>
        {isAuthed ? (
          <Link to="/" className="btn btn-primary btn-hero-primary" style={{ fontSize: "1rem", padding: "0.75rem 2rem" }}>
            Go to Dashboard &rarr;
          </Link>
        ) : (
          <a href="/api/auth/google" className="btn btn-primary btn-hero-primary" style={{ fontSize: "1rem", padding: "0.75rem 2rem" }}>
            Get started free &rarr;
          </a>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "center", gap: "1.5rem", marginTop: "1.5rem", flexWrap: "wrap" }}>
        <span className="hero-badge">&#128274; No cloud required</span>
        <span className="hero-badge">&#9889; Local AI</span>
        <span className="hero-badge">&#127919; Instant insights</span>
      </div>

      <hr style={{ border: "none", borderTop: "1px solid var(--color-border)", margin: "4rem 0 2rem" }} />

      <footer className="landing-footer">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "24px", height: "24px", borderRadius: "6px", background: "linear-gradient(135deg, var(--color-accent), var(--color-purple))", fontSize: "0.75rem", color: "white", fontWeight: 700 }}>M</span>
            <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>MeetingAI</span>
            <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginLeft: "0.25rem" }}>Turn meetings into action.</span>
          </div>

          <div style={{ display: "flex", gap: "1.5rem", fontSize: "0.8125rem" }}>
            <a href="#features" style={{ color: "var(--color-text-muted)" }}>Features</a>
            <a href="#how-it-works" style={{ color: "var(--color-text-muted)" }}>How it works</a>
            <a href="#demo" style={{ color: "var(--color-text-muted)" }}>Demo</a>
          </div>

          <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
            Built with &#10084;&#65039; using FastAPI + React + local AI
          </p>
        </div>

        <div className="footer-bottom">
          &copy; 2025 MeetingAI &middot; No data leaves your machine
        </div>
      </footer>
    </section>
  );
}
