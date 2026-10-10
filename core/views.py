import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseNotAllowed

from .models import StudyMaterial, Quiz, Question, UserAttempt, UserAnswer
from .forms import StudyMaterialUploadForm
from .utils import (
    extract_text_from_pdf,
    fetch_youtube_transcript,
    generate_study_material_with_gemini,
    evaluate_short_answer
)

logger = logging.getLogger(__name__)


def dashboard_view(request):
    """Dashboard view listing all uploaded study materials in a card grid."""
    materials = StudyMaterial.objects.prefetch_related('quizzes').all().order_by('-created_at')
    context = {
        'materials': materials,
    }
    return render(request, 'core/dashboard.html', context)


def upload_view(request):
    """
    Upload view to handle Text, PDF, or YouTube inputs.
    Extracts content, queries Gemini AI for summary and quiz questions,
    and saves records in MySQL.
    """
    if request.method == 'POST':
        form = StudyMaterialUploadForm(request.POST, request.FILES)
        if form.is_valid():
            title = form.cleaned_data['title'].strip()
            source_type = form.cleaned_data['source_type']
            raw_content = ""

            try:
                # 1. Extract content based on source_type
                if source_type == 'Text':
                    raw_content = form.cleaned_data['text_content'].strip()
                elif source_type == 'PDF':
                    pdf_file = form.cleaned_data['pdf_file']
                    raw_content = extract_text_from_pdf(pdf_file)
                elif source_type == 'YouTube':
                    yt_url = form.cleaned_data['youtube_url'].strip()
                    raw_content = fetch_youtube_transcript(yt_url)

                if not raw_content:
                    messages.error(request, "Failed to extract readable content from the provided source.")
                    return render(request, 'core/upload.html', {'form': form})

                # 2. Generate summary, MCQs, and Short Answer questions using Gemini AI
                ai_data = generate_study_material_with_gemini(raw_content, title)
                summary = ai_data.get('summary', '').strip()
                mcqs = ai_data.get('mcqs', [])
                short_answers = ai_data.get('short_answers', [])

                if not mcqs and not short_answers:
                    messages.error(request, "Unable to generate quiz questions from this material. Please try again.")
                    return render(request, 'core/upload.html', {'form': form})

                # 3. Save StudyMaterial, Quiz, and Questions in a database transaction
                with transaction.atomic():
                    material = StudyMaterial.objects.create(
                        user=request.user if request.user.is_authenticated else None,
                        title=title,
                        source_type=source_type,
                        content=raw_content,
                        summary=summary
                    )

                    quiz = Quiz.objects.create(
                        material=material,
                        title=f"{title} - Assessment Quiz"
                    )

                    for item in mcqs:
                        Question.objects.create(
                            quiz=quiz,
                            question_text=item.get('question', ''),
                            question_type='MCQ',
                            options=item.get('options', []),
                            correct_answer=item.get('correct_answer', ''),
                            explanation=item.get('explanation', '')
                        )

                    for item in short_answers:
                        Question.objects.create(
                            quiz=quiz,
                            question_text=item.get('question', ''),
                            question_type='Short',
                            options=None,
                            correct_answer=item.get('correct_answer', ''),
                            explanation=item.get('explanation', '')
                        )

                messages.success(request, f"Successfully processed '{title}'! Quiz generated with {quiz.questions.count()} questions.")
                return redirect('dashboard')

            except Exception as e:
                logger.exception("Error processing study material upload:")
                messages.error(request, f"Processing Error: {str(e)}")
                return render(request, 'core/upload.html', {'form': form})
    else:
        form = StudyMaterialUploadForm()

    return render(request, 'core/upload.html', {'form': form})


def delete_material_view(request, pk):
    """Delete a study material and its associated quizzes/questions."""
    if request.method == 'POST':
        material = get_object_or_404(StudyMaterial, pk=pk)
        material_title = material.title
        material.delete()
        messages.success(request, f"Study Material '{material_title}' was successfully deleted.")
        return redirect('dashboard')
    return HttpResponseNotAllowed(['POST'])


def quiz_view(request, pk):
    """
    Renders quiz questions and evaluates user answers on submission.
    Calculates percentage score and creates UserAttempt / UserAnswer records.
    """
    quiz = get_object_or_404(Quiz.objects.select_related('material'), pk=pk)
    questions = list(quiz.questions.all())

    if not questions:
        messages.warning(request, "This quiz has no questions available.")
        return redirect('dashboard')

    if request.method == 'POST':
        total_questions = len(questions)
        correct_count = 0
        answers_to_create = []

        with transaction.atomic():
            # Create attempt placeholder
            attempt = UserAttempt.objects.create(
                user=request.user if request.user.is_authenticated else None,
                quiz=quiz,
                score=0.0
            )

            for question in questions:
                field_name = f"question_{question.id}"
                user_response = request.POST.get(field_name, '').strip()

                if question.question_type == 'MCQ':
                    is_correct = (user_response.lower() == question.correct_answer.strip().lower())
                    if is_correct:
                        correct_count += 1
                        feedback = f"Correct! {question.explanation}"
                    else:
                        feedback = f"Incorrect. Correct answer: '{question.correct_answer}'. {question.explanation}"
                else:
                    # Short answer question
                    is_correct, feedback = evaluate_short_answer(
                        user_resp=user_response,
                        correct_ans=question.correct_answer,
                        explanation=question.explanation
                    )
                    if is_correct:
                        correct_count += 1

                answers_to_create.append(UserAnswer(
                    attempt=attempt,
                    question=question,
                    user_response=user_response if user_response else "(No answer)",
                    is_correct=is_correct,
                    ai_feedback=feedback
                ))

            UserAnswer.objects.bulk_create(answers_to_create)

            # Calculate score percentage
            score_percentage = round((correct_count / total_questions) * 100.0, 1)
            attempt.score = score_percentage
            attempt.save(update_fields=['score'])

        return redirect('quiz_result', attempt_id=attempt.id)

    return render(request, 'core/quiz.html', {
        'quiz': quiz,
        'material': quiz.material,
        'questions': questions,
    })


def quiz_result_view(request, attempt_id):
    """Displays detailed breakdown of a completed quiz attempt."""
    attempt = get_object_or_404(
        UserAttempt.objects.select_related('quiz', 'quiz__material').prefetch_related('answers__question'),
        pk=attempt_id
    )
    answers = attempt.answers.select_related('question').all()
    total_questions = answers.count()
    correct_count = answers.filter(is_correct=True).count()

    return render(request, 'core/result.html', {
        'attempt': attempt,
        'quiz': attempt.quiz,
        'material': attempt.quiz.material,
        'answers': answers,
        'total_questions': total_questions,
        'correct_count': correct_count,
    })
