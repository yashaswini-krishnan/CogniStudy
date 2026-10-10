# Cognistudy - AI Powered Study Companion & Quiz Generator

Cognistudy is a full-featured Django web application that transforms lecture notes, PDF documents, and YouTube videos into structured study notes and interactive quizzes powered by Google Gemini AI.

---

## 🚀 Key Features

1. **Multi-Source Ingestion (`/upload/`)**:
   - **Raw Text**: Paste lecture notes, markdown, or textbooks directly.
   - **PDF Upload**: Automatic text extraction using `pypdf`.
   - **YouTube Video URLs**: Automatic transcript retrieval using `youtube-transcript-api`.

2. **AI Study Material Generation**:
   - Integrated with Google GenAI SDK (`google-genai`) using `gemini-3.6-flash`.
   - Strict JSON response formatting generating:
     - Comprehensive, structured study summary.
     - 4-choice Multiple Choice Questions (MCQs) with correct answers and explanations.
     - Conceptual Short Answer Questions with model answers and evaluation criteria.
   - Built-in intelligent offline fallback mode to ensure uninterrupted operation even when the API key is missing or quota is exceeded.

3. **Dashboard (`/`)**:
   - Grid view of all uploaded study materials.
   - Source type indicators (`PDF`, `Text`, `YouTube`).
   - Scrollable summary boxes.
   - Fast "Take Quiz" action and delete confirmation modals.

4. **Interactive Quiz & Results Engine (`/quiz/<id>/`, `/quiz/result/<id>/`)**:
   - Dynamic interactive quiz interface.
   - Automated evaluation of MCQs and semantic grading of short answers.
   - Detailed result breakdown featuring score percentage, correct/incorrect badges, explanations, and AI feedback.

---

## 🛠 Tech Stack

- **Backend**: Python 3.10+, Django 5.1+
- **Database**: MySQL 8.0 (configured with PyMySQL)
- **AI / LLM**: Google GenAI SDK (`google-genai`), `gemini-3.6-flash`
- **Parsing Libraries**: `pypdf`, `youtube-transcript-api`
- **Frontend**: Bootstrap 5, Bootstrap Icons, Google Fonts

---

## ⚙️ Configuration & Environment (`.env`)

In the project root, edit `.env`:

```env
DEBUG=True
SECRET_KEY=django-insecure-cognistudy-super-secret-key-2026-prod
DB_NAME=cognistudy_db
DB_USER=root
DB_PASSWORD=Saravanavel@219
DB_HOST=127.0.0.1
DB_PORT=3306
GEMINI_API_KEY=your_gemini_api_key_here
```

### How to get a Gemini API Key:
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Click **Create API Key**.
3. Paste the key into `GEMINI_API_KEY` in `.env`.

---

## 🏃 Running the Application

1. **Apply Migrations** (already applied):
   ```powershell
   python manage.py migrate
   ```

2. **Run the Development Server**:
   ```powershell
   python manage.py runserver
   ```

3. **Open in Browser**:
   Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

4. **Run Automated Tests**:
   ```powershell
   python manage.py test core
   ```
