import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import type { Meeting, MeetingSearchResult } from "../api/client";
import { api } from "../api/client";

interface MeetingsState {
  list: Meeting[];
  listStatus: "idle" | "loading" | "succeeded" | "failed";
  listError: string | null;
  selected: Meeting | null;
  selectedStatus: "idle" | "loading" | "succeeded" | "failed";
  selectedError: string | null;
  searchResults: MeetingSearchResult[];
  searchStatus: "idle" | "loading" | "succeeded" | "failed";
  searchError: string | null;
  searchQuery: string;
  shareUrls: Record<string, string>;
  shareStatus: "idle" | "loading" | "succeeded" | "failed";
}

const initialState: MeetingsState = {
  list: [],
  listStatus: "idle",
  listError: null,
  selected: null,
  selectedStatus: "idle",
  selectedError: null,
  searchResults: [],
  searchStatus: "idle",
  searchError: null,
  searchQuery: "",
  shareUrls: {},
  shareStatus: "idle",
};

export const fetchMeetings = createAsyncThunk(
  "meetings/fetchMeetings",
  async () => {
    return await api.listMeetings();
  },
);

export const fetchMeeting = createAsyncThunk(
  "meetings/fetchMeeting",
  async (id: string) => {
    return await api.getMeeting(id);
  },
);

export const searchMeetings = createAsyncThunk(
  "meetings/searchMeetings",
  async (query: string) => {
    return await api.searchMeetings(query);
  },
);

export const shareMeeting = createAsyncThunk(
  "meetings/shareMeeting",
  async (id: string) => {
    return await api.shareMeeting(id);
  },
);

export const unshareMeeting = createAsyncThunk(
  "meetings/unshareMeeting",
  async (id: string) => {
    await api.unshareMeeting(id);
    return id;
  },
);

export const toggleActionItem = createAsyncThunk(
  "meetings/toggleActionItem",
  async (args: { meetingId: string; itemId: string; done: boolean }) => {
    // Returns the FULL updated Meeting (see the backend route's own
    // reasoning for this response shape) -- the fulfilled reducer below
    // replaces `state.selected` wholesale with this response rather than
    // trying to locate-and-patch a single nested action_items entry in
    // Redux state by hand, which would risk drifting out of sync with
    // whatever the server actually persisted.
    return await api.updateActionItem(args.meetingId, args.itemId, args.done);
  },
);

const meetingsSlice = createSlice({
  name: "meetings",
  initialState,
  reducers: {
    updateSelectedMeeting(state, action) {
      state.selected = action.payload;
    },
    clearSelectedMeeting(state) {
      state.selected = null;
      state.selectedStatus = "idle";
      state.selectedError = null;
    },
    clearSearch(state) {
      state.searchResults = [];
      state.searchStatus = "idle";
      state.searchError = null;
      state.searchQuery = "";
    },
    setSearchQuery(state, action) {
      state.searchQuery = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchMeetings.pending, (state) => {
        state.listStatus = "loading";
        state.listError = null;
      })
      .addCase(fetchMeetings.fulfilled, (state, action) => {
        state.list = action.payload;
        state.listStatus = "succeeded";
      })
      .addCase(fetchMeetings.rejected, (state, action) => {
        state.listStatus = "failed";
        state.listError = action.error.message ?? "Failed to load meetings";
      })
      .addCase(fetchMeeting.pending, (state) => {
        state.selectedStatus = "loading";
        state.selectedError = null;
      })
      .addCase(fetchMeeting.fulfilled, (state, action) => {
        state.selected = action.payload;
        state.selectedStatus = "succeeded";
      })
      .addCase(fetchMeeting.rejected, (state, action) => {
        state.selectedStatus = "failed";
        state.selectedError = action.error.message ?? "Failed to load meeting";
      })
      .addCase(searchMeetings.pending, (state) => {
        state.searchStatus = "loading";
        state.searchError = null;
      })
      .addCase(searchMeetings.fulfilled, (state, action) => {
        state.searchResults = action.payload;
        state.searchStatus = "succeeded";
      })
      .addCase(searchMeetings.rejected, (state, action) => {
        state.searchStatus = "failed";
        state.searchError = action.error.message ?? "Search failed";
      })
      .addCase(shareMeeting.pending, (state) => {
        state.shareStatus = "loading";
      })
      .addCase(shareMeeting.fulfilled, (state, action) => {
        const { share_url } = action.payload as { share_url: string };
        const id = action.meta.arg as string;
        state.shareUrls[id] = share_url;
        state.shareStatus = "succeeded";
      })
      .addCase(shareMeeting.rejected, (state) => {
        state.shareStatus = "failed";
      })
      .addCase(unshareMeeting.fulfilled, (state, action) => {
        delete state.shareUrls[action.payload];
        state.shareStatus = "idle";
      })
      // No .pending/.rejected handling for toggleActionItem deliberately --
      // see ActionItemsTable.tsx's own optimistic-update comment for why
      // the checkbox UI doesn't wait on this slice's status at all.
      .addCase(toggleActionItem.fulfilled, (state, action) => {
        // Only replace `selected` if it's still the SAME meeting the toggle
        // was for -- guards against a stale response landing after the
        // user has already navigated to a different meeting (e.g. a slow
        // network response arriving after MeetingDetail unmounted and
        // remounted for a different id). Without this check, a late
        // response could silently overwrite whatever meeting is now
        // actually being viewed with data for a DIFFERENT one.
        if (state.selected && state.selected.id === action.payload.id) {
          state.selected = action.payload;
        }
      });
  },
});

export const { updateSelectedMeeting, clearSelectedMeeting, clearSearch, setSearchQuery } = meetingsSlice.actions;
export const selectMeetingsList = (state: { meetings: MeetingsState }) => state.meetings;
export const selectMeetingDetail = (state: { meetings: MeetingsState }) => state.meetings;
export const selectSearch = (state: { meetings: MeetingsState }) => state.meetings;
export const selectShareUrl = (state: { meetings: MeetingsState }, id: string) =>
  state.meetings.shareUrls[id] ?? null;
export default meetingsSlice.reducer;
