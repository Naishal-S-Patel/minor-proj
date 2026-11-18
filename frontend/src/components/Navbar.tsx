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
    : "AI";

  return (
    <nav
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.75rem 2rem",
        background: "rgba(10, 15, 30, 0.85)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid var(--color-border)",
      }}
    >
      {/* Brand */}
      <Link
        to="/"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          textDecoration: "none",
          color: "var(--color-text)",
          fontWeight: 800,
          fontSize: "1.125rem",
          letterSpacing: "-0.01em",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: "34px",
            height: "34px",
            borderRadius: "10px",
            background: "linear-gradient(135deg, #6c63ff 0%, #a855f7 100%)",
            boxShadow: "0 4px 12px rgba(108, 99, 255, 0.35)",
            fontSize: "1.1rem",
            color: "white",
          }}
        >
          ⚡
        </span>
        <span>AI Meeting Intelligence</span>
      </Link>

      {/* Nav Links & Controls */}
      <div style={{ display: "flex", alignItems: "center", gap: "1.25rem" }}>
        {/* Status Pill */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.4rem",
            background: "rgba(34, 197, 94, 0.12)",
            border: "1px solid rgba(34, 197, 94, 0.25)",
            padding: "0.2rem 0.65rem",
            borderRadius: "999px",
            fontSize: "0.7rem",
            fontWeight: 600,
            color: "var(--color-success)",
          }}
        >
          <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
          <span>Engine Active</span>
        </div>

        <Link
          to="/"
          style={{
            color: location.pathname === "/" ? "var(--color-accent)" : "var(--color-text-muted)",
            fontSize: "0.875rem",
            fontWeight: 600,
            textDecoration: "none",
            transition: "color 0.15s",
          }}
        >
          Dashboard
        </Link>

        <Link
          to="/analytics"
          style={{
            color: location.pathname === "/analytics" ? "var(--color-accent)" : "var(--color-text-muted)",
            fontSize: "0.875rem",
            fontWeight: 600,
            textDecoration: "none",
            transition: "color 0.15s",
          }}
        >
          Analytics
        </Link>

        <Link
          to="/upload"
          className="btn btn-primary"
          style={{
            fontSize: "0.8125rem",
            padding: "0.45rem 1rem",
            fontWeight: 600,
            boxShadow: "0 2px 10px rgba(108, 99, 255, 0.3)",
          }}
        >
          + Upload Meeting
        </Link>

        {user && (
          <div ref={dropdownRef} style={{ position: "relative" }}>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.2rem",
                border: "none",
                borderRadius: "50%",
                background: "transparent",
                cursor: "pointer",
              }}
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
                <span
                  style={{
                    width: "32px",
                    height: "32px",
                    borderRadius: "50%",
                    background: "linear-gradient(135deg, var(--color-accent), var(--color-purple))",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    color: "white",
                  }}
                >
                  {initials}
                </span>
              )}
            </button>

            {dropdownOpen && (
              <div
                style={{
                  position: "absolute",
                  top: "calc(100% + 8px)",
                  right: 0,
                  minWidth: "220px",
                  background: "rgba(15, 23, 42, 0.98)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                  boxShadow: "0 10px 40px rgba(0,0,0,0.5)",
                  overflow: "hidden",
                }}
              >
                <div style={{ padding: "0.875rem 1rem", borderBottom: "1px solid var(--color-border)" }}>
                  <p style={{ fontSize: "0.8125rem", fontWeight: 700, margin: 0 }}>
                    {user.display_name}
                  </p>
                  <p
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--color-text-muted)",
                      margin: "0.15rem 0 0",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
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
                    color: "#f87171",
                    fontSize: "0.8125rem",
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  🚪 Sign out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </nav>
  );
}
