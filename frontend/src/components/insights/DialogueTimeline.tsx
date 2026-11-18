import { useState, useMemo, useEffect } from "react";
import { useDispatch } from "react-redux";
import type { AppDispatch } from "../../store";
import { updateSpeakerMap } from "../../store/meetingsSlice";
import type { DialogueTurn } from "../../api/client";

interface DialogueTimelineProps {
  meetingId?: string;
  dialogues: DialogueTurn[] | undefined;
  speakers: string[];
  speakerMap?: Record<string, string>;
  rawTranscript?: string | null;
}

const SPEAKER_COLORS = [
  { bg: "rgba(99, 102, 241, 0.15)", border: "rgba(99, 102, 241, 0.35)", color: "#818cf8" },
  { bg: "rgba(16, 185, 129, 0.15)", border: "rgba(16, 185, 129, 0.35)", color: "#34d399" },
  { bg: "rgba(245, 158, 11, 0.15)", border: "rgba(245, 158, 11, 0.35)", color: "#fbbf24" },
  { bg: "rgba(239, 68, 68, 0.15)",  border: "rgba(239, 68, 68, 0.35)",  color: "#f87171" },
  { bg: "rgba(168, 85, 247, 0.15)", border: "rgba(168, 85, 247, 0.35)", color: "#c084fc" },
  { bg: "rgba(14, 165, 233, 0.15)", border: "rgba(14, 165, 233, 0.35)", color: "#38bdf8" },
];

export function DialogueTimeline({ meetingId, dialogues, speakers, speakerMap = {}, rawTranscript }: DialogueTimelineProps) {
  const dispatch = useDispatch<AppDispatch>();
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [isEditingMap, setIsEditingMap] = useState(false);
  const [draftMap, setDraftMap] = useState<Record<string, string>>({});
  const [isSavingMap, setIsSavingMap] = useState(false);

  // Parse turns from dialogues or fallback from transcript
  const parsedTurns: DialogueTurn[] = useMemo(() => {
    if (dialogues && dialogues.length > 0) {
      return dialogues;
    }
    if (!rawTranscript) return [];

    const lines = rawTranscript.split("\n").filter((l) => l.trim().length > 0);
    const result: DialogueTurn[] = [];

    const regex = /^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*)?(?:\[?([A-Za-z0-9_\s\.\-]+?)\]?):\s*(.+)$/;
    for (const line of lines) {
      const match = line.match(regex);
      if (match) {
        const rawSpk = match[2].trim();
        result.push({
          time: match[1] || null,
          speaker: speakerMap[rawSpk] || rawSpk,
          speaker_id: rawSpk in speakerMap ? rawSpk : null,
          text: match[3].trim(),
        });
      } else {
        result.push({
          speaker: speakers[0] || "Speaker 1",
          time: null,
          text: line,
        });
      }
    }
    return result;
  }, [dialogues, rawTranscript, speakers, speakerMap]);

  // Build effective ID -> Speaker map (combining backend speakerMap + unique speaker_ids/speakers)
  const effectiveEntries = useMemo(() => {
    const entries: Record<string, string> = { ...speakerMap };
    for (const turn of parsedTurns) {
      const id = turn.speaker_id || turn.speaker;
      if (id && !(id in entries)) {
        entries[id] = turn.speaker;
      }
    }
    for (const s of speakers) {
      const alreadyMapped = Object.values(entries).includes(s) || s in entries;
      if (!alreadyMapped) {
        entries[s] = s;
      }
    }
    return entries;
  }, [speakerMap, parsedTurns, speakers]);

  // Reverse lookup: Speaker Name -> Person ID (if mapped)
  const nameToIdMap = useMemo(() => {
    const rev: Record<string, string> = {};
    for (const [pid, name] of Object.entries(effectiveEntries)) {
      if (pid !== name && !rev[name]) {
        rev[name] = pid;
      }
    }
    return rev;
  }, [effectiveEntries]);

  useEffect(() => {
    setDraftMap(effectiveEntries);
  }, [effectiveEntries]);

  const handleSaveMapping = async () => {
    if (!meetingId) return;
    setIsSavingMap(true);
    try {
      await dispatch(updateSpeakerMap({ meetingId, speakerMap: draftMap })).unwrap();
      setIsEditingMap(false);
    } catch {
      // handled gracefully
    } finally {
      setIsSavingMap(false);
    }
  };

  // Color map per speaker
  const speakerColorMap = useMemo(() => {
    const map = new Map<string, typeof SPEAKER_COLORS[0]>();
    speakers.forEach((s, idx) => {
      map.set(s, SPEAKER_COLORS[idx % SPEAKER_COLORS.length]);
    });
    return map;
  }, [speakers]);

  // Filtered turns
  const filteredTurns = useMemo(() => {
    return parsedTurns.filter((turn) => {
      const matchesSpeaker = selectedSpeaker === "all" || turn.speaker.toLowerCase() === selectedSpeaker.toLowerCase();
      const matchesSearch =
        !searchQuery.trim() ||
        turn.text.toLowerCase().includes(searchQuery.toLowerCase()) ||
        turn.speaker.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (turn.speaker_id && turn.speaker_id.toLowerCase().includes(searchQuery.toLowerCase()));
      return matchesSpeaker && matchesSearch;
    });
  }, [parsedTurns, selectedSpeaker, searchQuery]);

  if (parsedTurns.length === 0) {
    return (
      <div className="empty-state" style={{ padding: "2.5rem 1rem" }}>
        <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>💬</div>
        <p style={{ fontWeight: 600, color: "var(--color-text)" }}>No Dialogue Turns Detected</p>
        <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)" }}>
          The transcript does not contain partitioned speaker dialogue lines.
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Person ID -> Speaker Mapping Panel */}
      {Object.keys(effectiveEntries).length > 0 && (
        <div
          style={{
            marginBottom: "1rem",
            padding: "0.85rem 1rem",
            borderRadius: "var(--radius)",
            background: "rgba(99, 102, 241, 0.06)",
            border: "1px solid rgba(99, 102, 241, 0.25)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.6rem" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-accent)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              🪪 Person ID → Speaker Mapping
            </span>
            {meetingId && (
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: "0.72rem", padding: "0.25rem 0.65rem" }}
                onClick={() => {
                  setDraftMap(effectiveEntries);
                  setIsEditingMap(!isEditingMap);
                }}
              >
                {isEditingMap ? "Cancel" : "✏️ Map IDs to Names"}
              </button>
            )}
          </div>

          {!isEditingMap ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              {Object.entries(effectiveEntries).map(([pid, name]) => (
                <div
                  key={pid}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    padding: "0.25rem 0.6rem",
                    borderRadius: "6px",
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    fontSize: "0.75rem",
                  }}
                >
                  <code style={{ color: "var(--color-text-muted)", fontWeight: 600 }}>{pid}</code>
                  <span style={{ color: "var(--color-accent)" }}>➔</span>
                  <strong style={{ color: "var(--color-text)" }}>{name}</strong>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "0.5rem" }}>
                {Object.entries(draftMap).map(([pid, name]) => (
                  <div key={pid} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <code
                      style={{
                        minWidth: "84px",
                        fontSize: "0.75rem",
                        padding: "0.35rem 0.5rem",
                        borderRadius: "6px",
                        background: "rgba(0,0,0,0.25)",
                        color: "var(--color-text-muted)",
                        border: "1px solid var(--color-border)",
                      }}
                    >
                      {pid}
                    </code>
                    <span style={{ color: "var(--color-accent)", fontSize: "0.8rem" }}>➔</span>
                    <input
                      type="text"
                      className="input"
                      value={name}
                      onChange={(e) => setDraftMap({ ...draftMap, [pid]: e.target.value })}
                      placeholder="Speaker Name"
                      style={{ fontSize: "0.78rem", padding: "0.35rem 0.55rem" }}
                    />
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.25rem" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ fontSize: "0.75rem", padding: "0.35rem 0.85rem" }}
                  onClick={handleSaveMapping}
                  disabled={isSavingMap}
                >
                  {isSavingMap ? "Saving..." : "💾 Save Mapping"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Header controls: Speaker pills & search */}
      <div style={{ marginBottom: "1.25rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase" }}>
              Filter by Speaker:
            </span>
            <button
              type="button"
              onClick={() => setSelectedSpeaker("all")}
              style={{
                background: selectedSpeaker === "all" ? "var(--color-accent)" : "var(--color-surface)",
                color: selectedSpeaker === "all" ? "white" : "var(--color-text-muted)",
                border: "1px solid var(--color-border)",
                borderRadius: "999px",
                padding: "0.25rem 0.65rem",
                fontSize: "0.75rem",
                cursor: "pointer",
                fontWeight: selectedSpeaker === "all" ? 700 : 500,
              }}
            >
              All Speakers ({parsedTurns.length})
            </button>
            {speakers.map((s, idx) => {
              const c = speakerColorMap.get(s) || SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
              const isSelected = selectedSpeaker.toLowerCase() === s.toLowerCase();
              const pid = nameToIdMap[s];
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSelectedSpeaker(s)}
                  style={{
                    background: isSelected ? c.bg : "var(--color-surface)",
                    color: isSelected ? c.color : "var(--color-text-muted)",
                    border: `1px solid ${isSelected ? c.border : "var(--color-border)"}`,
                    borderRadius: "999px",
                    padding: "0.25rem 0.65rem",
                    fontSize: "0.75rem",
                    cursor: "pointer",
                    fontWeight: isSelected ? 700 : 500,
                  }}
                >
                  👤 {s}{pid ? ` (${pid})` : ""}
                </button>
              );
            })}
          </div>

          <div style={{ width: "200px" }}>
            <input
              type="text"
              className="input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search dialogues..."
              style={{ fontSize: "0.75rem", padding: "0.35rem 0.65rem" }}
            />
          </div>
        </div>
      </div>

      {/* Dialogue List */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.625rem",
          maxHeight: "460px",
          overflowY: "auto",
          paddingRight: "0.25rem",
        }}
      >
        {filteredTurns.map((turn, i) => {
          const c = speakerColorMap.get(turn.speaker) || SPEAKER_COLORS[i % SPEAKER_COLORS.length];
          const displayId = turn.speaker_id || nameToIdMap[turn.speaker];

          return (
            <div
              key={i}
              style={{
                display: "flex",
                gap: "0.875rem",
                alignItems: "flex-start",
                padding: "0.75rem 1rem",
                borderRadius: "var(--radius)",
                background: "rgba(255, 255, 255, 0.02)",
                border: "1px solid var(--color-border)",
                transition: "background 0.15s ease",
              }}
            >
              {/* Speaker Avatar Badge */}
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "50%",
                  background: c.bg,
                  border: `1px solid ${c.border}`,
                  color: c.color,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.8125rem",
                  fontWeight: 700,
                  flexShrink: 0,
                  marginTop: "0.15rem",
                }}
              >
                {turn.speaker.slice(0, 2).toUpperCase()}
              </div>

              {/* Turn Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.25rem" }}>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 700, color: c.color }}>
                    {turn.speaker}
                  </span>
                  {displayId && displayId !== turn.speaker && (
                    <span
                      style={{
                        fontSize: "0.68rem",
                        color: "var(--color-accent)",
                        background: "rgba(99, 102, 241, 0.12)",
                        border: "1px solid rgba(99, 102, 241, 0.25)",
                        padding: "0.08rem 0.4rem",
                        borderRadius: "4px",
                        fontFamily: "monospace",
                        fontWeight: 600,
                      }}
                    >
                      ID: {displayId}
                    </span>
                  )}
                  {turn.time && (
                    <span
                      style={{
                        fontSize: "0.7rem",
                        color: "var(--color-text-muted)",
                        background: "rgba(0, 0, 0, 0.3)",
                        padding: "0.1rem 0.4rem",
                        borderRadius: "4px",
                        fontFamily: "monospace",
                      }}
                    >
                      ⏱️ {turn.time}
                    </span>
                  )}
                </div>

                <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--color-text)", lineHeight: 1.6, wordBreak: "break-word" }}>
                  {turn.text}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

