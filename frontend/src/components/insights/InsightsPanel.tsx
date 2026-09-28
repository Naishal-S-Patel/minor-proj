import { useState } from "react";
import type { Meeting } from "../../api/client";
import { SummaryCard } from "./SummaryCard";
import { ActionItemsTable } from "./ActionItemsTable";
import { DecisionsList } from "./DecisionsList";
import { KeywordChips } from "./KeywordChips";
import { SentimentBadge } from "./SentimentBadge";
import { ChatPanel } from "./ChatPanel";

interface InsightsPanelProps {
  meeting: Meeting;
}

type TabKey = "summary" | "actions" | "decisions" | "keywords" | "chat";

function actionsTabLabel(meeting: Meeting): string {
  const total = meeting.action_items.length;
  if (total === 0) return "Actions";
  const done = meeting.action_items.filter((item) => item.done).length;
  // "X/Y" only once at least one item exists -- keeps the empty-state tab
  // label plain ("Actions", handled by isEmpty below) rather than showing
  // a confusing "0/0".
  return `Actions (${done}/${total})`;
}

const TABS: { key: TabKey; label: (m: Meeting) => string; isEmpty: (m: Meeting) => boolean }[] = [
  { key: "summary", label: () => "Summary", isEmpty: (m) => !m.summary },
  { key: "actions", label: actionsTabLabel, isEmpty: (m) => m.action_items.length === 0 },
  { key: "decisions", label: () => "Decisions", isEmpty: (m) => m.decisions.length === 0 },
  { key: "keywords", label: () => "Keywords", isEmpty: (m) => m.keywords.length === 0 },
  { key: "chat", label: () => "Ask", isEmpty: () => false },
];

export function InsightsPanel({ meeting }: InsightsPanelProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("summary");

  return (
    <div className="glass-card animate-fade-in" style={{ marginTop: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
        <h2 style={{ fontSize: "1.125rem", fontWeight: 600 }}>Insights</h2>
        <SentimentBadge sentiment={meeting.sentiment as "positive" | "neutral" | "negative" | null} />
      </div>

      <div className="tabs" style={{ marginTop: "1rem" }}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`tab ${activeTab === tab.key ? "active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label(meeting)}
            {!tab.isEmpty(meeting) && tab.key !== "actions" && tab.key !== "chat" && <span className="tab-indicator" />}
          </button>
        ))}
      </div>

      <div style={{ minHeight: "120px" }}>
        {activeTab === "summary" && <SummaryCard summary={meeting.summary} />}
        {activeTab === "actions" && (
          <ActionItemsTable meetingId={meeting.id} actionItems={meeting.action_items} />
        )}
        {activeTab === "decisions" && <DecisionsList decisions={meeting.decisions} />}
        {activeTab === "keywords" && <KeywordChips keywords={meeting.keywords} />}
        {activeTab === "chat" && <ChatPanel meetingId={meeting.id} />}
      </div>
    </div>
  );
}
