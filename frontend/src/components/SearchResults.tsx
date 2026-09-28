import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { selectSearch } from "../store/meetingsSlice";

const SENTIMENT_EMOJI: Record<string, string> = {
  positive: "\u{1F60A}",
  neutral: "\u{1F610}",
  negative: "\u{1F61F}",
};

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function SearchResults() {
  const navigate = useNavigate();
  const { searchResults, searchStatus, searchError } = useSelector(selectSearch);

  if (searchStatus === "loading") return null;

  if (searchError) {
    return <div className="error-card"><p>{searchError}</p></div>;
  }

  if (searchResults.length === 0) {
    return (
      <div className="empty-state" style={{ padding: "2rem" }}>
        <div className="empty-state-icon">&#128269;</div>
        <p>No meetings match your search.</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)" }}>
        {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} found
      </p>
      {searchResults.map((result, i) => (
        <div
          key={result.id}
          className="glass-card"
          onClick={() => navigate(`/meetings/${result.id}`)}
          style={{
            cursor: "pointer",
            transition: "transform 0.2s, box-shadow 0.2s",
            animation: `fadeIn 0.3s ease ${i * 0.05}s forwards`,
            opacity: 0,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(-2px)";
            e.currentTarget.style.boxShadow = "0 8px 24px rgba(0,0,0,0.3)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow = "none";
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.375rem" }}>
                <span style={{ fontWeight: 600, fontSize: "1rem" }}>{result.title}</span>
                {result.sentiment && <span style={{ fontSize: "0.875rem" }}>{SENTIMENT_EMOJI[result.sentiment] ?? ""}</span>}
              </div>
              {result.highlight && (
                <p
                  style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)", marginBottom: "0.375rem" }}
                  dangerouslySetInnerHTML={{ __html: result.highlight }}
                />
              )}
              <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>{formatDate(result.created_at)}</p>
            </div>
          </div>
        </div>
      ))}
      <style>{`@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}
