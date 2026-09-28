import { useSelector } from "react-redux";
import { selectAuth } from "../store/authSlice";

export function LoginPage() {
  const { status } = useSelector(selectAuth);

  const handleLogin = () => {
    window.location.href = "/api/auth/google";
  };

  return (
    <div style={{
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      minHeight: "100vh",
      background: "var(--color-bg)",
      padding: "1.5rem",
    }}>
      <div className="glass-card" style={{
        maxWidth: "400px",
        width: "100%",
        padding: "2.5rem 2rem",
        textAlign: "center",
      }}>
        <div style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: "56px",
          height: "56px",
          borderRadius: "16px",
          background: "linear-gradient(135deg, var(--color-accent), var(--color-purple))",
          fontSize: "1.5rem",
          fontWeight: 700,
          color: "white",
          marginBottom: "1.5rem",
        }}>
          M
        </div>

        <h1 style={{
          fontSize: "1.5rem",
          fontWeight: 700,
          marginBottom: "0.5rem",
        }}>
          MeetingAI
        </h1>
        <p style={{
          color: "var(--color-text-muted)",
          fontSize: "0.875rem",
          marginBottom: "2rem",
          lineHeight: 1.5,
        }}>
          Intelligent meeting summaries powered by AI.
        </p>

        <button
          onClick={handleLogin}
          disabled={status === "loading"}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.75rem",
            width: "100%",
            padding: "0.75rem 1.5rem",
            border: "none",
            borderRadius: "var(--radius)",
            background: "white",
            color: "#1f1f1f",
            fontSize: "0.9375rem",
            fontWeight: 500,
            cursor: status === "loading" ? "not-allowed" : "pointer",
            opacity: status === "loading" ? 0.7 : 1,
            transition: "opacity 0.2s, transform 0.1s",
            marginBottom: "1rem",
          }}
          onMouseEnter={(e) => { if (status !== "loading") e.currentTarget.style.opacity = "0.9"; }}
          onMouseLeave={(e) => { e.currentTarget.style.opacity = status === "loading" ? "0.7" : "1"; }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
            <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
            <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
            <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
          </svg>
          {status === "loading" ? "Signing in..." : "Sign in with Google"}
        </button>

        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          margin: "1rem 0",
          color: "var(--color-text-muted)",
          fontSize: "0.75rem",
        }}>
          <div style={{ flex: 1, height: "1px", background: "var(--color-border, #333)" }} />
          <span>OR</span>
          <div style={{ flex: 1, height: "1px", background: "var(--color-border, #333)" }} />
        </div>

        <button
          onClick={() => { window.location.href = "/api/auth/dev-login"; }}
          disabled={status === "loading"}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.5rem",
            width: "100%",
            padding: "0.75rem 1.5rem",
            border: "1px solid var(--color-border, rgba(255,255,255,0.15))",
            borderRadius: "var(--radius)",
            background: "rgba(255, 255, 255, 0.08)",
            color: "var(--color-text, #fff)",
            fontSize: "0.9375rem",
            fontWeight: 500,
            cursor: status === "loading" ? "not-allowed" : "pointer",
            transition: "all 0.2s ease",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255, 255, 255, 0.15)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(255, 255, 255, 0.08)"; }}
        >
          <span>⚡</span>
          <span>Continue as Guest / Demo User</span>
        </button>
      </div>
    </div>
  );
}
