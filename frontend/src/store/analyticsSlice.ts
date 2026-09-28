import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import type { AnalyticsOverview } from "../api/client";
import { api } from "../api/client";

interface AnalyticsState {
  overview: AnalyticsOverview | null;
  status: "idle" | "loading" | "succeeded" | "failed";
  error: string | null;
}

const initialState: AnalyticsState = {
  overview: null,
  status: "idle",
  error: null,
};

export const fetchAnalytics = createAsyncThunk(
  "analytics/fetchOverview",
  async () => {
    return await api.getAnalyticsOverview();
  },
);

const analyticsSlice = createSlice({
  name: "analytics",
  initialState,
  reducers: {
    clearAnalytics(state) {
      state.overview = null;
      state.status = "idle";
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchAnalytics.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchAnalytics.fulfilled, (state, action) => {
        state.overview = action.payload;
        state.status = "succeeded";
      })
      .addCase(fetchAnalytics.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message ?? "Failed to load analytics";
      });
  },
});

export const { clearAnalytics } = analyticsSlice.actions;
export const selectAnalytics = (state: { analytics: AnalyticsState }) => state.analytics;
export default analyticsSlice.reducer;
