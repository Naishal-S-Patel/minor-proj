import { useEffect, useRef } from "react";
import { useDispatch } from "react-redux";
import type { AppDispatch } from "../store";
import { searchMeetings, clearSearch, setSearchQuery } from "../store/meetingsSlice";
import { useSelector } from "react-redux";
import { selectSearch } from "../store/meetingsSlice";

export function SearchBar() {
  const dispatch = useDispatch<AppDispatch>();
  const { searchStatus, searchQuery } = useSelector(selectSearch);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && document.activeElement === inputRef.current) {
        dispatch(clearSearch());
        if (inputRef.current) inputRef.current.value = "";
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [dispatch]);

  const handleChange = (value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim()) {
      dispatch(clearSearch());
      return;
    }
    debounceRef.current = setTimeout(() => {
      dispatch(setSearchQuery(value));
      dispatch(searchMeetings(value));
    }, 300);
  };

  return (
    <div style={{ position: "relative", marginBottom: "1.5rem" }}>
      <div style={{ position: "relative" }}>
        <span style={{
          position: "absolute",
          left: "0.875rem",
          top: "50%",
          transform: "translateY(-50%)",
          color: "var(--color-text-muted)",
          fontSize: "0.875rem",
          pointerEvents: "none",
        }}>
          &#128269;
        </span>
        <input
          ref={inputRef}
          type="text"
          defaultValue={searchQuery}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="Search meetings..."
          style={{
            width: "100%",
            padding: "0.75rem 2.5rem",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            color: "var(--color-text)",
            fontSize: "0.9375rem",
            fontFamily: "inherit",
            backdropFilter: "blur(12px)",
            transition: "border-color 0.2s, box-shadow 0.2s",
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--color-accent)";
            e.currentTarget.style.boxShadow = "0 0 0 3px rgba(108, 99, 255, 0.15)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "var(--color-border)";
            e.currentTarget.style.boxShadow = "none";
          }}
        />
        {searchStatus === "loading" && (
          <span style={{
            position: "absolute",
            right: "0.875rem",
            top: "50%",
            transform: "translateY(-50%)",
            width: "16px",
            height: "16px",
            border: "2px solid var(--color-surface-2)",
            borderTopColor: "var(--color-accent)",
            borderRadius: "50%",
            animation: "spin 0.6s linear infinite",
          }} />
        )}
      </div>
      <style>{`@keyframes spin { to { transform: translateY(-50%) rotate(360deg); } }`}</style>
    </div>
  );
}
