import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Navbar } from "../components/Navbar";

type UploadState = "idle" | "uploading" | "success" | "error";

const AUDIO_EXTS = [".mp3", ".mp4", ".wav", ".m4a", ".m4v"];

const PLATFORMS = [
  { id: "Zoom", label: "Zoom", icon: "📹" },
  { id: "Google Meet", label: "Google Meet", icon: "🟢" },
  { id: "Microsoft Teams", label: "Teams", icon: "👥" },
  { id: "In-Person", label: "In-Person", icon: "🎙️" },
];

const LANGUAGES = [
  { code: "auto", name: "Auto Detect", flag: "🌐" },
  { code: "en", name: "English", flag: "🇺🇸" },
  { code: "hi", name: "Hindi (हिन्दी)", flag: "🇮🇳" },
  { code: "gu", name: "Gujarati (ગુજરાતી)", flag: "🇮🇳" },
  { code: "es", name: "Spanish (Español)", flag: "🇪🇸" },
  { code: "fr", name: "French (Français)", flag: "🇫🇷" },
  { code: "de", name: "German (Deutsch)", flag: "🇩🇪" },
  { code: "zh", name: "Chinese (中文)", flag: "🇨🇳" },
  { code: "ja", name: "Japanese (日本語)", flag: "🇯🇵" },
  { code: "ar", name: "Arabic (العربية)", flag: "🇸🇦" },
  { code: "pt", name: "Portuguese (Português)", flag: "🇧🇷" },
  { code: "ru", name: "Russian (Русский)", flag: "🇷🇺" },
];

function getFileIcon(name: string): string {
  const ext = name.slice(name.lastIndexOf(".")).toLowerCase();
  if (ext === ".txt" || ext === ".vtt") return "📄";
  if (AUDIO_EXTS.includes(ext)) return "🎵";
  return "📁";
}

export function UploadPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState("");
  const [meetingIdCode, setMeetingIdCode] = useState("");
  const [platform, setPlatform] = useState("Zoom");
  const [language, setLanguage] = useState("auto");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setError(null);
      if (!title.trim()) {
        const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
        setTitle(cleanName.charAt(0).toUpperCase() + cleanName.slice(1));
      }
    }
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      setSelectedFile(file);
      setError(null);
      if (!title.trim()) {
        const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
        setTitle(cleanName.charAt(0).toUpperCase() + cleanName.slice(1));
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !selectedFile) {
      setError("Please provide a title and select a transcript or audio file.");
      return;
    }
    setUploadState("uploading");
    setError(null);
    try {
      const meeting = await api.uploadMeeting(
        title.trim(),
        selectedFile,
        meetingIdCode.trim() || undefined,
        platform || undefined,
        language || undefined
      );
      setUploadState("success");
      navigate(`/meetings/${meeting.id}`);
    } catch (err) {
      setUploadState("error");
      setError(err instanceof ApiError ? err.message : "An unexpected error occurred.");
    }
  };

  // Sample presets for quick testing
  const loadPreset = (presetType: "lecture" | "standup" | "hindi") => {
    if (presetType === "lecture") {
      setTitle("CS402: Distributed Systems Lecture & Exam Prep");
      setMeetingIdCode("842-192-3841");
      setPlatform("Zoom");
      setLanguage("en");
      const content = `Topic: CS402 Distributed Systems Lecture
Zoom Meeting ID: 842-192-3841
Passcode: 948123

[00:05] Prof. Mehta: Good morning everyone, let's start today's lecture on consensus algorithms and Raft.
[00:25] Alex: Good morning professor. We had a question about Paxos versus Raft from the last assignment.
[00:45] Prof. Mehta: Great question. Paxos guarantees safety but Raft is much more understandable.
[01:15] Prof. Mehta: Important announcement: There will be a test after 3 days covering consensus protocols and leader election.
[01:40] Priya: Noted sir. Will it be multiple choice or coding questions?
[01:55] Prof. Mehta: It will be a mix of both. Priya, please share the study guide with the cohort by Friday.
[02:15] Alex: I will submit the project repository link before tomorrow evening.
[02:35] Prof. Mehta: Perfect. We decided to hold an extra doubt clearing session this Thursday at 4 PM.
`;
      const blob = new Blob([content], { type: "text/plain" });
      const file = new File([blob], "cs402_lecture_notes.txt", { type: "text/plain" });
      setSelectedFile(file);
      setError(null);
    } else if (presetType === "hindi") {
      setTitle("Project Planning & Design Review (Hindi/Hinglish)");
      setMeetingIdCode("912-384-5512");
      setPlatform("Google Meet");
      setLanguage("hi");
      const content = `Meeting ID: 912-384-5512
Platform: Google Meet

[00:10] Rahul: Namaste team, aaj hum final sprint planning aur testing schedule discuss karenge.
[00:30] Anjali: Haan Rahul, maine backend API integration complete kar liya hai.
[00:55] Rahul: Bohot badiya. Dhyaan rahe, humara client test after 3 days scheduled hai.
[01:20] Vikram: Main test environment setup ready kar dunga by tomorrow morning.
[01:45] Anjali: Main testing documentation Friday tak share kar dungi.
[02:10] Rahul: Humne decide kiya hai ki pehle local cluster pe deploy karenge.
`;
      const blob = new Blob([content], { type: "text/plain" });
      const file = new File([blob], "hindi_sprint_meeting.txt", { type: "text/plain" });
      setSelectedFile(file);
      setError(null);
    } else {
      setTitle("Q4 Strategic Product Alignment");
      setMeetingIdCode("771-482-9011");
      setPlatform("Zoom");
      setLanguage("en");
      const content = `Zoom Meeting ID: 771-482-9011
Host: Sarah Jenkins

[00:10] Sarah: Welcome everyone to the product roadmap sync.
[00:30] David: The customer feedback on the new real-time transcription feature has been overwhelmingly positive.
[00:55] Sarah: That is fantastic. Let us make sure the presentation for executives is scheduled after 3 days.
[01:25] David: I will finalize the slide deck by Thursday afternoon.
[01:50] Elena: I am responsible for generating the analytics metrics report before the meeting.
[02:10] Sarah: We agreed to launch the beta to all tier-1 customers next week.
`;
      const blob = new Blob([content], { type: "text/plain" });
      const file = new File([blob], "product_strategy_sync.txt", { type: "text/plain" });
      setSelectedFile(file);
      setError(null);
    }
  };

  const isUploading = uploadState === "uploading";
  const hasFile = selectedFile !== null;

  return (
    <>
      <Navbar />
      <div className="container" style={{ maxWidth: "760px", paddingBottom: "3rem" }}>
        {/* Header banner */}
        <div style={{ marginBottom: "2rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
            <span style={{ fontSize: "1.5rem" }}>✨</span>
            <span style={{
              fontSize: "0.75rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--color-accent)",
              background: "rgba(108, 99, 255, 0.12)",
              padding: "0.2rem 0.6rem",
              borderRadius: "999px",
            }}>
              Intelligent Ingestion
            </span>
          </div>
          <h1 style={{ fontSize: "1.875rem", fontWeight: 800, letterSpacing: "-0.02em" }}>
            Upload & Analyze Meeting
          </h1>
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.9375rem", marginTop: "0.25rem" }}>
            Upload an audio recording or transcript with multi-language detection, Zoom meeting IDs, calendar events, and real-time streaming.
          </p>
        </div>

        {/* Quick Presets */}
        <div
          className="glass-card"
          style={{
            padding: "1rem 1.25rem",
            marginBottom: "1.75rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "0.75rem",
            background: "linear-gradient(135deg, rgba(108, 99, 255, 0.08) 0%, rgba(168, 85, 247, 0.05) 100%)",
            border: "1px solid rgba(108, 99, 255, 0.2)",
          }}
        >
          <div>
            <p style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text)" }}>
              ⚡ Quick Test Samples
            </p>
            <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", margin: 0 }}>
              Instantly test Zoom ID, "test after 3 days", and multilingual features
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => loadPreset("lecture")}
              className="btn btn-secondary"
              style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem" }}
            >
              🎓 Class Lecture (Test in 3 Days)
            </button>
            <button
              type="button"
              onClick={() => loadPreset("hindi")}
              className="btn btn-secondary"
              style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem" }}
            >
              🇮🇳 Hindi / Multi-lang
            </button>
            <button
              type="button"
              onClick={() => loadPreset("standup")}
              className="btn btn-secondary"
              style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem" }}
            >
              💼 Product Sync
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Title */}
          <div style={{ marginBottom: "1.5rem" }}>
            <label
              htmlFor="title"
              style={{
                display: "block",
                marginBottom: "0.5rem",
                fontSize: "0.8125rem",
                fontWeight: 600,
                color: "var(--color-text)",
              }}
            >
              Meeting Title *
            </label>
            <input
              id="title"
              type="text"
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. CS402 Lecture & Exam Prep or Q3 Roadmap Review"
              maxLength={200}
              disabled={isUploading}
              style={{ fontSize: "0.9375rem" }}
            />
          </div>

          {/* Grid: Platform & Meeting ID */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
            <div>
              <label
                style={{
                  display: "block",
                  marginBottom: "0.5rem",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  color: "var(--color-text)",
                }}
              >
                Platform
              </label>
              <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
                {PLATFORMS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setPlatform(p.id)}
                    style={{
                      flex: 1,
                      minWidth: "70px",
                      padding: "0.45rem 0.5rem",
                      borderRadius: "var(--radius)",
                      border: platform === p.id ? "1px solid var(--color-accent)" : "1px solid var(--color-border)",
                      background: platform === p.id ? "rgba(108, 99, 255, 0.15)" : "var(--color-surface)",
                      color: platform === p.id ? "white" : "var(--color-text-muted)",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "0.3rem",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <span>{p.icon}</span> {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label
                htmlFor="meetingId"
                style={{
                  display: "block",
                  marginBottom: "0.5rem",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  color: "var(--color-text)",
                }}
              >
                Zoom / Meeting ID <span style={{ color: "var(--color-text-muted)", fontWeight: 400 }}>(Optional)</span>
              </label>
              <input
                id="meetingId"
                type="text"
                className="input"
                value={meetingIdCode}
                onChange={(e) => setMeetingIdCode(e.target.value)}
                placeholder="e.g. 842-192-3841"
                disabled={isUploading}
              />
            </div>
          </div>

          {/* Language Selector */}
          <div style={{ marginBottom: "1.5rem" }}>
            <label
              htmlFor="language"
              style={{
                display: "block",
                marginBottom: "0.5rem",
                fontSize: "0.8125rem",
                fontWeight: 600,
                color: "var(--color-text)",
              }}
            >
              Language Support
            </label>
            <div style={{ position: "relative" }}>
              <select
                id="language"
                className="input"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                disabled={isUploading}
                style={{ cursor: "pointer", appearance: "auto" }}
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code} style={{ background: "#111827", color: "white" }}>
                    {l.flag} {l.name}
                  </option>
                ))}
              </select>
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", marginTop: "0.35rem" }}>
              Select language or keep "Auto Detect" — Whisper & our local AI engine detect and process multilingual speech accurately.
            </p>
          </div>

          {/* File Upload Zone */}
          <div style={{ marginBottom: "1.75rem" }}>
            <label
              style={{
                display: "block",
                marginBottom: "0.5rem",
                fontSize: "0.8125rem",
                fontWeight: 600,
                color: "var(--color-text)",
              }}
            >
              Upload Audio File or Transcript *
            </label>
            <div
              className={`drag-zone ${isDragOver ? "drag-over" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              style={{ padding: "2.5rem 1.5rem", textAlign: "center" }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.vtt,.mp3,.mp4,.wav,.m4a,.m4v"
                onChange={handleFileChange}
                disabled={isUploading}
                style={{ display: "none" }}
              />

              {hasFile ? (
                <div className="animate-fade-in">
                  <div
                    style={{
                      width: "60px",
                      height: "60px",
                      borderRadius: "50%",
                      background: "rgba(108, 99, 255, 0.15)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      margin: "0 auto 1rem",
                      fontSize: "2rem",
                    }}
                  >
                    {getFileIcon(selectedFile!.name)}
                  </div>
                  <p style={{ margin: "0.25rem 0", fontWeight: 700, fontSize: "1.0625rem" }}>
                    {selectedFile!.name}
                  </p>
                  <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--color-text-muted)" }}>
                    {(selectedFile!.size / 1024).toFixed(1)} KB &bull; Ready to analyze
                  </p>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedFile(null);
                    }}
                    style={{
                      marginTop: "0.75rem",
                      background: "none",
                      border: "none",
                      color: "var(--color-error)",
                      fontSize: "0.75rem",
                      cursor: "pointer",
                      textDecoration: "underline",
                    }}
                  >
                    Remove and choose another
                  </button>
                </div>
              ) : (
                <div>
                  <div
                    style={{
                      width: "56px",
                      height: "56px",
                      borderRadius: "50%",
                      background: "rgba(255, 255, 255, 0.05)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      margin: "0 auto 0.75rem",
                      fontSize: "1.75rem",
                      opacity: 0.8,
                    }}
                  >
                    ⬆️
                  </div>
                  <p style={{ margin: "0.5rem 0 0.25rem", fontWeight: 600, fontSize: "0.9375rem" }}>
                    Drop your audio, .vtt, or .txt file here, or <span style={{ color: "var(--color-accent)" }}>browse</span>
                  </p>
                  <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                    Supports MP3, WAV, M4A, MP4 (up to 25 MB) and .txt / Zoom .vtt transcripts
                  </p>
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className="error-card" style={{ marginBottom: "1.5rem" }} role="alert">
              <strong>Error:</strong> {error}
            </div>
          )}

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isUploading || !hasFile || !title.trim()}
              style={{
                padding: "0.75rem 1.75rem",
                fontSize: "0.9375rem",
                fontWeight: 600,
                boxShadow: "0 4px 15px rgba(108, 99, 255, 0.3)",
              }}
            >
              {isUploading ? "Uploading & Initializing..." : "Analyze Meeting ✨"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate("/")}
              disabled={isUploading}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
