import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import type { User } from "../../types/user";

interface LandingNavbarProps {
  isAuthed: boolean;
  user: User | null;
}

export function LandingNavbar({ isAuthed }: LandingNavbarProps) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav className={`landing-nav ${scrolled ? "scrolled" : ""}`}>
      <div className="landing-nav-inner">
        <Link to="/landing" style={{ display: "flex", alignItems: "center", gap: "0.5rem", textDecoration: "none", color: "var(--color-text)", fontWeight: 700, fontSize: "1.0625rem" }}>
          <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "28px", height: "28px", borderRadius: "7px", background: "linear-gradient(135deg, var(--color-accent), var(--color-purple))", fontSize: "0.875rem" }}>M</span>
          MeetingAI
        </Link>

        <div className="landing-nav-links">
          <a href="#features" className="landing-nav-link">Features</a>
          <a href="#how-it-works" className="landing-nav-link">How it works</a>
          <a href="#demo" className="landing-nav-link">Demo</a>
        </div>

        <div>
          {isAuthed ? (
            <Link to="/" className="btn btn-primary" style={{ fontSize: "0.8125rem", padding: "0.5rem 1rem" }}>
              Go to app &rarr;
            </Link>
          ) : (
            <a href="/api/auth/google" className="btn btn-primary" style={{ fontSize: "0.8125rem", padding: "0.5rem 1rem" }}>
              Sign in
            </a>
          )}
        </div>
      </div>
    </nav>
  );
}
