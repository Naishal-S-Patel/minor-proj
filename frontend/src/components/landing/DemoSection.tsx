import { useState, useEffect } from "react";

const TABS = [
  {
    label: "Summary",
    content: (
      <div style={{ padding: "1.5rem" }}>
        <p style={{ fontSize: "0.875rem", lineHeight: 1.7, marginBottom: "1rem" }}>
          The team discussed Q4 priorities and resource allocation. Key decisions included finalizing the mobile app launch timeline for mid-November and prioritizing the security audit. Action items were assigned across three teams with specific deadlines.
        </p>
        <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
          {["Q4 planning", "mobile app", "security audit", "resource allocation"].map((k) => (
            <span key={k} style={{ padding: "0.1875rem 0.5rem", borderRadius: "9999px", fontSize: "0.6875rem", background: "rgba(108,99,255,0.15)", color: "#818cf8" }}>{k}</span>
          ))}
        </div>
      </div>
    ),
  },
  {
    label: "Actions",
    content: (
      <div style={{ padding: "1rem 1.5rem" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
          <thead>
            <tr style={{ color: "var(--color-text-muted)", fontSize: "0.6875rem", textTransform: "uppercase" }}>
              <th style={{ textAlign: "left", padding: "0.5rem 0" }}>Person</th>
              <th style={{ textAlign: "left", padding: "0.5rem 0" }}>Task</th>
              <th style={{ textAlign: "left", padding: "0.5rem 0" }}>Deadline</th>
            </tr>
          </thead>
          <tbody>
            {[
              { person: "Sarah", task: "Finalize mobile app UI", deadline: "Nov 1", done: true },
              { person: "Mike", task: "Database schema review", deadline: "Thu", done: false },
              { person: "Alex", task: "Performance optimization plan", deadline: "Next Mon", done: false },
            ].map((item) => (
              <tr key={item.task} style={{ borderTop: "1px solid var(--color-border)" }}>
                <td style={{ padding: "0.625rem 0", fontWeight: 500 }}>{item.person}</td>
                <td style={{ padding: "0.625rem 0", textDecoration: item.done ? "line-through" : "none", color: item.done ? "var(--color-text-muted)" : "inherit" }}>
                  {item.done && <span style={{ marginRight: "0.375rem" }}>&#10003;</span>}
                  {item.task}
                </td>
                <td style={{ padding: "0.625rem 0", color: "var(--color-text-muted)" }}>{item.deadline}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
  },
  {
    label: "Ask AI",
    content: (
      <div style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <div style={{ alignSelf: "flex-end", maxWidth: "80%", padding: "0.625rem 1rem", borderRadius: "12px 12px 4px 12px", background: "var(--color-accent)", color: "white", fontSize: "0.8125rem" }}>
          Who owns the backend API work?
        </div>
        <div style={{ alignSelf: "flex-start", maxWidth: "80%", padding: "0.625rem 1rem", borderRadius: "12px 12px 12px 4px", background: "var(--color-surface)", border: "1px solid var(--color-border)", fontSize: "0.8125rem", lineHeight: 1.55 }}>
          According to the transcript, Sarah is responsible for the API redesign. The migration script is being worked on by her team and should be completed by end of next week.
        </div>
      </div>
    ),
  },
];

export function DemoSection() {
  const [activeTab, setActiveTab] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveTab((prev) => (prev + 1) % TABS.length);
    }, 3500);
    return () => clearInterval(timer);
  }, []);

  return (
    <section id="demo" className="landing-section">
      <div className="landing-section-header">
        <span className="eyebrow-chip">DEMO</span>
        <h2 style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", fontWeight: 700, marginTop: "1rem" }}>
          See it in action
        </h2>
        <p style={{ color: "var(--color-text-muted)", marginTop: "0.75rem" }}>
          From raw audio to structured insights in under 60 seconds.
        </p>
      </div>

      <div className="demo-browser">
        <div className="demo-browser-bar">
          <div style={{ display: "flex", gap: "6px" }}>
            <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#ef4444" }} />
            <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#f59e0b" }} />
            <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#22c55e" }} />
          </div>
          <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
            <span style={{ fontSize: "0.6875rem", color: "var(--color-text-muted)", background: "var(--color-surface-2)", padding: "0.25rem 0.75rem", borderRadius: "9999px" }}>
              &#128274; meetingai.app/meetings/q4-planning
            </span>
          </div>
          <div />
        </div>

        <div className="demo-tabs">
          {TABS.map((tab, i) => (
            <button
              key={tab.label}
              className={`demo-tab-btn ${activeTab === i ? "active" : ""}`}
              onClick={() => setActiveTab(i)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="demo-content">
          {TABS[activeTab].content}
        </div>
      </div>
    </section>
  );
}
