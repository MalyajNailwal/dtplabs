# Document Summarizer API

A Django REST API that accepts documents (PDF, DOCX, TXT), extracts text, sends content to an LLM via OpenRouter, and returns a structured summary.

## Features

- **File Upload**: Support for PDF, DOCX, and TXT files
- **Text Extraction**: Automatic text extraction using PyPDF2, python-docx
- **LLM Integration**: Uses OpenRouter API with free model selection
- **Demo UI**: Minimal browser page at `/` that drives the same public API (upload, live status polling, summary render)
- **Structured Response**: Returns title, summary, keywords, language, and word count
- **Async Processing**: Celery background tasks, with automatic synchronous fallback if Redis is unavailable
- **Retry Logic**: Celery task retries (3 attempts, 10s backoff) plus request timeouts on LLM calls
- **Configurable**: Model, timeout, token limit and upload cap all driven by env vars
- **Docker Support**: Dockerfile + docker-compose (web, redis, celery)
- **Unit Tests**: Comprehensive test coverage (14 tests covering models, APIs, extraction, LLM utils, demo page)

## Project Structure

```
dtplabs/
├── config/                  # Django project settings
│   ├── settings.py
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py
├── documents/               # Main app
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── tasks.py
│   ├── utils.py
│   ├── llm_utils.py
│   ├── exceptions.py
│   ├── tests.py
│   └── templates/
│       └── documents/
│           └── index.html   # Minimal demo UI
├── requirements.txt
├── .env.example
├── .gitignore
├── postman_collection.json   # Importable API collection
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Setup Instructions

### Prerequisites

- Python 3.8+
- Redis (for Celery)
- OpenRouter API key (free tier available)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd dtplabs
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your settings
```

5. Run migrations:
```bash
python manage.py migrate
```

6. Start Redis server:
```bash
redis-server
```

7. Start Celery worker:
```bash
celery -A config worker -l info
```

8. Run development server:
```bash
python manage.py runserver
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Debug mode | `True` |
| `SECRET_KEY` | Django secret key | `django-insecure-dev-key` |
| `ALLOWED_HOSTS` | Allowed hosts | `localhost,127.0.0.1` |
| `OPENROUTER_API_KEY` | OpenRouter API key | - |
| `OPENROUTER_BASE_URL` | OpenRouter API base URL | `https://openrouter.ai/api/v1` |
| `DEFAULT_LLM_MODEL` | Model used when the request omits `model` | `openai/gpt-oss-20b:free` |
| `LLM_REQUEST_TIMEOUT` | LLM HTTP timeout (seconds) | `60` |
| `LLM_MAX_TOKENS` | Max tokens in the LLM response | `2000` |
| `LLM_REASONING_EFFORT` | Reasoning budget for reasoning models (`low`/`medium`/`high`) | `low` |
| `MAX_UPLOAD_SIZE` | Max upload size (bytes) | `10485760` (10MB) |
| `CELERY_BROKER_URL` | Redis broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Redis result backend | `redis://localhost:6379/0` |

## Demo UI

A single-page demo client is served at the project root:

```
http://localhost:8000/
```

It is not part of the REST API — it is a thin browser client that calls the same
public endpoints (`GET /api/models/free/`, `POST /api/documents/upload/`,
`GET /api/documents/{id}/status/`, `GET /api/documents/{id}/`), so the whole flow
can be demonstrated without Postman or curl:

1. Pick a `.pdf`, `.docx` or `.txt` file (max size comes from `MAX_UPLOAD_SIZE`).
2. Optionally pick a model — the dropdown is populated from the live free-model
   list; leaving it on **Default** uses `DEFAULT_LLM_MODEL`.
3. Submit — the page uploads, then polls the status endpoint every 2s and renders
   the title, summary, keywords, language, word count and processing time.
4. Validation and processing errors (bad type, empty document, LLM failure) are
   shown inline exactly as the API returns them.

## API Endpoints

### 1. Get Free Models
```http
GET /api/models/free/
```

Response:
```json
{
  "free_models": [
    {"id": "openai/gpt-oss-20b:free", "name": "OpenAI: gpt-oss-20b"},
    {"id": "nvidia/nemotron-nano-9b-v2:free", "name": "NVIDIA: Nemotron Nano 9B V2"}
  ],
  "count": 2
}
```

### 2. Upload Document
```http
POST /api/documents/upload/
Content-Type: multipart/form-data

file: <file>
model: openai/gpt-oss-20b:free
```

Response:
```json
{
  "message": "Document uploaded successfully. Processing started.",
  "document_id": "uuid",
  "status": "pending"
}
```

### 3. List Documents
```http
GET /api/documents/
```

Response:
```json
{
  "count": 1,
  "results": [
    {
      "id": "uuid",
      "filename": "document.pdf",
      "file_type": "pdf",
      "file_size": 1024,
      "model_used": "openai/gpt-oss-20b:free",
      "status": "completed",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### 4. Get Document Detail
```http
GET /api/documents/{id}/
```

Response:
```json
{
  "id": "uuid",
  "filename": "document.pdf",
  "file_type": "pdf",
  "extracted_text": "Document content...",
  "status": "completed",
  "llm_response": {
    "title": "Document Title",
    "summary": "Document summary...",
    "keywords": ["keyword1", "keyword2"],
    "language": "English",
    "word_count": 500,
    "processing_time": 2.5
  }
}
```

### 5. Check Document Status
```http
GET /api/documents/{id}/status/
```

Response:
```json
{
  "id": "uuid",
  "filename": "document.pdf",
  "status": "processing",
  "error_message": null
}
```

## Usage Examples

### Using curl

```bash
# Get free models
curl http://localhost:8000/api/models/free/

# Upload document
curl -X POST http://localhost:8000/api/documents/upload/ \
  -F "file=@document.pdf" \
  -F "model=openai/gpt-oss-20b:free"

# List documents
curl http://localhost:8000/api/documents/

# Get document detail
curl http://localhost:8000/api/documents/{uuid}/
```

### Using Python requests

```python
import requests

# Upload document
url = "http://localhost:8000/api/documents/upload/"
files = {"file": open("document.pdf", "rb")}
data = {"model": "openai/gpt-oss-20b:free"}
response = requests.post(url, files=files, data=data)
print(response.json())
```

## Postman Collection

Import `postman_collection.json` into Postman. It contains all 5 endpoints with
example responses (success and error cases).

Collection variables:

| Variable | Purpose |
|----------|---------|
| `base_url` | API root, defaults to `http://localhost:8000` |
| `document_id` | Auto-filled by the **Upload Document** test script, so the detail/status requests work without copy-pasting an id |
| `model` | Model sent with the upload request |

Suggested run order: **1. List Free Models → 2. Upload Document → 5. Check
Document Status → 4. Get Document Detail**. For the upload request, pick a local
file for the `file` form-data key before sending.

## Docker Setup

Create the env file first (Compose reads `.env`, which is not committed), then bring
the stack up:

```bash
cp .env.example .env      # Windows: copy .env.example .env
# add your OPENROUTER_API_KEY to .env
docker compose up --build
```

This starts:
- Django app on port 8000 (migrations run automatically on boot)
- Redis on port 6379
- Celery worker

Inside Compose the broker URLs are overridden to `redis://redis:6379/0`, so the
`localhost` values in `.env` only apply when you run the app natively.

## Running Tests

```bash
python manage.py test documents
```

## License

MIT
