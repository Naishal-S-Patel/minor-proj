import { useState } from "react";
import type { Meeting } from "../../api/client";
import { SummaryCard } from "./SummaryCard";
import { ActionItemsTable } from "./ActionItemsTable";
import { DecisionsList } from "./DecisionsList";
import { KeywordChips } from "./KeywordChips";
import { SentimentBadge } from "./SentimentBadge";
import { ChatPanel } from "./ChatPanel";
import { CalendarEventsSection } from "./CalendarEventsSection";
import { DialogueTimeline } from "./DialogueTimeline";

interface InsightsPanelProps {
  meeting: Meeting;
}

type TabKey = "summary" | "calendar" | "dialogue" | "actions" | "decisions" | "keywords" | "chat";

function actionsTabLabel(meeting: Meeting): string {
  const total = meeting.action_items.length;
  if (total === 0) return "Actions";
  const done = meeting.action_items.filter((item) => item.done).length;
  return `Actions (${done}/${total})`;
}

export function InsightsPanel({ meeting }: InsightsPanelProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("summary");

  const calendarCount = meeting.calendar_events?.length || 0;
  const dialogueCount = meeting.dialogue_turns?.length || 0;

  const tabs: { key: TabKey; label: string; count?: number; badgeColor?: string }[] = [
    { key: "summary", label: "Executive Summary" },
    {
      key: "calendar",
      label: "📅 Calendar & Deadlines",
      count: calendarCount,
      badgeColor: calendarCount > 0 ? "var(--color-warning)" : undefined,
    },
    {
      key: "dialogue",
      label: "💬 Who Spoke What",
      count: dialogueCount > 0 ? dialogueCount : undefined,
    },
    { key: "actions", label: actionsTabLabel(meeting) },
    { key: "decisions", label: `Decisions (${meeting.decisions.length})` },
    { key: "keywords", label: `Keywords (${meeting.keywords.length})` },
    { key: "chat", label: "🤖 Ask AI Assistant" },
  ];

  return (
    <div className="glass-card animate-fade-in" style={{ marginTop: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <h2 style={{ fontSize: "1.125rem", fontWeight: 700 }}>Meeting Insights & Intelligence</h2>
          {meeting.detected_language && meeting.detected_language !== "en" && (
            <span
              style={{
                fontSize: "0.7rem",
                fontWeight: 600,
                background: "rgba(168, 85, 247, 0.15)",
                color: "var(--color-purple)",
                padding: "0.15rem 0.5rem",
                borderRadius: "999px",
              }}
            >
              🌐 Language: {meeting.detected_language.toUpperCase()}
            </span>
          )}
        </div>
        <SentimentBadge sentiment={meeting.sentiment as "positive" | "neutral" | "negative" | null} />
      </div>

      <div className="tabs" style={{ marginTop: "1.25rem", overflowX: "auto", display: "flex" }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`tab ${activeTab === tab.key ? "active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
            style={{ whiteSpace: "nowrap" }}
          >
            {tab.label}
            {tab.badgeColor && (
              <span
                style={{
                  display: "inline-block",
                  width: "6px",
                  height: "6px",
                  borderRadius: "50%",
                  background: tab.badgeColor,
                  marginLeft: "0.35rem",
                  boxShadow: `0 0 8px ${tab.badgeColor}`,
                }}
              />
            )}
          </button>
        ))}
      </div>

      <div style={{ minHeight: "150px", marginTop: "1rem" }}>
        {activeTab === "summary" && <SummaryCard summary={meeting.summary} />}

        {activeTab === "calendar" && (
          <CalendarEventsSection
            events={meeting.calendar_events}
            meetingTitle={meeting.title}
            meetingId={meeting.id}
          />
        )}

        {activeTab === "dialogue" && (
          <DialogueTimeline
            meetingId={meeting.id}
            dialogues={meeting.dialogue_turns}
            speakers={meeting.speakers}
            speakerMap={meeting.speaker_map}
            rawTranscript={meeting.cleaned_transcript}
          />
        )}

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
