# Project: CDSS Scheduling Chatbot

This is an intelligent **Clinical Decision Support System (CDSS)** chatbot for appointment scheduling. It supports **voice and text** input and handles **both patient and doctor roles**: patients can book/cancel/reschedule, while doctors can manage availability and appointments in real time.

## Demo
![Chatbot Demo](images/demo.gif)

---

## Introduction
Scheduling in clinical settings is tricky: multiple doctors, limited time slots, and fast‑changing availability. This project delivers a **CDSS‑powered scheduling assistant** that streamlines the process with a conversational interface. The bot:

- Understands **natural language in voice and text**.
- Distinguishes **patient vs. doctor** tasks, enforcing role‑appropriate actions.
- Books, reschedules, and cancels appointments while preventing double bookings.
- Surfaces **upcoming availability** and handles relative time phrases (e.g., “tomorrow morning”).

The system is **scalable and user‑centered**, suitable for clinics with multiple doctors and patients.

---

## Features
- **Voice + Text** interaction (microphone input for real‑time conversation; text chat supported as well).
- **Multi‑role workflows**: patient and doctor actions in one chatbot.
- **Availability management**: add/remove slots, recurring patterns (weekly), and ad‑hoc events.
- **Conflict & constraints**: checks before booking; prevents overbooking.
- **Timezone‑aware** display of suggested times.
- **Reschedule & cancel** flows with confirmations and guardrails.
- **Auditability**: all actions logged for traceability.

---

## Installation

### 1) Prerequisites
- A Postgres/Supabase database (recommended)
- An LLM/Realtime‑voice API key (e.g., OpenAI)


### 2) Configure environment
Create a `.env` from the example and fill the values to match your setup:

**`.env.example` (sample keys):**
```env
# LLM / Voice
OPENAI_API_KEY

# Database (Supabase/Postgres)
SUPABASE_URL
SUPABASE_KEY

# Auth
JWT_SECRET
JWT_ALGORITHM
```

### 4) Run locally 
1. Backend (FastAPI)  
```bash
cd backend
uvicorn main:app --reload
```
2. Frontend (Next.js)  
```bash
cd frontend
npm run dev
```
3. Launch  
```bash
Open [http://localhost:3000]
```
---

## Project Structure
```
CDSS_project/
│
├── backend/
│   ├── chatbot_services.py      # Main task logic & LLM dispatch
│   ├── llm_client.py            # OpenAI LLM API wrapper
│   ├── main.py                  # FastAPI entry point, routing
│   └── supabase_utils.py        # Supabase DB operations
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── chat/
│       │   │   ├── chat.tsx             # Text-based chat interface
│       │   │   └── voice-capture.tsx    # Voice-based realtime chat interface
│       │   └── login_ui/, icons/, etc.  # UI components
│       └── app/, auth/, etc.            # App logic and routing
│
├── supabase/
│   ├── schema.sql      # supbase DB related queries, functions, triggers
```

---
