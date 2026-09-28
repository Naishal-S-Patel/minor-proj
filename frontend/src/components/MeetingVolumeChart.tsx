import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface ChartData {
  week: string;
  count: number;
}

function getWeekLabel(date: Date): string {
  const start = new Date(date);
  start.setDate(start.getDate() - start.getDay());
  return start.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function buildWeeklyData(meetings: { created_at: string }[]): ChartData[] {
  const now = new Date();
  const weeks: ChartData[] = [];

  for (let i = 7; i >= 0; i--) {
    const weekStart = new Date(now);
    weekStart.setDate(weekStart.getDate() - weekStart.getDay() - i * 7);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 7);

    const count = meetings.filter((m) => {
      const d = new Date(m.created_at);
      return d >= weekStart && d < weekEnd;
    }).length;

    weeks.push({ week: getWeekLabel(weekStart), count });
  }

  return weeks;
}

interface MeetingVolumeChartProps {
  meetings: { created_at: string }[];
}

export function MeetingVolumeChart({ meetings }: MeetingVolumeChartProps) {
  const [visible, setVisible] = useState(false);
  const data = buildWeeklyData(meetings);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      className="glass-card"
      style={{
        marginBottom: "1.5rem",
        padding: "1.25rem",
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(8px)",
        transition: "opacity 0.5s ease, transform 0.5s ease",
      }}
    >
      <h3
        style={{
          fontSize: "0.75rem",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--color-text-muted)",
          marginBottom: "1rem",
        }}
      >
        Meetings per Week
      </h3>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="gradient" x1="0" y1="0" x2="0" y2="1">
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
            fill="url(#gradient)"
            dot={{ r: 3, fill: "#a855f7", strokeWidth: 0 }}
            activeDot={{ r: 5, fill: "#a855f7" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
