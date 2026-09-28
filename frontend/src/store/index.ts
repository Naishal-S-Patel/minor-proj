import { configureStore } from "@reduxjs/toolkit";
import authReducer from "./authSlice";
import meetingsReducer from "./meetingsSlice";
import analyticsReducer from "./analyticsSlice";

export const store = configureStore({
  reducer: {
    auth: authReducer,
    meetings: meetingsReducer,
    analytics: analyticsReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
