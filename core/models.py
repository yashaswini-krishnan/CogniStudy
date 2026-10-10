from django.db import models
from django.contrib.auth.models import User


class StudyMaterial(models.Model):
    SOURCE_CHOICES = [
        ('PDF', 'PDF'),
        ('Text', 'Text'),
        ('YouTube', 'YouTube'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    content = models.TextField(help_text="Raw extracted text")
    summary = models.TextField(help_text="AI generated summary")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Quiz(models.Model):
    material = models.ForeignKey(StudyMaterial, related_name='quizzes', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Quiz: {self.title}"


class Question(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('MCQ', 'Multiple Choice Question'),
        ('Short', 'Short Answer Question'),
    ]

    quiz = models.ForeignKey(Quiz, related_name='questions', on_delete=models.CASCADE)
    question_text = models.TextField()
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPE_CHOICES)
    options = models.JSONField(null=True, blank=True, help_text="List of choices for MCQ")
    correct_answer = models.TextField()
    explanation = models.TextField(blank=True, default='')

    def __str__(self):
        return f"[{self.question_type}] {self.question_text[:50]}"


class UserAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    quiz = models.ForeignKey(Quiz, related_name='attempts', on_delete=models.CASCADE)
    score = models.FloatField(help_text="Score percentage")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-completed_at']

    def __str__(self):
        return f"Attempt #{self.id} on {self.quiz.title} - {self.score:.1f}%"


class UserAnswer(models.Model):
    attempt = models.ForeignKey(UserAttempt, related_name='answers', on_delete=models.CASCADE)
    question = models.ForeignKey(Question, related_name='user_answers', on_delete=models.CASCADE)
    user_response = models.TextField()
    is_correct = models.BooleanField(default=False)
    ai_feedback = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Answer for Q#{self.question_id}: {'Correct' if self.is_correct else 'Incorrect'}"
