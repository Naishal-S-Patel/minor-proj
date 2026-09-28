import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector, useDispatch } from "react-redux";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import type { AppDispatch } from "../store";
import { fetchAnalytics, selectAnalytics } from "../store/analyticsSlice";
import { Navbar } from "../components/Navbar";

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "#22c55e",
  neutral: "#818cf8",
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
  return `hsl(${hue}, 55%, 55%)`;
}

export function AnalyticsPage() {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { overview, status, error } = useSelector(selectAnalytics);

  useEffect(() => {
    dispatch(fetchAnalytics());
  }, [dispatch]);

  const isLoading = status === "loading" || status === "idle";

  return (
    <>
      <Navbar />
      <div className="container">
        <div style={{ marginBottom: "2rem" }}>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Analytics</h1>
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.875rem", marginTop: "0.25rem" }}>
            Across all your processed meetings
          </p>
        </div>

        {isLoading && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton" style={{ height: "200px", width: "100%" }} />
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
            {/* Summary stats */}
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
              <span className="stat-chip">
                {overview.total_meetings} meeting{overview.total_meetings !== 1 ? "s" : ""}
              </span>
              <span className="stat-chip">
                {overview.processed_meetings} processed
              </span>
              <span className="stat-chip">
                {overview.pending_tasks.length} pending task{overview.pending_tasks.length !== 1 ? "s" : ""}
              </span>
            </div>

            <div className="analytics-grid">
              {/* Panel 1 — Sentiment Breakdown */}
              <div className="glass-card analytics-panel">
                <h3 className="panel-title">Sentiment Breakdown</h3>
                {overview.processed_meetings === 0 ? (
                  <div className="empty-state" style={{ padding: "2rem" }}>
                    <p>No processed meetings yet</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
                    <ResponsiveContainer width={160} height={160}>
                      <PieChart>
                        <Pie
                          data={Object.entries(overview.sentiment_breakdown)
                            .filter(([, v]) => v > 0)
                            .map(([name, value]) => ({ name, value }))}
                          cx="50%"
                          cy="50%"
                          innerRadius={40}
                          outerRadius={65}
                          paddingAngle={3}
                          dataKey="value"
                        >
                          {Object.entries(overview.sentiment_breakdown)
                            .filter(([, v]) => v > 0)
                            .map(([name]) => (
                              <Cell key={name} fill={SENTIMENT_COLORS[name] || "#818cf8"} />
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
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                      {Object.entries(overview.sentiment_breakdown).map(([name, count]) => (
                        <div key={name} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem" }}>
                          <span
                            style={{
                              width: "10px",
                              height: "10px",
                              borderRadius: "50%",
                              background: SENTIMENT_COLORS[name],
                              flexShrink: 0,
                            }}
                          />
                          <span style={{ color: "var(--color-text-muted)", textTransform: "capitalize" }}>{name}</span>
                          <span style={{ fontWeight: 600 }}>{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Panel 2 — Top Keywords */}
              <div className="glass-card analytics-panel">
                <h3 className="panel-title">Top Keywords</h3>
                {overview.top_keywords.length === 0 ? (
                  <div className="empty-state" style={{ padding: "2rem" }}>
                    <p>No keywords extracted yet</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={Math.max(180, overview.top_keywords.length * 28 + 20)}>
                    <BarChart
                      data={overview.top_keywords}
                      layout="vertical"
                      margin={{ top: 0, right: 10, left: 10, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
                      <XAxis
                        type="number"
                        allowDecimals={false}
                        tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="keyword"
                        width={130}
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
                        }}
                        formatter={(value: any) => [`${value}x`, "Frequency"]}
                      />
                      <Bar
                        dataKey="count"
                        fill="var(--color-accent)"
                        radius={[0, 4, 4, 0]}
                        barSize={16}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>

              {/* Panel 3 — Pending Action Items */}
              <div className="glass-card analytics-panel" style={{ gridColumn: "span 1" }}>
                <h3 className="panel-title">Pending Action Items</h3>
                {overview.pending_tasks.length === 0 ? (
                  <div className="empty-state" style={{ padding: "2rem" }}>
                    <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>&#10003;</div>
                    <p>All caught up! No pending action items.</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxHeight: "300px", overflowY: "auto" }}>
                    {overview.pending_tasks.map((task) => (
                      <div
                        key={task.item_id}
                        className="pending-task-row"
                        onClick={() => navigate(`/meetings/${task.meeting_id}`)}
                        style={{ cursor: "pointer" }}
                      >
                        <div
                          className="person-avatar"
                          style={{ background: hashColor(task.person) }}
                        >
                          {getInitials(task.person)}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontSize: "0.8125rem", fontWeight: 500, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {task.task}
                          </p>
                          <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", margin: 0 }}>
                            {task.meeting_title}
                          </p>
                        </div>
                        {task.deadline && (
                          <span className="deadline-badge present">{task.deadline}</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Panel 4 — Meeting Volume Trend */}
              <div className="glass-card analytics-panel">
                <h3 className="panel-title">Meeting Volume Trend</h3>
                {overview.weekly_counts.length === 0 ? (
                  <div className="empty-state" style={{ padding: "2rem" }}>
                    <p>No meeting data yet</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={overview.weekly_counts} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="analyticsGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#a855f7" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#a855f7" stopOpacity={0.02} />
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
                        stroke="#a855f7"
                        strokeWidth={2}
                        fill="url(#analyticsGradient)"
                        dot={{ r: 3, fill: "#a855f7", strokeWidth: 0 }}
                        activeDot={{ r: 5, fill: "#a855f7" }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
