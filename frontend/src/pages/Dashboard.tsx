import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useSelector, useDispatch } from "react-redux";
import type { AppDispatch } from "../store";
import { selectMeetingsList, selectSearch, fetchMeetings } from "../store/meetingsSlice";
import { MeetingCard } from "../components/MeetingCard";
import { MeetingVolumeChart } from "../components/MeetingVolumeChart";
import { Navbar } from "../components/Navbar";
import { SearchBar } from "../components/SearchBar";
import { SearchResults } from "../components/SearchResults";

export function Dashboard() {
  const dispatch = useDispatch<AppDispatch>();
  const { list: meetings, listStatus, listError } = useSelector(selectMeetingsList);
  const { searchQuery } = useSelector(selectSearch);

  useEffect(() => {
    dispatch(fetchMeetings());
  }, [dispatch]);

  const isLoading = listStatus === "loading" || listStatus === "idle";
  const error = listStatus === "failed" ? listError : null;
  const isSearching = searchQuery.trim().length > 0;

  return (
    <>
      <Navbar />
      <div className="container">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "2rem",
          }}
        >
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Meetings</h1>
        </div>

        <SearchBar />

        {isSearching ? (
          <SearchResults />
        ) : (
          <>
            {isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {[1, 2, 3].map((i) => (
                  <div key={i} className="skeleton" style={{ height: "88px", width: "100%" }} />
                ))}
              </div>
            )}

            {!isLoading && error && (
              <div className="error-card">
                <p>{error}</p>
              </div>
            )}

            {!isLoading && !error && meetings.length === 0 && (
              <div className="empty-state">
                <div className="empty-state-icon">&#128197;</div>
                <h3 style={{ fontSize: "1.125rem", marginBottom: "0.5rem" }}>No meetings yet</h3>
                <p style={{ marginBottom: "1.5rem" }}>Upload a transcript or audio file to get started.</p>
                <Link to="/upload" className="btn btn-primary">
                  Upload your first meeting
                </Link>
              </div>
            )}

            {!isLoading && !error && meetings.length > 0 && (
              <>
                {meetings.length >= 1 && <MeetingVolumeChart meetings={meetings} />}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {meetings.map((meeting) => (
                    <MeetingCard key={meeting.id} meeting={meeting} />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
