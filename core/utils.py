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


def extract_text_from_pdf(file_obj) -> str:
    """Extract all readable text from an uploaded PDF file."""
    try:
        reader = pypdf.PdfReader(file_obj)
        pages_text = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            if text.strip():
                pages_text.append(text.strip())
        
        full_text = "\n\n".join(pages_text).strip()
        if not full_text:
            raise ValueError("The uploaded PDF does not contain any readable text or is image-only/scanned.")
        return full_text
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Failed to process PDF file: {str(e)}")


def generate_fallback_study_content(content_text: str, title: str) -> Dict[str, Any]:
    """Offline heuristic fallback generator if Gemini API key is missing or quota exceeded."""
    cleaned = re.sub(r'\s+', ' ', content_text).strip()
    sentences = re.split(r'(?<=[.!?]) +', cleaned)
    selected_sentences = sentences[:12] if len(sentences) >= 12 else sentences
    summary_text = " ".join(selected_sentences)
    if not summary_text:
        summary_text = f"Study notes for {title}. Summary generated from source material."

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


def generate_study_material_with_gemini(content_text: str, title: str) -> Dict[str, Any]:
    """
    Generate structured study summary, MCQs, and short answer questions using Google GenAI SDK.
    Uses the gemini-3.6-flash model with fallback if needed.
    Strict JSON output is enforced.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set. Using offline fallback generator.")
        return generate_fallback_study_content(content_text, title)

    # Prompt requirement:
    # return JSON with keys: "summary" (string),
    # "mcqs" (array with question, options array of 4, correct_answer, explanation),
    # "short_answers" (array with question, correct_answer, explanation)
    prompt = f"""You are an expert AI educator and tutor. Analyze the following study material titled "{title}" and generate comprehensive learning resources.

Return ONLY a valid JSON object with the following exact structure:
{{
  "summary": "A comprehensive, clear, well-organized summary highlighting main concepts, key takeaways, and definitions.",
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
1. Provide a detailed summary with bullet-point-friendly clear phrasing.
2. Generate 4 to 6 challenging Multiple Choice Questions (MCQs). Each MCQ must have exactly 4 options, and 'correct_answer' must exactly match one of the items in 'options'.
3. Generate 2 to 4 Short Answer Questions testing deeper conceptual understanding.
4. Base all questions and summary strictly on the provided content.

Study Material Title: {title}
Content:
\"\"\"
{content_text[:40000]}
\"\"\"
"""

    models_to_try = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash"
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
    fallback = generate_fallback_study_content(content_text, title)
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
