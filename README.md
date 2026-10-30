# CogniStudy – AI-Powered Study Companion & Assessment Engine

> A full-stack Django web application that transforms PDFs, lecture notes, and YouTube videos into structured study notes and interactive quizzes using Google Gemini AI.

---

## Features

| Feature | Description |
|---|---|
| **Multi-source ingestion** | Upload a PDF, paste raw text/notes, or provide a YouTube URL with captions |
| **AI-powered summarization** | Google Gemini generates structured study notes with headings, key concepts, and takeaways |
| **3 summary depth levels** | Short (quick overview), Medium (balanced), Detailed (exhaustive notes) |
| **OCR for scanned PDFs** | Hybrid pipeline: pypdf text extraction → Gemini Vision OCR fallback for image-based pages |
| **AI quiz generation** | Auto-generates MCQ and short-answer questions directly from your material |
| **AI short-answer grading** | Gemini evaluates open-ended responses and provides detailed feedback |
| **Performance tracking** | Every quiz attempt is logged with a score, timestamp and full answer breakdown |
| **User authentication** | Registration, login, logout with Django's built-in auth system |
| **Data isolation** | Every user sees only their own materials, quizzes, and results — enforced at the query level |
| **Paginated dashboard** | Search, filter by source type, and paginate through your materials |
| **Markdown rendering** | AI summaries are rendered as formatted markdown in the browser |
| **Drag-and-drop upload** | PDF upload zone supports drag-and-drop in addition to click-to-browse |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, Django 5.1 |
| Database | MySQL 8.0 (via PyMySQL) |
| AI / LLM | Google Gemini AI (`google-genai` SDK) |
| PDF parsing | pypdf + Gemini Vision OCR (fallback) |
| YouTube | youtube-transcript-api |
| Frontend | Bootstrap 5.3, Bootstrap Icons, Plus Jakarta Sans |
| Markdown | marked.js + DOMPurify (client-side rendering) |
| Static files | WhiteNoise (production serving with compression) |
| Environment | python-dotenv (.env file loading) |

---

## Project Structure

```
CogniStudy/
├── cognistudy_project/     # Django project configuration
│   ├── settings.py         # All settings, env-driven
│   ├── urls.py             # Root URL config
│   └── wsgi.py
├── core/                   # Main Django app
│   ├── models.py           # StudyMaterial, Quiz, Question, UserAttempt, UserAnswer
│   ├── views.py            # All views (landing, dashboard, upload, quiz, results, auth, CRUD)
│   ├── forms.py            # Upload, update, register, login forms
│   ├── utils.py            # PDF extraction, OCR, YouTube, Gemini AI, chunking
│   ├── urls.py             # App URL patterns
│   └── tests.py            # 26 automated tests
├── templates/
│   ├── base.html           # Shared layout, navbar, CDN scripts
│   └── core/
│       ├── landing.html    # Public landing page
│       ├── dashboard.html  # Authenticated materials dashboard
│       ├── upload.html     # Material creation form
│       ├── material_detail.html
│       ├── material_edit.html
│       ├── quiz.html
│       ├── result.html
│       ├── login.html
│       └── register.html
├── static/                 # Static assets (CSS, JS, images)
├── logs/                   # Runtime log files (git-ignored)
├── .env                    # Local secrets — NEVER commit (git-ignored)
├── .env.example            # Template for required env variables
├── requirements.txt        # Direct Python dependencies
└── manage.py
```

---

## Getting Started (Local Development)

### Prerequisites

- Python 3.10+
- MySQL 8.0 running locally
- A Google Gemini API key (free at [aistudio.google.com](https://aistudio.google.com/apikey))

### 1. Clone the repository

```bash
git clone https://github.com/your-username/CogniStudy.git
cd CogniStudy
```

### 2. Create a virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```env
DEBUG=True
SECRET_KEY=your-strong-secret-key-here
ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=cognistudy_db
DB_USER=root
DB_PASSWORD=your-mysql-password
DB_HOST=127.0.0.1
DB_PORT=3306

GEMINI_API_KEY=your-gemini-api-key
```

### 5. Create the database

```sql
CREATE DATABASE cognistudy_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 6. Apply migrations

```bash
python manage.py migrate
```

### 7. Run the development server

```bash
python manage.py runserver
```

Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## Running Tests

```bash
python manage.py test core
```

26 tests covering authentication, data isolation, CRUD, PDF extraction, OCR, chunking, summarization, quiz flow, and result rendering.

---

## Deployment (Production Checklist)

Before deploying to a public host (Railway, Render, fly.io, etc.):

| Step | Action |
|---|---|
| `SECRET_KEY` | Set a strong, unique key via environment variable |
| `DEBUG` | Set to `False` |
| `ALLOWED_HOSTS` | Set to your domain(s), e.g. `myapp.railway.app` |
| `DB_PASSWORD` | Use the host's managed database credentials |
| `GEMINI_API_KEY` | Set as a secret environment variable on the platform |
| Static files | Run `python manage.py collectstatic` before deploy |
| HTTPS | WhiteNoise + `SECURE_SSL_REDIRECT=True` is already configured when `DEBUG=False` |

> All production security settings (HSTS, secure cookies, SSL redirect, content-type sniffing prevention) activate **automatically** when `DEBUG=False`. See `settings.py` for details.

---

## Security

- All views require authentication (`@login_required`) except the landing page, login, and register pages
- Every database query is scoped to `request.user` — URL manipulation cannot access another user's data
- CSRF protection is enabled on all state-changing forms
- Passwords are hashed using Django's default PBKDF2 algorithm
- PDF uploads are validated for file type and capped at 15 MB
- Secrets are loaded exclusively from environment variables — no hardcoded credentials

---

## License

MIT License — free to use, modify, and distribute.
