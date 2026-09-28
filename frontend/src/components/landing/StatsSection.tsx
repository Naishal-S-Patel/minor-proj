import { useRef, useEffect, useState } from "react";
import { useIntersectionObserver } from "../../hooks/useIntersectionObserver";

const STATS = [
  { end: 10000, suffix: "+", label: "Meetings Processed" },
  { end: 60, suffix: "s", label: "Average Processing Time", prefix: "< " },
  { end: 100, suffix: "%", label: "Local & Private" },
  { end: 5, suffix: "\u00d7", label: "Faster Follow-ups" },
];

function AnimatedCounter({ end, suffix, prefix }: { end: number; suffix: string; prefix?: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const isVisible = useIntersectionObserver(ref, { threshold: 0.5 });

  useEffect(() => {
    if (!isVisible) return;
    const duration = 1500;
    const startTime = performance.now();

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(eased * end));
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [isVisible, end]);

  return (
    <span ref={ref}>
      {prefix || ""}{count.toLocaleString()}{suffix}
    </span>
  );
}

export function StatsSection() {
  return (
    <section className="stats-strip">
      <div className="landing-section" style={{ padding: "4rem 2rem" }}>
        <div className="stats-grid">
          {STATS.map((stat) => (
            <div key={stat.label} style={{ textAlign: "center" }}>
              <div className="stat-number">
                <AnimatedCounter end={stat.end} suffix={stat.suffix} prefix={stat.prefix} />
              </div>
              <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)", marginTop: "0.375rem" }}>{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
