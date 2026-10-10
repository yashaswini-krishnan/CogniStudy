from django.contrib import admin
from .models import StudyMaterial, Quiz, Question, UserAttempt, UserAnswer


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'source_type', 'user', 'created_at')
    list_filter = ('source_type', 'created_at')
    search_fields = ('title', 'content', 'summary')


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'material', 'created_at')
    search_fields = ('title',)
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'quiz', 'question_type')
    list_filter = ('question_type',)
    search_fields = ('question_text', 'correct_answer')


class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0


@admin.register(UserAttempt)
class UserAttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'quiz', 'user', 'score', 'completed_at')
    list_filter = ('completed_at',)
    inlines = [UserAnswerInline]


@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ('id', 'attempt', 'question', 'is_correct')
    list_filter = ('is_correct',)
