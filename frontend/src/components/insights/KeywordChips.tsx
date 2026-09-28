interface KeywordChipsProps {
  keywords: string[];
}

function keywordToHue(keyword: string): number {
  let hash = 0;
  for (let i = 0; i < keyword.length; i++) {
    hash = keyword.charCodeAt(i) + ((hash << 5) - hash);
  }
  return Math.abs(hash) % 360;
}

export function KeywordChips({ keywords }: KeywordChipsProps) {
  if (keywords.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">#</div>
        <p>No keywords extracted from this meeting.</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
      {keywords.map((kw, i) => {
        const hue = keywordToHue(kw);
        return (
          <span
            key={i}
            className="chip"
            style={{
              background: `hsla(${hue}, 70%, 50%, 0.15)`,
              color: `hsl(${hue}, 80%, 70%)`,
              border: `1px solid hsla(${hue}, 70%, 50%, 0.3)`,
            }}
          >
            {kw}
          </span>
        );
      })}
    </div>
  );
}
