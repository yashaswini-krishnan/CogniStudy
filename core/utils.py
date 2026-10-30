import os
import re
import json
import logging
from typing import Dict, Any, List
import pypdf
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


def extract_youtube_video_id(url_or_id: str) -> str | None:
    """Extract YouTube 11-character video ID from varied URL formats or raw ID."""
    if not url_or_id:
        return None
    url_or_id = url_or_id.strip()
    if len(url_or_id) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'[?&]v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return None


def fetch_youtube_transcript(video_url_or_id: str) -> str:
    """Fetch transcripts for a YouTube video using youtube-transcript-api."""
    video_id = extract_youtube_video_id(video_url_or_id)
    if not video_id:
        raise ValueError("Invalid YouTube URL or Video ID. Please check the link.")
    
    try:
        # First try direct get_transcript
        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        text_parts = [item.get('text', '') for item in transcript_data]
        full_transcript = " ".join(text_parts).strip()
        if not full_transcript:
            raise ValueError("Transcript was found but contains no readable text.")
        return full_transcript
    except Exception as e:
        # Try listing transcripts to get available language if english is not default
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
            data = transcript.fetch()
            return " ".join([item.get('text', '') for item in data]).strip()
        except Exception:
            raise ValueError(f"Could not retrieve YouTube transcript: {str(e)}")


def ocr_image_data(image_bytes: bytes, mime_type: str = "image/png") -> str | None:
    """
    Attempt OCR on raw image bytes using:
    1. Local pytesseract if installed and configured on the host.
    2. Google Gemini Multimodal Vision API if GEMINI_API_KEY is configured.
    Returns extracted text string, or None if OCR could not recognize text.
    """
    # 1. Attempt local Tesseract if available
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        tess_text = pytesseract.image_to_string(img)
        if tess_text and len(tess_text.strip()) > 5:
            logger.info("Successfully extracted text using local Tesseract OCR.")
            return tess_text.strip()
    except Exception:
        # Tesseract not installed or binary not on PATH; continue to Gemini Vision
        pass

    # 2. Attempt Gemini Multimodal Vision OCR
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            for model_name in ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest"]:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            "Transcribe all readable text from this scanned document page accurately. "
                            "Preserve headings, tables, equations, and paragraph structure verbatim without commentary.",
                            part
                        ]
                    )
                    if response.text and response.text.strip():
                        logger.info(f"Successfully extracted text using Gemini Vision OCR ({model_name}).")
                        return response.text.strip()
                except Exception as model_err:
                    logger.debug(f"Vision OCR failed with {model_name}: {model_err}")
                    continue
        except Exception as e:
            logger.warning(f"Gemini Vision OCR error: {e}")

    return None


def extract_text_from_pdf(file_obj) -> str:
    """
    Hybrid PDF extraction workflow:
    1. Attempts standard text extraction using pypdf page by page.
    2. Identifies pages with missing or insufficient text (< 50 characters).
    3. Applies OCR (Tesseract or Gemini Vision) to embedded scanned images on those pages.
    4. Combines extracted text in exact page order.
    5. Supports text-based, scanned, and mixed PDFs.
    """
    try:
        reader = pypdf.PdfReader(file_obj)
        pages_text = []

        for page_num, page in enumerate(reader.pages, 1):
            extracted = (page.extract_text() or '').strip()

            # If page text is sufficient (>= 50 chars), keep it without unnecessary OCR
            if len(extracted) >= 50:
                pages_text.append(extracted)
                continue

            # Page has insufficient or no text: check for scanned images
            ocr_text_parts = []
            if hasattr(page, 'images') and page.images:
                for img_obj in page.images:
                    try:
                        img_bytes = img_obj.data
                        img_ext = (img_obj.name or '').lower()
                        mime = "image/jpeg" if img_ext.endswith(('.jpg', '.jpeg')) else "image/png"

                        ocr_result = ocr_image_data(img_bytes, mime_type=mime)
                        if ocr_result:
                            ocr_text_parts.append(ocr_result)
                    except Exception as img_err:
                        logger.warning(f"Failed to process image on page {page_num}: {img_err}")
                        continue

            if ocr_text_parts:
                combined_page_text = "\n".join(ocr_text_parts).strip()
                if extracted:
                    combined_page_text = f"{extracted}\n{combined_page_text}"
                pages_text.append(combined_page_text)
            elif extracted:
                pages_text.append(extracted)
            else:
                logger.warning(f"Page {page_num} yielded no readable text and no OCR results.")

        full_text = "\n\n".join(pages_text).strip()
        if not full_text:
            raise ValueError(
                "The uploaded PDF does not contain readable text or OCR was unable to transcribe the scanned pages. "
                "Please ensure the document contains clear readable text or scanned pages."
            )
        return full_text
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Failed to process PDF file: {str(e)}")


def chunk_text(text: str, max_chunk_size: int = 15000, overlap: int = 500) -> List[str]:
    """
    Split text into coherent semantic chunks breaking at paragraph or sentence boundaries.
    Ensures long documents can be processed in manageable sections without cutting off sentences.
    """
    if not text or len(text) <= max_chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + max_chunk_size, text_len)
        if end < text_len:
            # Look for paragraph boundary first
            split_at = text.rfind('\n\n', start, end)
            if split_at == -1 or split_at <= start + (max_chunk_size // 2):
                # Look for single line break
                split_at = text.rfind('\n', start, end)
            if split_at == -1 or split_at <= start + (max_chunk_size // 2):
                # Look for sentence boundary
                split_at = text.rfind('. ', start, end)
                if split_at != -1:
                    split_at += 1  # Include period
            if split_at == -1 or split_at <= start + (max_chunk_size // 2):
                # Look for space between words
                split_at = text.rfind(' ', start, end)

            if split_at != -1 and split_at > start:
                end = split_at

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break
        start = max(end - overlap, end)

    return chunks


def get_summary_prompt_instructions(summary_level: str) -> str:
    """Return tailored pedagogical prompt guidelines for the selected summary depth."""
    level = (summary_level or 'medium').lower()
    if level == 'short':
        return """Generate a CONCISE, HIGH-IMPACT SHORT REVISION SUMMARY (150-250 words).
Structure strictly with:
### Quick Overview
A clear 2-3 sentence overview of the topic.
### Core Key Points
5 to 7 high-impact bullet points capturing the essential facts and mechanisms.
### Key Takeaway
The primary conclusion, core insight, or practical takeaway."""
    elif level == 'detailed':
        return """Generate EXHAUSTIVE, DETAILED ACADEMIC STUDY NOTES (700-1200 words).
Structure strictly with:
### Comprehensive Overview
In-depth introduction establishing context, objectives, and foundational importance.
### In-Depth Conceptual Breakdown
Detailed multi-paragraph sectional explanations of each major concept, mechanism, and component.
### Key Terminology & Definitions
Exhaustive glossary of specialized domain terms, core principles, and relationships.
### Analytical Insights & Practical Implications
Critical analysis, trade-offs, real-world examples, and implications.
### Comprehensive Review Checklist
Key checkpoints, revision questions, and core takeaways for exam mastery."""
    else:  # medium
        return """Generate a BALANCED, WELL-STRUCTURED STUDY GUIDE (350-550 words).
Structure strictly with:
### Executive Overview
Clear contextual overview of the topic and its significance.
### Key Concepts & Principles
Core theories, mechanisms, and conceptual framework with bullet explanations.
### Essential Terminology & Definitions
Key vocabulary terms and precise definitions.
### Practical Takeaways & Summary
Crucial conclusions and practical applications."""


def generate_fallback_study_content(content_text: str, title: str, summary_level: str = 'medium') -> Dict[str, Any]:
    """Offline heuristic fallback generator if Gemini API key is missing or quota exceeded."""
    cleaned = re.sub(r'\s+', ' ', content_text).strip()
    sentences = re.split(r'(?<=[.!?]) +', cleaned)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    level = (summary_level or 'medium').lower()

    if level == 'short':
        selected = sentences[:6] if len(sentences) >= 6 else sentences
        intro = selected[0] if selected else f"Study notes for {title}."
        bullets = "\n".join([f"- {s}" for s in selected[1:-1]]) if len(selected) > 2 else "- Core topic principles discussed in detail."
        conclusion = selected[-1] if len(selected) > 1 else "Essential concepts for revision."
        summary_text = f"### Quick Overview\n{intro}\n\n### Core Key Points\n{bullets}\n\n### Key Takeaway\n{conclusion}"

    elif level == 'detailed':
        selected = sentences[:18] if len(sentences) >= 18 else sentences
        intro = " ".join(selected[:3]) if len(selected) >= 3 else f"Detailed study material for {title}."
        body = "\n\n".join(selected[3:12]) if len(selected) >= 12 else "\n\n".join(selected[1:-2])
        terms = "\n".join([f"- **Term {i+1}:** {s}" for i, s in enumerate(selected[12:15])]) if len(selected) >= 15 else "- **Core Theory:** Central framework analyzed in the text."
        conclusion = " ".join(selected[-2:]) if len(selected) >= 2 else "Comprehensive review of the subject matter."
        summary_text = (
            f"### Comprehensive Overview\n{intro}\n\n"
            f"### In-Depth Conceptual Breakdown\n{body}\n\n"
            f"### Key Terminology & Definitions\n{terms}\n\n"
            f"### Analytical Insights & Implications\n{conclusion}\n\n"
            f"### Comprehensive Review Checklist\n- Review foundational definitions\n- Understand core mechanisms and workflows\n- Test recall using the assessment quiz below."
        )

    else:  # medium
        selected = sentences[:12] if len(sentences) >= 12 else sentences
        intro = " ".join(selected[:2]) if len(selected) >= 2 else f"Study guide on {title}."
        concepts = "\n".join([f"- {s}" for s in selected[2:8]]) if len(selected) >= 8 else "- Primary conceptual foundations."
        takeaway = selected[-1] if len(selected) > 1 else "Core revision takeaway."
        summary_text = (
            f"### Executive Overview\n{intro}\n\n"
            f"### Key Concepts & Principles\n{concepts}\n\n"
            f"### Practical Takeaways & Summary\n{takeaway}"
        )

    # Heuristic MCQ creation
    words = [w for w in re.findall(r'\b[A-Za-z]{5,}\b', cleaned) if w.lower() not in ['which', 'about', 'their', 'there', 'these', 'could', 'should', 'would']]
    unique_words = list(dict.fromkeys(words))[:10]

    mcqs = []
    if len(sentences) >= 2 and len(unique_words) >= 4:
        mcqs.append({
            "question": f"According to the material on '{title}', which concept is primarily discussed?",
            "options": [
                unique_words[0].capitalize(),
                unique_words[1].capitalize() if len(unique_words) > 1 else "Analysis",
                unique_words[2].capitalize() if len(unique_words) > 2 else "Methodology",
                unique_words[3].capitalize() if len(unique_words) > 3 else "Evaluation"
            ],
            "correct_answer": unique_words[0].capitalize(),
            "explanation": f"The term '{unique_words[0]}' is central to the core discussion of {title}."
        })
        if len(sentences) >= 4 and len(unique_words) >= 6:
            mcqs.append({
                "question": f"Which statement best aligns with the text: '{sentences[1][:100]}...'?",
                "options": [
                    "It presents a core foundational insight of the topic.",
                    "It contradicts the general premise.",
                    "It is completely unrelated.",
                    "None of the above."
                ],
                "correct_answer": "It presents a core foundational insight of the topic.",
                "explanation": "The text directly states this fact as part of the primary argument."
            })
    else:
        mcqs.append({
            "question": f"What is the primary topic of this study material?",
            "options": [title, "Unrelated Topic A", "General Discussion B", "Historical Overview C"],
            "correct_answer": title,
            "explanation": f"The material focuses squarely on {title}."
        })

    short_answers = [
        {
            "question": f"Explain the main objective or concept discussed in '{title}'.",
            "correct_answer": sentences[0] if sentences else f"The core concept of {title}.",
            "explanation": "Should describe the fundamental idea presented in the introductory section."
        },
        {
            "question": "What is one key takeaway or practical implication from this material?",
            "correct_answer": sentences[-1] if len(sentences) > 1 else "Practical application of the discussed concepts.",
            "explanation": "Should summarize the final takeaway or conclusion."
        }
    ]

    return {
        "summary": summary_text,
        "mcqs": mcqs,
        "short_answers": short_answers
    }


def generate_study_material_with_gemini(content_text: str, title: str, summary_level: str = 'medium') -> Dict[str, Any]:
    """
    Generate structured study summary, MCQs, and short answer questions using Google GenAI SDK.
    Supports selectable summary depth (short, medium, detailed).
    Features chunking for long documents to process comprehensive content without loss.
    Enforces strict JSON schema output and includes graceful offline fallback.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set. Using offline fallback generator.")
        return generate_fallback_study_content(content_text, title, summary_level=summary_level)

    summary_instructions = get_summary_prompt_instructions(summary_level)

    # Document length handling: If content is very long (> 18,000 characters),
    # process with a map-reduce chunking approach so the entire document is utilized.
    chunks = chunk_text(content_text, max_chunk_size=15000, overlap=400)
    
    if len(chunks) > 1:
        logger.info(f"Long document detected ({len(content_text)} chars). Processing with {len(chunks)} chunks.")
        # If multiple chunks, synthesize sectional excerpts
        analyzed_content = ""
        for i, chunk in enumerate(chunks[:6]):  # Handle up to ~90,000 chars across 6 chunks
            analyzed_content += f"\n--- SECTION {i+1} ---\n{chunk}\n"
    else:
        analyzed_content = content_text

    prompt = f"""You are an expert AI educator and academic tutor. Analyze the following study material titled "{title}" and generate comprehensive learning resources.

{summary_instructions}

Return ONLY a valid JSON object with the following exact structure:
{{
  "summary": "The structured summary in markdown adhering strictly to the headings and depth requested above.",
  "mcqs": [
    {{
      "question": "The question text",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Exact text matching one of the options",
      "explanation": "Detailed explanation of why this answer is correct"
    }}
  ],
  "short_answers": [
    {{
      "question": "The conceptual short-answer question",
      "correct_answer": "A model concise answer explaining the key concept",
      "explanation": "Evaluation criteria or elaboration"
    }}
  ]
}}

Requirements:
1. Preserve all important technical terminology, formulas, and domain keywords.
2. Base all questions and summary strictly on the provided content. Do not invent details not supported by the source.
3. Generate 4 to 6 challenging Multiple Choice Questions (MCQs) covering key ideas across the material. Each MCQ must have exactly 4 options, and 'correct_answer' must exactly match one of the items in 'options'.
4. Generate 2 to 4 Short Answer Questions testing deeper conceptual understanding.

Study Material Title: {title}
Content:
\"\"\"
{analyzed_content}
\"\"\"
"""

    models_to_try = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest",
    ]

    client = genai.Client(api_key=api_key)
    last_error = None

    for model_name in models_to_try:
        try:
            logger.info(f"Attempting content generation with model: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                )
            )

            raw_text = response.text.strip()
            # Clean possible markdown fence if model wrapped it
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            parsed = json.loads(raw_text)
            
            # Validate required keys
            if "summary" in parsed and "mcqs" in parsed and "short_answers" in parsed:
                # Sanitize MCQs
                sanitized_mcqs = []
                for item in parsed.get("mcqs", []):
                    opts = item.get("options", [])
                    if isinstance(opts, list) and len(opts) >= 2:
                        sanitized_mcqs.append({
                            "question": str(item.get("question", "")).strip(),
                            "options": [str(o).strip() for o in opts],
                            "correct_answer": str(item.get("correct_answer", "")).strip(),
                            "explanation": str(item.get("explanation", "")).strip()
                        })
                parsed["mcqs"] = sanitized_mcqs

                # Sanitize Short Answers
                sanitized_short = []
                for item in parsed.get("short_answers", []):
                    sanitized_short.append({
                        "question": str(item.get("question", "")).strip(),
                        "correct_answer": str(item.get("correct_answer", "")).strip(),
                        "explanation": str(item.get("explanation", "")).strip()
                    })
                parsed["short_answers"] = sanitized_short

                return parsed

        except Exception as e:
            logger.warning(f"Generation failed with {model_name}: {e}")
            last_error = e
            continue

    logger.error(f"All Gemini models failed. Error: {last_error}. Using fallback generator.")
    fallback = generate_fallback_study_content(content_text, title, summary_level=summary_level)
    fallback["summary"] = f"[Note: AI generation fell back to offline mode due to: {last_error}]\n\n" + fallback["summary"]
    return fallback


def evaluate_short_answer(user_resp: str, correct_ans: str, explanation: str) -> tuple[bool, str]:
    """Evaluate short answer by checking semantic overlap of key concepts."""
    cleaned_user = user_resp.strip().lower()
    cleaned_correct = correct_ans.strip().lower()

    if not cleaned_user:
        return False, f"No answer provided. Expected: {correct_ans}. {explanation}"

    # Extract non-stop words
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'it', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'that', 'this'}
    correct_tokens = [w for w in re.findall(r'\b\w+\b', cleaned_correct) if w not in stop_words and len(w) > 2]
    user_tokens = set(re.findall(r'\b\w+\b', cleaned_user))

    if not correct_tokens:
        is_correct = (cleaned_user in cleaned_correct) or (cleaned_correct in cleaned_user)
        feedback = "Great attempt!" if is_correct else f"Expected: {correct_ans}. {explanation}"
        return is_correct, feedback

    matched = sum(1 for t in correct_tokens if t in user_tokens)
    overlap_ratio = matched / len(correct_tokens)

    # If at least 35% key terminology matched or user response contains key phrasing
    if overlap_ratio >= 0.35 or cleaned_correct in cleaned_user:
        return True, f"Good explanation! Covers key concepts ({int(overlap_ratio*100)}% match). {explanation}"
    else:
        return False, f"Needs improvement. Key expected points: {correct_ans}. {explanation}"
