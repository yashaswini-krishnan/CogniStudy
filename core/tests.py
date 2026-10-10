from django.test import TestCase, Client
from django.urls import reverse
from core.models import StudyMaterial, Quiz, Question, UserAttempt, UserAnswer
from core.utils import extract_youtube_video_id, evaluate_short_answer, generate_fallback_study_content


class CognistudyUtilsTest(TestCase):
    def test_youtube_video_id_extraction(self):
        urls = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ]
        for url, expected_id in urls:
            self.assertEqual(extract_youtube_video_id(url), expected_id)

    def test_evaluate_short_answer(self):
        is_correct, feedback = evaluate_short_answer(
            user_resp="Machine learning teaches computers to learn patterns from data",
            correct_ans="Machine learning allows systems to learn from data patterns",
            explanation="Focuses on algorithmic pattern learning."
        )
        self.assertTrue(is_correct)
        self.assertIn("Good explanation", feedback)

    def test_fallback_study_content(self):
        sample_text = (
            "Artificial Intelligence is a rapidly evolving field of computer science. "
            "Neural networks simulate the biological structure of the brain. "
            "Deep learning relies on layered neural networks to process representations. "
            "Reinforcement learning optimizes rewards in decision processes."
        )
        data = generate_fallback_study_content(sample_text, "AI Foundations")
        self.assertIn("summary", data)
        self.assertIn("mcqs", data)
        self.assertIn("short_answers", data)
        self.assertTrue(len(data["mcqs"]) >= 1)
        self.assertTrue(len(data["short_answers"]) >= 1)


class CognistudyWorkflowTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_dashboard_empty(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cognistudy")
        self.assertContains(response, "No Study Materials Yet")

    def test_upload_text_material(self):
        payload = {
            'title': 'Introduction to Python',
            'source_type': 'Text',
            'text_content': (
                'Python is a high-level, interpreted programming language known for its readable syntax. '
                'It supports object-oriented, procedural, and functional programming paradigms. '
                'Python is widely used in data science, web development, and artificial intelligence.'
            )
        }
        response = self.client.post(reverse('upload'), data=payload, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify in DB
        material = StudyMaterial.objects.filter(title='Introduction to Python').first()
        self.assertIsNotNone(material)
        self.assertEqual(material.source_type, 'Text')
        self.assertTrue(len(material.summary) > 0)

        quiz = material.quizzes.first()
        self.assertIsNotNone(quiz)
        questions = quiz.questions.all()
        self.assertTrue(questions.count() > 0)

    def test_quiz_and_result_flow(self):
        material = StudyMaterial.objects.create(
            title="Database Systems",
            source_type="Text",
            content="Relational databases use tables with rows and columns. SQL is the standard language.",
            summary="Relational databases organize data into tables and rely on SQL."
        )
        quiz = Quiz.objects.create(material=material, title="Database Systems Quiz")
        q1 = Question.objects.create(
            quiz=quiz,
            question_text="What does SQL stand for?",
            question_type="MCQ",
            options=["Structured Query Language", "Simple Quick Logic", "System Quality Link", "Standard Query List"],
            correct_answer="Structured Query Language",
            explanation="SQL is Structured Query Language."
        )
        q2 = Question.objects.create(
            quiz=quiz,
            question_text="Describe what relational databases use to store data.",
            question_type="Short",
            correct_answer="Tables with rows and columns",
            explanation="Tables organize relational records."
        )

        # GET quiz page
        response = self.client.get(reverse('quiz', args=[quiz.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What does SQL stand for?")

        # Submit quiz answers
        submission = {
            f"question_{q1.id}": "Structured Query Language",
            f"question_{q2.id}": "Relational databases store data in tables composed of rows and columns",
        }
        submit_response = self.client.post(reverse('quiz', args=[quiz.id]), data=submission, follow=True)
        self.assertEqual(submit_response.status_code, 200)

        # Check attempt was saved
        attempt = UserAttempt.objects.filter(quiz=quiz).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.score, 100.0)
        self.assertEqual(attempt.answers.count(), 2)

        # Result page contains correct data
        self.assertContains(submit_response, "100.0%")
        self.assertContains(submit_response, "Outstanding Mastery!")

    def test_delete_material(self):
        material = StudyMaterial.objects.create(
            title="Temporary Note",
            source_type="Text",
            content="Notes to be deleted.",
            summary="Summary to be deleted."
        )
        quiz = Quiz.objects.create(material=material, title="Temp Quiz")
        
        response = self.client.post(reverse('delete_material', args=[material.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudyMaterial.objects.filter(id=material.id).exists())
        self.assertFalse(Quiz.objects.filter(id=quiz.id).exists())
