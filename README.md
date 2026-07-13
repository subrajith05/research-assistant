# DocuMind — AI Multi-Agent Research Assistant

DocuMind is a full-stack AI research assistant that lets you upload PDF documents and ask questions about them. A multi-agent LangGraph pipeline handles query understanding, retrieval, summarization, validation, and response generation — all powered by Gemini.

---

## Features

- **JWT Authentication** — secure signup and login
- **PDF Upload & Management** — upload, list, and delete documents
- **Multi-Agent RAG Pipeline** — 5 specialized agents with conditional routing and retry logic
- **Cross-Document Retrieval** — search across all uploaded documents simultaneously
- **Conversation Memory** — Redis-backed session history with query disambiguation
- **Agent Execution Logging** — every agent step logged to PostgreSQL
- **Error Handling** — retries, graceful fallbacks, and user-friendly error messages

---

## Tech Stack

**Backend**
- FastAPI + SQLAlchemy (async) + PostgreSQL (Neon)
- LangChain + LangGraph (multi-agent orchestration)
- ChromaDB Cloud (vector store)
- Redis / Upstash (conversation memory)
- Gemini (`gemini-3.1-flash-lite` + `gemini-embedding-001`)

**Frontend**
- React + Vite + Tailwind CSS
- Axios + React Router

**Deployment**
- Backend → Render
- Frontend → Vercel

---

## Architecture

```
User → FastAPI → LangGraph Pipeline
                 ├── Query Analyzer     (intent classification + query rewriting)
                 ├── Retrieval Agent    (ChromaDB semantic search)
                 ├── Summarization Agent (context compression)
                 ├── Validation Agent   (relevance check + retry routing)
                 └── Final Response Agent (answer generation)
```

---

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL (Neon recommended)
- Redis (Upstash recommended)
- ChromaDB Cloud account
- Gemini API key

### Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env    # fill in your credentials
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env    # set VITE_API_URL
npm run dev
```

---

## Environment Variables

### Backend `.env`

```
APP_NAME=DocuMind
APP_VERSION=0.1.0
DEBUG=True

DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=rediss://...
GEMINI_API_KEY=...
SECRET_KEY=...
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

CHROMA_API_KEY=...
CHROMA_TENANT=...
CHROMA_DATABASE=documind

ALLOWED_ORIGINS=http://localhost:5173
```

### Frontend `.env`

```
VITE_API_URL=http://localhost:8000
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/signup` | Register a new user |
| POST | `/auth/login` | Login and receive JWT |
| POST | `/documents/upload` | Upload a PDF |
| GET | `/documents/` | List uploaded documents |
| DELETE | `/documents/{id}` | Delete a document |
| POST | `/chat/` | Send a query |
| GET | `/chat/history/{session_id}` | Get chat history |
| GET | `/health` | Health check |
