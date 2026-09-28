import { useEffect, useState } from "react";

interface SummaryCardProps {
  summary: string | null;
}

export function SummaryCard({ summary }: SummaryCardProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(t);
  }, []);

  if (!summary) {
    return (
      <div className="glass-card" style={{ borderLeft: "3px solid var(--color-text-muted)" }}>
        <p style={{ color: "var(--color-text-muted)", fontStyle: "italic" }}>No summary available.</p>
      </div>
    );
  }

  return (
    <div
      className="glass-card animate-fade-in"
      style={{
        borderLeft: "3px solid var(--color-accent)",
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(8px)",
        transition: "opacity 0.4s ease, transform 0.4s ease",
      }}
    >
      <h3
        style={{
          fontSize: "0.75rem",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--color-text-muted)",
          marginBottom: "0.75rem",
        }}
      >
        Summary
      </h3>
      <p style={{ fontSize: "0.9375rem", lineHeight: 1.7, color: "var(--color-text)" }}>{summary}</p>
    </div>
  );
}
