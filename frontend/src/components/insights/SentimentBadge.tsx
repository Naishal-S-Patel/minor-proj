import { useEffect, useState } from "react";

interface SentimentBadgeProps {
  sentiment: "positive" | "neutral" | "negative" | null;
}

const SENTIMENT_CONFIG = {
  positive: { emoji: "\u{1F60A}", label: "Positive", className: "positive" },
  neutral: { emoji: "\u{1F610}", label: "Neutral", className: "neutral" },
  negative: { emoji: "\u{1F61F}", label: "Negative", className: "negative" },
} as const;

export function SentimentBadge({ sentiment }: SentimentBadgeProps) {
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setAnimate(true), 100);
    return () => clearTimeout(t);
  }, []);

  if (!sentiment) return null;

  const config = SENTIMENT_CONFIG[sentiment];

  return (
    <span
      className={`sentiment-badge ${config.className} ${animate ? "animate-pulse" : ""}`}
    >
      <span style={{ fontSize: "1.125rem" }}>{config.emoji}</span>
      {config.label}
    </span>
  );
}
