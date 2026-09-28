interface DecisionsListProps {
  decisions: string[];
}

export function DecisionsList({ decisions }: DecisionsListProps) {
  if (decisions.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">&#128269;</div>
        <p>No decisions were identified in this meeting.</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {decisions.map((decision, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "0.75rem",
            padding: "0.875rem 1rem",
            background: "var(--color-surface)",
            borderRadius: "var(--radius)",
            borderLeft: "3px solid var(--color-accent)",
          }}
        >
          <span className="index-badge">{i + 1}</span>
          <p style={{ fontSize: "0.9375rem", lineHeight: 1.6, paddingTop: "0.125rem" }}>{decision}</p>
        </div>
      ))}
    </div>
  );
}
