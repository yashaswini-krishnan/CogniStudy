import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponseNotAllowed

from .models import StudyMaterial, Quiz, Question, UserAttempt, UserAnswer
from .forms import (
    StudyMaterialUploadForm,
    StudyMaterialUpdateForm,
    UserRegisterForm,
    UserLoginForm
)
from .utils import (
    extract_text_from_pdf,
    fetch_youtube_transcript,
    generate_study_material_with_gemini,
    evaluate_short_answer
)

logger = logging.getLogger(__name__)


def landing_view(request):
    """
    Public landing page at '/'. Redirects authenticated users straight to
    the dashboard so they skip the marketing page on repeat visits.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/landing.html')


def register_view(request):
    """User registration view with automatic login upon successful sign up."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to CogniStudy, {user.username}! Your account has been created.")
            return redirect('dashboard')
    else:
        form = UserRegisterForm()

    return render(request, 'core/register.html', {'form': form})


def login_view(request):
    """User login view with redirect handling and session creation."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    next_url = request.GET.get('next') or request.POST.get('next') or 'dashboard'

    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password. Please try again.")
    else:
        form = UserLoginForm(request)

    return render(request, 'core/login.html', {'form': form, 'next': next_url})


def logout_view(request):
    """User logout view that invalidates session and redirects to login."""
    if request.user.is_authenticated:
        username = request.user.username
        logout(request)
        messages.info(request, f"Goodbye, {username}! You have been logged out successfully.")
    return redirect('login')


@login_required
def dashboard_view(request):
    """
    Dashboard view listing only the authenticated user's uploaded study materials.
    Enforces strict user-level data isolation.
    Supports live search (JS-based) and pagination (6 cards per page).
    """
    materials_qs = (
        StudyMaterial.objects.filter(user=request.user)
        .prefetch_related('quizzes', 'quizzes__questions')
        .order_by('-created_at')
    )
    paginator = Paginator(materials_qs, 6)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'materials': page_obj,          # keep alias for backward compat
        'total_count': materials_qs.count(),
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def upload_view(request):
    """
    Upload view to handle Text, PDF, or YouTube inputs.
    Extracts content, queries Gemini AI for summary and quiz questions,
    and saves records in MySQL scoped strictly to request.user.
    """
    if request.method == 'POST':
        form = StudyMaterialUploadForm(request.POST, request.FILES)
        if form.is_valid():
            title = form.cleaned_data['title'].strip()
            source_type = form.cleaned_data['source_type']
            summary_level = form.cleaned_data.get('summary_level', 'medium')
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
                ai_data = generate_study_material_with_gemini(raw_content, title, summary_level=summary_level)
                summary = ai_data.get('summary', '').strip()
                mcqs = ai_data.get('mcqs', [])
                short_answers = ai_data.get('short_answers', [])

                if not mcqs and not short_answers:
                    messages.error(request, "Unable to generate quiz questions from this material. Please try again.")
                    return render(request, 'core/upload.html', {'form': form})

                # 3. Save StudyMaterial, Quiz, and Questions in a database transaction
                with transaction.atomic():
                    material = StudyMaterial.objects.create(
                        user=request.user,
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
                # Sanitize error message to avoid exposing internal server stack traces or keys
                messages.error(request, "We encountered an issue processing your study material. Please verify your document or URL and try again.")
                return render(request, 'core/upload.html', {'form': form})
    else:
        form = StudyMaterialUploadForm()

    return render(request, 'core/upload.html', {'form': form})


@login_required
def material_detail_view(request, pk):
    """
    Detail view for an individual study material.
    Displays full summary, metadata, quiz link, and past quiz attempts.
    Restricted strictly to the material owner.
    """
    material = get_object_or_404(
        StudyMaterial.objects.prefetch_related('quizzes__questions'),
        pk=pk,
        user=request.user
    )
    quiz = material.quizzes.first()
    attempts = []
    if quiz:
        attempts = UserAttempt.objects.filter(quiz=quiz, user=request.user).order_by('-completed_at')

    # Calculate reading stats
    word_count = len(material.summary.split()) if material.summary else 0
    reading_time_mins = max(1, round(word_count / 200))

    context = {
        'material': material,
        'quiz': quiz,
        'attempts': attempts,
        'word_count': word_count,
        'reading_time_mins': reading_time_mins,
    }
    return render(request, 'core/material_detail.html', context)


@login_required
def edit_material_view(request, pk):
    """
    Edit view allowing users to update material title and summary notes.
    Original extracted content is preserved and no AI re-generation is triggered.
    Restricted strictly to the material owner.
    """
    material = get_object_or_404(StudyMaterial, pk=pk, user=request.user)

    if request.method == 'POST':
        form = StudyMaterialUpdateForm(request.POST, instance=material)
        if form.is_valid():
            updated_material = form.save()
            # Also keep quiz title in sync with updated material title
            for quiz in updated_material.quizzes.all():
                quiz.title = f"{updated_material.title} - Assessment Quiz"
                quiz.save(update_fields=['title'])

            messages.success(request, f"Study Material '{updated_material.title}' was successfully updated.")
            return redirect('material_detail', pk=updated_material.pk)
    else:
        form = StudyMaterialUpdateForm(instance=material)

    return render(request, 'core/material_edit.html', {
        'form': form,
        'material': material,
    })


@login_required
def delete_material_view(request, pk):
    """
    Delete a study material and its associated quizzes/questions.
    Restricted strictly to the material owner.
    """
    if request.method == 'POST':
        material = get_object_or_404(StudyMaterial, pk=pk, user=request.user)
        material_title = material.title
        material.delete()
        messages.success(request, f"Study Material '{material_title}' was successfully deleted.")
        return redirect('dashboard')
    return HttpResponseNotAllowed(['POST'])


@login_required
def quiz_view(request, pk):
    """
    Renders quiz questions and evaluates user answers on submission.
    Calculates percentage score and creates UserAttempt / UserAnswer records.
    Restricted strictly to the material owner.
    """
    quiz = get_object_or_404(
        Quiz.objects.select_related('material'),
        pk=pk,
        material__user=request.user
    )
    questions = list(quiz.questions.all())

    if not questions:
        messages.warning(request, "This quiz has no questions available.")
        return redirect('dashboard')

    if request.method == 'POST':
        total_questions = len(questions)
        correct_count = 0
        answers_to_create = []

        with transaction.atomic():
            # Create attempt placeholder bound to the authenticated user
            attempt = UserAttempt.objects.create(
                user=request.user,
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


@login_required
def quiz_result_view(request, attempt_id):
    """
    Displays detailed breakdown of a completed quiz attempt.
    Enforces that only the user who completed the attempt can view the results.
    """
    attempt = get_object_or_404(
        UserAttempt.objects.select_related('quiz', 'quiz__material').prefetch_related('answers__question'),
        pk=attempt_id,
        user=request.user
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
