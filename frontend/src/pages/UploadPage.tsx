import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Navbar } from "../components/Navbar";

type UploadState = "idle" | "uploading" | "success" | "error";

const AUDIO_EXTS = [".mp3", ".mp4", ".wav", ".m4a", ".m4v"];

function getFileIcon(name: string): string {
  const ext = name.slice(name.lastIndexOf(".")).toLowerCase();
  if (ext === ".txt") return "\uD83D\uDCC4";
  if (AUDIO_EXTS.includes(ext)) return "\uD83C\uDFB5";
  return "\uD83D\uDCC1";
}

export function UploadPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setError(null);
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
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !selectedFile) {
      setError("Please provide a title and select a file.");
      return;
    }
    setUploadState("uploading");
    setError(null);
    try {
      const meeting = await api.uploadMeeting(title.trim(), selectedFile);
      setUploadState("success");
      navigate(`/meetings/${meeting.id}`);
    } catch (err) {
      setUploadState("error");
      setError(err instanceof ApiError ? err.message : "An unexpected error occurred.");
    }
  };

  const isUploading = uploadState === "uploading";
  const hasFile = selectedFile !== null;

  return (
    <>
      <Navbar />
      <div className="container" style={{ maxWidth: "640px" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>
          Upload Meeting
        </h1>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "1.25rem" }}>
            <label htmlFor="title" style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.8125rem", fontWeight: 500, color: "var(--color-text-muted)" }}>
              Meeting Title
            </label>
            <input
              id="title"
              type="text"
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Q3 Planning Meeting"
              maxLength={200}
              disabled={isUploading}
            />
          </div>

          <div style={{ marginBottom: "1.25rem" }}>
            <label style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.8125rem", fontWeight: 500, color: "var(--color-text-muted)" }}>
              Transcript or Audio File
            </label>
            <div
              className={`drag-zone ${isDragOver ? "drag-over" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.mp3,.mp4,.wav,.m4a,.m4v"
                onChange={handleFileChange}
                disabled={isUploading}
                style={{ display: "none" }}
              />
              {hasFile ? (
                <div>
                  <span style={{ fontSize: "1.5rem" }}>{getFileIcon(selectedFile!.name)}</span>
                  <p style={{ margin: "0.5rem 0 0.25rem", fontWeight: 500 }}>{selectedFile!.name}</p>
                  <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--color-text-muted)" }}>
                    {((selectedFile!.size) / 1024).toFixed(1)} KB
                  </p>
                </div>
              ) : (
                <div>
                  <span style={{ fontSize: "1.5rem", opacity: 0.5 }}>&#8682;</span>
                  <p style={{ margin: "0.5rem 0 0", color: "var(--color-text-muted)" }}>
                    Drag and drop a .txt or audio file here, or click to browse
                  </p>
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className="error-card" style={{ marginBottom: "1.25rem" }} role="alert">
              {error}
            </div>
          )}

          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isUploading || !hasFile || !title.trim()}
            >
              {isUploading ? "Uploading\u2026" : "Upload Transcript"}
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
