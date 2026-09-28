import { useState, useRef, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useSelector, useDispatch } from "react-redux";
import type { AppDispatch } from "../store";
import { selectAuth, logout } from "../store/authSlice";

export function Navbar() {
  const { user } = useSelector(selectAuth);
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const location = useLocation();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = async () => {
    setDropdownOpen(false);
    await dispatch(logout());
    navigate("/login");
  };

  const initials = user?.display_name
    ? user.display_name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2)
    : "?";

  return (
    <nav
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.75rem 1.5rem",
        background: "rgba(10, 15, 30, 0.8)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--color-border)",
      }}
    >
      <Link
        to="/landing"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.625rem",
          textDecoration: "none",
          color: "var(--color-text)",
          fontWeight: 700,
          fontSize: "1.125rem",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: "32px",
            height: "32px",
            borderRadius: "8px",
            background: "linear-gradient(135deg, var(--color-accent), var(--color-purple))",
            fontSize: "1rem",
          }}
        >
          M
        </span>
        MeetingAI
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <Link
          to="/analytics"
          className="nav-link"
          style={{
            color: location.pathname === "/analytics" ? "var(--color-accent)" : "var(--color-text-muted)",
            fontSize: "0.875rem",
            fontWeight: 500,
            textDecoration: "none",
            transition: "color 0.2s",
          }}
        >
          Analytics
        </Link>
        <Link to="/upload" className="btn btn-primary" style={{ fontSize: "0.8125rem", padding: "0.5rem 1rem" }}>
          + New Upload
        </Link>

        {user && (
          <div ref={dropdownRef} style={{ position: "relative" }}>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.25rem",
                border: "none",
                borderRadius: "50%",
                background: "transparent",
                cursor: "pointer",
                transition: "background 0.2s",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "var(--color-surface-2)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
            >
              {user.picture_url ? (
                <img
                  src={user.picture_url}
                  alt={user.display_name}
                  style={{
                    width: "32px",
                    height: "32px",
                    borderRadius: "50%",
                    objectFit: "cover",
                  }}
                />
              ) : (
                <span style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "50%",
                  background: "linear-gradient(135deg, var(--color-accent), var(--color-purple))",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color: "white",
                }}>
                  {initials}
                </span>
              )}
            </button>

            {dropdownOpen && (
              <div style={{
                position: "absolute",
                top: "calc(100% + 8px)",
                right: 0,
                minWidth: "200px",
                background: "rgba(15, 23, 42, 0.95)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
                boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
                overflow: "hidden",
                animation: "slideDown 0.15s ease-out",
              }}>
                <div style={{
                  padding: "0.75rem 1rem",
                  borderBottom: "1px solid var(--color-border)",
                }}>
                  <p style={{ fontSize: "0.8125rem", fontWeight: 500, margin: 0 }}>
                    {user.display_name}
                  </p>
                  <p style={{
                    fontSize: "0.75rem",
                    color: "var(--color-text-muted)",
                    margin: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}>
                    {user.email}
                  </p>
                </div>
                <button
                  onClick={handleLogout}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: "0.625rem 1rem",
                    border: "none",
                    background: "transparent",
                    color: "var(--color-text)",
                    fontSize: "0.8125rem",
                    textAlign: "left",
                    cursor: "pointer",
                    transition: "background 0.15s",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "var(--color-surface-2)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      <style>{`
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </nav>
  );
}
