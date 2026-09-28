import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

interface HeroSectionProps {
  isAuthed: boolean;
}

const HEADLINE_WORDS = ["Turn", "every", "meeting", "into", "actionable", "intelligence"];

export function HeroSection({ isAuthed }: HeroSectionProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Particle field
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    const particles: { x: number; y: number; vx: number; vy: number; r: number }[] = [];
    const COUNT = 70;
    const CONNECT_DIST = 120;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < COUNT; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: Math.random() * 1.5 + 0.5,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(108, 99, 255, 0.35)";
        ctx.fill();
      }
      // Connect nearby particles
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < CONNECT_DIST) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(108, 99, 255, ${0.15 * (1 - dist / CONNECT_DIST)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }
      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <section className="hero-section">
      <canvas ref={canvasRef} className="hero-canvas" />

      {/* Glow blobs */}
      <div className="hero-blob" style={{ top: "10%", left: "5%", width: "400px", height: "400px", background: "radial-gradient(circle, rgba(108,99,255,0.35), transparent 70%)", animation: "blob-float-1 14s ease-in-out infinite alternate" }} />
      <div className="hero-blob" style={{ top: "5%", right: "10%", width: "350px", height: "350px", background: "radial-gradient(circle, rgba(168,85,247,0.3), transparent 70%)", animation: "blob-float-2 16s ease-in-out infinite alternate" }} />
      <div className="hero-blob" style={{ bottom: "10%", left: "40%", width: "300px", height: "300px", background: "radial-gradient(circle, rgba(6,182,212,0.25), transparent 70%)", animation: "blob-float-3 12s ease-in-out infinite alternate" }} />

      <div className="landing-section hero-content">
        {/* Text */}
        <div className="hero-text">
          <span className="eyebrow-chip">&#10022; AI-powered meeting intelligence</span>

          <h1 style={{ fontSize: "clamp(2rem, 5vw, 3.25rem)", fontWeight: 800, lineHeight: 1.15, marginTop: "1.5rem" }}>
            {HEADLINE_WORDS.map((word, i) => (
              <span key={i} className="word-reveal visible" style={{ animationDelay: `${i * 0.08}s` }}>
                {word}{" "}
              </span>
            ))}
          </h1>

          <p className="hero-subtitle">
            Upload a transcript or audio. Get an instant summary, action items, decisions, and sentiment — powered by local AI.
          </p>

          <div className="hero-cta-row">
            {isAuthed ? (
              <Link to="/" className="btn btn-primary btn-hero-primary">Get started free &rarr;</Link>
            ) : (
              <a href="/api/auth/google" className="btn btn-primary btn-hero-primary">Get started free &rarr;</a>
            )}
            <a href="#how-it-works" className="btn btn-secondary">See how it works</a>
          </div>

          <div className="hero-badges">
            <span className="hero-badge">&#128274; No cloud required</span>
            <span className="hero-badge">&#9889; Local AI</span>
            <span className="hero-badge">&#127919; Instant insights</span>
          </div>
        </div>

        {/* 3D Card mockup */}
        <div className="hero-card-mock">
          <div className="hero-card-mock-inner">
            <div className="glass-card" style={{ padding: "1.25rem", width: "100%" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <div>
                  <p style={{ fontWeight: 600, fontSize: "0.9375rem" }}>Q4 Planning Meeting</p>
                  <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>Processed just now</p>
                </div>
                <span className="status-pill" style={{ background: "rgba(34,197,94,0.15)", color: "var(--color-success)", fontSize: "0.6875rem" }}>processed &#10003;</span>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
                {["Summary", "Actions", "Ask &#10024;"].map((t) => (
                  <span key={t} style={{ padding: "0.25rem 0.625rem", borderRadius: "9999px", fontSize: "0.6875rem", background: t === "Summary" ? "var(--color-accent)" : "var(--color-surface-2)", color: t === "Summary" ? "white" : "var(--color-text-muted)" }} dangerouslySetInnerHTML={{ __html: t }} />
                ))}
              </div>
              <div style={{ height: "6px", width: "90%", borderRadius: "3px", background: "var(--color-surface-2)", marginBottom: "0.5rem" }} />
              <div style={{ height: "6px", width: "75%", borderRadius: "3px", background: "var(--color-surface-2)", marginBottom: "0.5rem" }} />
              <div style={{ height: "6px", width: "60%", borderRadius: "3px", background: "var(--color-surface-2)" }} />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
