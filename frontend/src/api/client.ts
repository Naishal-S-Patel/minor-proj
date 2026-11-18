/**
 * Minimal typed API client.
 */

import type { User } from "../types/user";

const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type MeetingStatus =
  | "uploaded"
  | "transcribing"
  | "cleaning"
  | "analyzing"
  | "processed"
  | "failed";

export interface ActionItem {
  id: string;
  person: string;
  task: string;
  deadline: string | null;
  done: boolean;
}

export interface CalendarEvent {
  id: string;
  title: string;
  relative_time: string;
  event_date: string;
  formatted_date: string;
  days_from_now?: number | null;
  speaker?: string | null;
  context: string;
  category: "exam" | "deadline" | "meeting" | "presentation" | "review" | string;
}

export interface DialogueTurn {
  id?: string;
  speaker: string;
  speaker_id?: string | null;
  time?: string | null;
  text: string;
}

export interface Meeting {
  id: string;
  title: string;
  status: MeetingStatus;
  created_at: string;
  updated_at: string;
  meeting_id_code?: string | null;
  platform?: string | null;
  language?: string | null;
  detected_language?: string | null;
  cleaned_transcript: string | null;
  error_message: string | null;
  audio_filename: string | null;
  audio_duration_seconds: number | null;
  live_transcript_lines?: string[];
  summary: string | null;
  action_items: ActionItem[];
  decisions: string[];
  keywords: string[];
  sentiment: string | null;
  speakers: string[];
  speaker_map?: Record<string, string>;
  calendar_events?: CalendarEvent[];
  dialogue_turns?: DialogueTurn[];
  share_token: string | null;
  is_public: boolean;
}

export interface MeetingSearchResult {
  id: string;
  title: string;
  status: MeetingStatus;
  created_at: string;
  summary: string | null;
  sentiment: string | null;
  highlight: string | null;
  score: number;
}

export interface KeywordFrequency {
  keyword: string;
  count: number;
}

export interface PendingTask {
  meeting_id: string;
  meeting_title: string;
  person: string;
  task: string;
  item_id: string;
  deadline: string | null;
}

export interface WeeklyCount {
  week: string;
  count: number;
}

export interface AnalyticsOverview {
  total_meetings: number;
  processed_meetings: number;
  sentiment_breakdown: { positive: number; neutral: number; negative: number };
  top_keywords: KeywordFrequency[];
  pending_tasks: PendingTask[];
  weekly_counts: WeeklyCount[];
}

// Polling constants for MeetingDetail
export const IN_PROGRESS_STATUSES: MeetingStatus[] = ["uploaded", "transcribing", "cleaning", "analyzing"];
export const TERMINAL_STATUSES: MeetingStatus[] = ["processed", "failed"];
export const POLL_INTERVAL_MS = 1500; // 1.5s snappy polling for live line-by-line streaming

/**
 * Shared fetch wrapper: parses JSON, throws a typed ApiError on non-2xx
 * responses.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (response.status === 401 && path !== "/auth/me") {
    window.location.href = "/login";
    throw new ApiError("Session expired", 401);
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        message = body.detail;
      }
    } catch {
      // ignore
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  auth: {
    me: () => request<User>("/auth/me"),
    logout: () => request<void>("/auth/logout", { method: "POST" }),
  },
  listMeetings: () => request<Meeting[]>("/meetings"),
  getMeeting: (id: string) => request<Meeting>(`/meetings/${id}`),
  uploadMeeting: (
    title: string,
    file: File,
    meetingIdCode?: string,
    platform?: string,
    language?: string
  ) => {
    const form = new FormData();
    form.append("title", title);
    form.append("file", file);
    if (meetingIdCode) form.append("meeting_id_code", meetingIdCode);
    if (platform) form.append("platform", platform);
    if (language) form.append("language", language);
    return request<Meeting>("/meetings", { method: "POST", body: form, headers: {} });
  },
  updateActionItem: (meetingId: string, itemId: string, done: boolean) =>
    request<Meeting>(`/meetings/${meetingId}/action-items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ done }),
    }),
  updateSpeakerMap: (meetingId: string, speakerMap: Record<string, string>) =>
    request<Meeting>(`/meetings/${meetingId}/speakers`, {
      method: "PATCH",
      body: JSON.stringify({ speaker_map: speakerMap }),
    }),
  searchMeetings: (query: string) =>
    request<MeetingSearchResult[]>(`/meetings/search?q=${encodeURIComponent(query)}`),
  exportMeeting: (id: string, format: "pdf" | "csv") => {
    window.open(`/api/meetings/${id}/export?format=${format}`, "_blank");
  },
  downloadCalendarIcs: (meetingId: string) => {
    window.open(`/api/meetings/${meetingId}/calendar/ics`, "_blank");
  },
  shareMeeting: (id: string) => request<{ share_url: string }>(`/meetings/${id}/share`, { method: "POST" }),
  unshareMeeting: (id: string) => request<void>(`/meetings/${id}/share`, { method: "DELETE" }),
  getSharedMeeting: (token: string) => request<Meeting>(`/shared/${token}`),
  chatMeeting: (id: string, question: string) =>
    request<{ answer: string }>(`/meetings/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  getAnalyticsOverview: () => request<AnalyticsOverview>("/analytics/overview"),
};
