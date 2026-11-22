# AI Meeting Intelligence — Comprehensive Technical Viva Guide

> **Prepared for:** Final Project Evaluation & Technical Viva  
> **Repository:** `Ai-indivisual-project-master`  
> **Tech Stack:** FastAPI | React (TypeScript + Vite) | AWS Transcribe + Local Whisper | AWS Bedrock (Nova / Claude) | MongoDB | Pytest (161 tests)  

---

## 1. Project Overview & Problem Statement

### The Problem
Organizations and academic teams conduct hours of virtual meetings (Zoom, Google Meet, Teams). Reviewing recordings or manual note-taking is inefficient, error-prone, and causes lost action items, forgotten deadlines, and poor accountability.

### The Solution: AI Meeting Intelligence
An automated, privacy-aware, multi-modal meeting intelligence platform that takes meeting recordings (MP4, M4A, WAV, MP3) or text transcripts (VTT, TXT) and delivers:
1. **Timestamped, Speaker-Diarized Transcripts** (Zoom `USR-101` and Meet `P01` tags mapped to real participant names).
2. **Dual-Tier Hybrid ASR Pipeline:** Primary cloud transcription via **AWS Transcribe** (with S3) in Mumbai (`ap-south-1`) with seamless offline fallback to **local Whisper**.
3. **Multi-Model Intelligence:** Executive summaries, decisions, and calendar events generated via **AWS Bedrock** (Amazon Nova Lite / Claude 3.5 Sonnet) with offline fallback to **SmartLocalExtractor**.
4. **Interactive Action Item Management:** Real-time completion progress tracking (`X of Y completed`), `✓ Done` / `⏳ Pending` status pills, and optimistic persistence to MongoDB.
5. **Context-Aware Meeting Q&A Chatbot:** Instant question answering with 1-click suggested question pills.
6. **Automated Calendar Scheduling:** Test and deadline detection with 1-click `.ics` calendar invite downloads.

---

## 2. High-Level System Architecture

```
                    ┌─────────────────────────────────────────────────────────┐
                    │           Frontend: React 18 + TypeScript + Vite         │
                    │   (TailwindCSS, Recharts, Interactive Action Items, Chat) │
                    └────────────────────────────┬────────────────────────────┘
                                                 │ HTTP / JSON API Proxy (/api)
                                                 ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │                Backend: FastAPI (Python 3.11)            │
                    └──────────┬─────────────────┬──────────────────┬─────────┘
                               │                 │                  │
            ┌──────────────────▼──┐   ┌──────────▼────────┐   ┌─────▼────────────────┐
            │ Audio / Speech ASR  │   │ LLM Intelligence  │   │ Persistence Layer    │
            ├─────────────────────┤   ├───────────────────┤   ├──────────────────────┤
            │ [Priority 1: Cloud] │   │ [Priority 1: Cloud]│   │ • MongoDB (Motor)    │
            │ • AWS Transcribe    │   │ • AWS Bedrock     │   │ • Repository Pattern │
            │ • AWS S3 Audio      │   │   (Nova / Claude) │   │   (Decoupled DB)     │
            │                     │   │                   │   │ • JWT Cookie Auth    │
            │ [Priority 2: Local] │   │ [Priority 2: Local]│   │ • 161 Unit Tests     │
            │ • OpenAI Whisper    │   │ • SmartLocal      │   └──────────────────────┘
            │ • BIC Diarization   │   │   Extractor & QA  │
            └─────────────────────┘   └───────────────────┘
```

### Layered Architecture (Clean Architecture Principles)
- **`app/api/`**: HTTP transport layer (FastAPI routers). Handles request validation, status codes, cookies, and CORS. No direct database or business logic calls.
- **`app/services/`**: Pure business logic (AWS Transcribe, Whisper audio transcription, diarization, phonetic normalization, AWS Bedrock LLM client, calendar parsing).
- **`app/repositories/`**: The **only** layer that accesses MongoDB collections. Decoupled using interfaces, allowing in-memory mocking for **161 unit tests** without requiring a live database.
- **`app/models/`**: Strict Pydantic models for data validation, serialization, and database document schemas.
- **`app/workers/`**: Asynchronous background workers for long-running speech recognition and NLP tasks without blocking web requests.

---

## 3. End-to-End Processing Pipeline

```
[ Upload Video/Audio ]
         │
         ▼
[ 1. Ingestion & Validation ] ──> Magic number check, format validation (WAV, MP4, M4A)
         │
         ▼
[ 2. Hybrid Speech Recognition ]
    ├─ Priority 1 (Online): AWS S3 upload -> AWS Transcribe (Mumbai ap-south-1) with Speaker Labels (~5-10s)
    └─ Fallback 2 (Offline): PyDub FFmpeg 16kHz WAV -> OpenAI Whisper greedy CPU ASR + BIC Diarizer
         │
         ▼
[ 3. Transcript Sanitization ] ─> Devanagari Unicode regex parser, noise hallucination filter, Hindi/Hinglish normalization
         │
         ▼
[ 4. Multi-LLM Extraction ]
    ├─ Priority 1 (Online): AWS Bedrock Converse API (Nova Lite / Claude 3.5)
    └─ Fallback 2 (Offline): Zero-failure deterministic SmartLocalExtractor
         │
         ▼
[ 5. Structured Intelligence Generation ]
    ├─ Executive Summary & Sentiment Analysis
    ├─ Speaker Identity Mapping (USR-101 -> Sarah Chen, USR-102 -> Alex Rivera)
    ├─ Action Items (with Interactive Checkboxes & Progress Bar)
    ├─ Key Decisions Made
    └─ Calendar Events (.ics generation)
         │
         ▼
[ 6. Persistence & Interactive UI ] ─> MongoDB updated -> Realtime Dashboard & Chat Studio
```

---

## 4. Deep-Dive: Core Technical Components & Algorithms

### 4.1 Hybrid Speech-to-Text (ASR) Pipeline
- **AWS Transcribe (Primary):**
  - Temporarily uploads audio to S3 bucket `meeting-ai-audio-transcribe-naishal` in Mumbai (`ap-south-1`).
  - Calls `StartTranscriptionJob` with `ShowSpeakerLabels=True` (native AWS diarization) and auto-language identification (`en-IN`, `hi-IN`).
  - Completes full transcription in **~5 to 10 seconds** and automatically deletes temporary S3 files.
- **Local Whisper (Fallback):**
  - If network is disconnected or S3 times out, `AudioService` catches the exception and immediately runs local Whisper.
  - **Greedy Decoding:** `beam_size = 1` for 3-4x faster CPU inference.
  - **FP32 Execution:** `fp16 = False` and `temperature = 0.0` for deterministic outputs without numerical underflow.

### 4.2 Speaker Diarization & Identity Resolution
- **Platform Identity Mapping:** Detects Zoom (`USR-101`, `USR-102`) and Google Meet (`P01`, `P02`) tags.
- **Dialogue Name Resolution:**
  - Matches self-introductions (*"I am Sarah Chen"*, *"Alex Rivera here"*, *"मेरा नाम रमेशा है"*).
  - Matches handoffs and greetings (*"Hi Alex, could you..."* $\to$ identifies Alex).
  - **Adjective Blacklist Filter:** Prevents Hindi colloquial adjectives (`बढ़िया`, `ठीक`, `अच्छा`, `व्यस्त`, `खुश`) from mistakenly being parsed as names.

### 4.3 Multi-Model Cloud & Offline LLM Intelligence
- **AWS Bedrock Client (`BedrockClient`):**
  - Uses the AWS Bedrock **Converse API** (`client.converse`) with thread-pool offloading (`asyncio.to_thread`) to avoid blocking FastAPI's async event loop.
  - Automatic exponential backoff retry via `tenacity`.
  - Configured for high-speed, cost-effective inference in Mumbai (`apac.amazon.nova-lite-v1:0` or Claude 3.5 Sonnet).
- **SmartLocalExtractor (Offline Fallback):**
  - Heuristic NLP engine running offline regex tokenizers and rule-based extraction for summaries, action items, and calendar dates (`जनवरी` ... `दिसंबर`).

### 4.4 Interactive Features Added for Production
- **Action Item Progress & Tracking:**
  - Live progress bar calculating completion percentage: `X of Y completed (Z%)`.
  - Visual status pills: `✓ Done` (green) and `⏳ Pending` (amber).
  - Optimistic UI updates with MongoDB PATCH updates (`/meetings/{id}/action-items/{item_id}`).
- **Interactive AI Chatbot:**
  - 1-click suggested question pills: *"When is the test or next deadline?"*, *"Who owns the action items?"*, *"What key decisions were finalized?"*.
  - Live query resolution against meeting dialogue history.

---

## 5. Database & Data Modeling

- **Database:** MongoDB (Async Motor driver).
- **Collections:**
  - `meetings`: Stores transcript, speaker turns, action items, calendar events, decisions, and analytics.
  - `users`: Stores user accounts and JWT authentication sessions.
- **Key Schemas (Pydantic):**
  - `MeetingPublic`: API projection stripping internal storage details.
  - `ActionItem`: `{ id, person, task, deadline, done: bool }`
  - `CalendarEvent`: `{ id, title, relative_time, days_from_now, category }`
  - `Sentiment`: `{ score: float, label: "positive"|"neutral"|"negative" }`

---

## 6. Testing & Quality Assurance

- **Test Suite:** **161 Automated Tests** using `pytest`.
- **Fast Execution:** Entire suite runs in **~28 seconds**.
- **Coverage:**
  - Audio magic-byte verification and format validation.
  - AWS Transcribe S3 upload, job polling, and speaker segment parsing.
  - AWS Bedrock JSON schema generation, prompt building, and error normalization.
  - Diarization clustering and Hindi/Hinglish phonetic correction.
  - Action item toggle persistence and calendar event extraction.
  - Meeting Q&A chatbot semantic context retrieval.

---

## 7. Viva Questions & Model Answers (Cheat Sheet)

### Q1: Why did you switch to AWS Bedrock and AWS Transcribe?
**Answer:**  
*"While local Whisper and free Gemini APIs worked well, they had inherent limitations: local Whisper is slow on CPU, and free Gemini APIs face severe 20 request/day rate limits. By integrating **AWS Transcribe in Mumbai (`ap-south-1`)**, transcription speed improved from 2 minutes to **under 8 seconds** with native Indian English/Hindi support. For intelligence, **AWS Bedrock (Amazon Nova Lite / Claude 3.5 Sonnet)** provides enterprise-grade token limits, ultra-fast response times, and consistent JSON compliance."*

### Q2: What happens if your AWS internet connection goes down during a meeting?
**Answer:**  
*"Our system features a **Resilient Hybrid Fallback Architecture**. Both `AudioService` and `ExtractionService` catch network and AWS exceptions gracefully. If internet is lost, the audio pipeline automatically activates local **OpenAI Whisper** and local **BIC Diarization**, while the intelligence layer falls back to **`SmartLocalExtractor`**. The application never crashes or displays a 502 Bad Gateway."*

### Q3: How does the system map Zoom tags like 'USR-101' to real human names?
**Answer:**  
*"The system uses a 4-tier identification pipeline: (1) Roster metadata if uploaded, (2) Self-introductions detected in dialogue (*'I am Sarah Chen'*), (3) Cross-speaker conversational handoffs (*'Alex, could you...'*), and (4) AWS Bedrock's few-shot speaker mapping prompt. We also built an adjective blacklist to prevent conversational words like 'बढ़िया' ('I am fine') from falsely registering as names."*

### Q4: How does the Action Item checklist work under the hood?
**Answer:**  
*"Action items are stored with a boolean `done` field in MongoDB. The frontend employs **Optimistic UI Updates**: when a user clicks the checkbox, the UI immediately flips the status, updates the progress bar, and strikes through the task. Concurrently, a background `PATCH /meetings/{id}/action-items/{item_id}` request updates MongoDB. If the request fails, the UI rolls back cleanly."*

### Q5: How do you extract calendar events and convert them to .ics files?
**Answer:**  
*"The NLP engine scans for modal announcements like 'exam on November 28th' or 'submission next Monday'. It extracts the title, category, and date offset, creating a structured `CalendarEvent`. Users can click '📅 Calendar (.ics)', which triggers our backend `ExportService` to generate standard RFC 5545 iCalendar files that import directly into Google Calendar, Outlook, and Apple Calendar."*

---

## 8. Technical Specifications Summary

| Component | Specification |
| :--- | :--- |
| **Backend Framework** | FastAPI (ASGI, Asyncio, Python 3.11) |
| **Frontend Framework** | React 18, TypeScript, Vite, TailwindCSS |
| **Primary Cloud ASR** | AWS Transcribe (Mumbai `ap-south-1`, Speaker Diarization) |
| **Fallback Local ASR** | OpenAI Whisper (`base`/`small`, greedy CPU decoding) |
| **Primary Cloud LLM** | AWS Bedrock (`apac.amazon.nova-lite-v1:0` / Claude 3.5 Sonnet) |
| **Fallback Offline NLP** | Deterministic Heuristic `SmartLocalExtractor` |
| **Cloud Storage** | Amazon S3 (`meeting-ai-audio-transcribe-naishal`) |
| **Primary Database** | MongoDB 7.0 (Motor AsyncIO Driver) |
| **Test Suite** | Pytest (**161 tests, 100% passing**) |
