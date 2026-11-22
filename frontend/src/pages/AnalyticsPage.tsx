import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector, useDispatch } from "react-redux";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import type { AppDispatch } from "../store";
import { fetchAnalytics, selectAnalytics } from "../store/analyticsSlice";
import { Navbar } from "../components/Navbar";

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "#10b981",
  neutral: "#6366f1",
  negative: "#ef4444",
};

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function hashColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 60%, 55%)`;
}

export function AnalyticsPage() {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { overview, status, error } = useSelector(selectAnalytics);

  useEffect(() => {
    dispatch(fetchAnalytics());
  }, [dispatch]);

  const isLoading = status === "loading" || status === "idle";

  const totalSentimentCount = overview
    ? Object.values(overview.sentiment_breakdown).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <>
      <Navbar />
      <div className="container" style={{ maxWidth: "1140px", paddingBottom: "4rem" }}>
        {/* Page Header */}
        <div style={{ marginBottom: "2rem" }}>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.02em", margin: 0 }}>
            Workspace Analytics & Intelligence
          </h1>
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.875rem", marginTop: "0.35rem" }}>
            Aggregated insights, sentiment analysis, task execution, and discussion trends across all meetings.
          </p>
        </div>

        {isLoading && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1rem" }}>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton" style={{ height: "180px", width: "100%", borderRadius: "var(--radius-lg)" }} />
            ))}
          </div>
        )}

        {!isLoading && error && (
          <div className="error-card">
            <p>{error}</p>
          </div>
        )}

        {!isLoading && !error && overview && (
          <>
            {/* KPI Metric Cards */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "1rem",
                marginBottom: "2rem",
              }}
            >
              <div className="glass-card" style={{ padding: "1.25rem" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", fontWeight: 600, textTransform: "uppercase" }}>
                  Total Meetings
                </span>
                <div style={{ fontSize: "1.875rem", fontWeight: 800, marginTop: "0.25rem", color: "var(--color-text)" }}>
                  {overview.total_meetings}
                </div>
                <span style={{ fontSize: "0.75rem", color: "var(--color-accent)", marginTop: "0.25rem", display: "block" }}>
                  Across all uploaded audio
                </span>
              </div>

              <div className="glass-card" style={{ padding: "1.25rem" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", fontWeight: 600, textTransform: "uppercase" }}>
                  AI Processed
                </span>
                <div style={{ fontSize: "1.875rem", fontWeight: 800, marginTop: "0.25rem", color: "#10b981" }}>
                  {overview.processed_meetings}
                </div>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginTop: "0.25rem", display: "block" }}>
                  {overview.total_meetings > 0 ? `${Math.round((overview.processed_meetings / overview.total_meetings) * 100)}% analyzed` : "0% analyzed"}
                </span>
              </div>

              <div className="glass-card" style={{ padding: "1.25rem" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", fontWeight: 600, textTransform: "uppercase" }}>
                  Pending Action Items
                </span>
                <div style={{ fontSize: "1.875rem", fontWeight: 800, marginTop: "0.25rem", color: "#f59e0b" }}>
                  {overview.pending_tasks.length}
                </div>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginTop: "0.25rem", display: "block" }}>
                  Awaiting team completion
                </span>
              </div>

              <div className="glass-card" style={{ padding: "1.25rem" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", fontWeight: 600, textTransform: "uppercase" }}>
                  Workspace Tone
                </span>
                <div style={{ fontSize: "1.875rem", fontWeight: 800, marginTop: "0.25rem", color: "#6366f1" }}>
                  {overview.sentiment_breakdown.positive > overview.sentiment_breakdown.negative ? "Productive" : "Balanced"}
                </div>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginTop: "0.25rem", display: "block" }}>
                  {overview.sentiment_breakdown.positive} positive sentiment
                </span>
              </div>
            </div>

            {/* Balanced 2-Column Analytics Grid */}
            <div className="analytics-grid">
              {/* Panel 1 — Sentiment Breakdown */}
              <div className="glass-card analytics-panel">
                <div className="panel-title">
                  <span>Sentiment Breakdown</span>
                  <span style={{ fontSize: "0.7rem", color: "var(--color-accent)", textTransform: "none", fontWeight: 500 }}>
                    {totalSentimentCount} meetings sampled
                  </span>
                </div>

                {overview.processed_meetings === 0 ? (
                  <div className="empty-state" style={{ padding: "2rem" }}>
                    <p>No processed meetings yet</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-around", flexWrap: "wrap", gap: "1rem" }}>
                      <div style={{ width: "140px", height: "140px", flexShrink: 0 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={Object.entries(overview.sentiment_breakdown)
                                .filter(([, v]) => v > 0)
                                .map(([name, value]) => ({ name, value }))}
                              cx="50%"
                              cy="50%"
                              innerRadius={36}
                              outerRadius={58}
                              paddingAngle={4}
                              dataKey="value"
                            >
                              {Object.entries(overview.sentiment_breakdown)
                                .filter(([, v]) => v > 0)
                                .map(([name]) => (
                                  <Cell key={name} fill={SENTIMENT_COLORS[name] || "#6366f1"} />
                                ))}
                            </Pie>
                            <Tooltip
                              contentStyle={{
                                background: "rgba(15, 23, 42, 0.95)",
                                border: "1px solid var(--color-border)",
                                borderRadius: "var(--radius)",
                                fontSize: "0.8125rem",
                              }}
                              formatter={(value: any, name: any) => [
                                `${value} meeting${value !== 1 ? "s" : ""}`,
                                String(name).charAt(0).toUpperCase() + String(name).slice(1),
                              ]}
                            />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>

                      <div style={{ flex: 1, minWidth: "160px", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                        {Object.entries(overview.sentiment_breakdown).map(([name, count]) => {
                          const pct = totalSentimentCount > 0 ? Math.round((count / totalSentimentCount) * 100) : 0;
                          const color = SENTIMENT_COLORS[name] || "#6366f1";
                          return (
                            <div key={name}>
                              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8125rem", marginBottom: "0.25rem" }}>
                                <span style={{ textTransform: "capitalize", fontWeight: 600, color: "var(--color-text)" }}>
                                  {name}
                                </span>
                                <span style={{ color: "var(--color-text-muted)" }}>
                                  {count} ({pct}%)
                                </span>
                              </div>
                              <div style={{ width: "100%", height: "6px", background: "rgba(255, 255, 255, 0.08)", borderRadius: "999px", overflow: "hidden" }}>
                                <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: "999px" }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Panel 2 — Top Keywords */}
              <div className="glass-card analytics-panel">
                <div className="panel-title">
                  <span>Top Discussion Keywords</span>
                  <span style={{ fontSize: "0.7rem", color: "var(--color-accent)", textTransform: "none", fontWeight: 500 }}>
                    {overview.top_keywords.length} topics
                  </span>
                </div>

                {overview.top_keywords.length === 0 ? (
                  <div className="empty-state" style={{ padding: "2rem" }}>
                    <p>No keywords extracted yet. Process a meeting to view topics.</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", maxHeight: "280px", overflowY: "auto" }}>
                    {overview.top_keywords.slice(0, 10).map((kw, idx) => {
                      const maxCount = overview.top_keywords[0]?.count || 1;
                      const barPct = Math.min(100, Math.round((kw.count / maxCount) * 100));
                      return (
                        <div
                          key={kw.keyword}
                          style={{
                            padding: "0.5rem 0.75rem",
                            background: "rgba(255, 255, 255, 0.02)",
                            borderRadius: "var(--radius)",
                            border: "1px solid rgba(255, 255, 255, 0.05)",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                            <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text)" }}>
                              #{kw.keyword}
                            </span>
                            <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-accent)" }}>
                              {kw.count}x
                            </span>
                          </div>
                          <div style={{ width: "100%", height: "4px", background: "rgba(255, 255, 255, 0.06)", borderRadius: "999px", overflow: "hidden" }}>
                            <div
                              style={{
                                width: `${barPct}%`,
                                height: "100%",
                                background: idx < 3 ? "linear-gradient(90deg, #6c63ff, #38bdf8)" : "#6c63ff",
                                borderRadius: "999px",
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Panel 3 — Pending Action Items */}
              <div className="glass-card analytics-panel">
                <div className="panel-title">
                  <span>Pending Action Items</span>
                  <span style={{ fontSize: "0.7rem", color: "#f59e0b", textTransform: "none", fontWeight: 600 }}>
                    {overview.pending_tasks.length} remaining
                  </span>
                </div>

                {overview.pending_tasks.length === 0 ? (
                  <div className="empty-state" style={{ padding: "2rem" }}>
                    <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>✓</div>
                    <p>All caught up! No pending action items.</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", maxHeight: "300px", overflowY: "auto" }}>
                    {overview.pending_tasks.map((task) => (
                      <div
                        key={task.item_id}
                        className="pending-task-row"
                        onClick={() => navigate(`/meetings/${task.meeting_id}`)}
                        style={{
                          cursor: "pointer",
                          padding: "0.6rem 0.75rem",
                          borderRadius: "var(--radius)",
                          border: "1px solid rgba(255, 255, 255, 0.04)",
                        }}
                      >
                        <div
                          className="person-avatar"
                          style={{
                            background: hashColor(task.person),
                            width: "30px",
                            height: "30px",
                            borderRadius: "50%",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            color: "#fff",
                            flexShrink: 0,
                          }}
                        >
                          {getInitials(task.person)}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontSize: "0.8125rem", fontWeight: 600, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {task.task}
                          </p>
                          <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", margin: 0 }}>
                            {task.meeting_title} &bull; <strong style={{ color: "var(--color-text)" }}>{task.person}</strong>
                          </p>
                        </div>
                        {task.deadline && (
                          <span
                            className="deadline-badge present"
                            style={{
                              fontSize: "0.7rem",
                              padding: "0.15rem 0.5rem",
                              borderRadius: "999px",
                              background: "rgba(245, 158, 11, 0.15)",
                              color: "#f59e0b",
                              fontWeight: 600,
                              flexShrink: 0,
                            }}
                          >
                            {task.deadline}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Panel 4 — Meeting Volume Trend */}
              <div className="glass-card analytics-panel">
                <div className="panel-title">
                  <span>Meeting Volume Trend</span>
                  <span style={{ fontSize: "0.7rem", color: "var(--color-purple)", textTransform: "none", fontWeight: 500 }}>
                    Weekly frequency
                  </span>
                </div>

                {overview.weekly_counts.length === 0 ? (
                  <div className="empty-state" style={{ padding: "2rem" }}>
                    <p>No meeting data yet</p>
                  </div>
                ) : (
                  <div style={{ width: "100%", height: "240px" }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={overview.weekly_counts} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="analyticsGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#818cf8" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="#818cf8" stopOpacity={0.0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                        <XAxis
                          dataKey="week"
                          tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
                          axisLine={false}
                          tickLine={false}
                        />
                        <YAxis
                          allowDecimals={false}
                          tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
                          axisLine={false}
                          tickLine={false}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "rgba(15, 23, 42, 0.95)",
                            border: "1px solid var(--color-border)",
                            borderRadius: "var(--radius)",
                            fontSize: "0.8125rem",
                            color: "var(--color-text)",
                          }}
                          labelStyle={{ color: "var(--color-text-muted)" }}
                        />
                        <Area
                          type="monotone"
                          dataKey="count"
                          stroke="#818cf8"
                          strokeWidth={2.5}
                          fill="url(#analyticsGradient)"
                          dot={{ r: 4, fill: "#818cf8", strokeWidth: 0 }}
                          activeDot={{ r: 6, fill: "#818cf8" }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
