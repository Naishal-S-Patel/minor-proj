import { useSelector } from "react-redux";
import { selectAuth } from "../store/authSlice";
import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";

function FullPageSpinner() {
  return (
    <div style={{
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      height: "100vh",
      background: "var(--color-bg)",
    }}>
      <div style={{
        width: "40px",
        height: "40px",
        border: "3px solid var(--color-surface-2)",
        borderTopColor: "var(--color-accent)",
        borderRadius: "50%",
        animation: "spin 0.8s linear infinite",
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useSelector(selectAuth);

  if (status === "loading" || status === "idle") return <FullPageSpinner />;
  if (status === "unauthenticated") return <Navigate to="/login" replace />;
  return <>{children}</>;
}
