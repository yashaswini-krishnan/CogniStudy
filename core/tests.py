import io
from unittest.mock import patch
from PIL import Image
from reportlab.pdfgen import canvas
import reportlab.lib.pagesizes

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import StudyMaterial, Quiz, Question, UserAttempt, UserAnswer
from core.utils import (
    extract_youtube_video_id,
    evaluate_short_answer,
    generate_fallback_study_content,
    chunk_text,
    get_summary_prompt_instructions,
    extract_text_from_pdf,
    ocr_image_data
)


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
        self.user = User.objects.create_user(username='alice', email='alice@example.com', password='Password123!')
        self.client.force_login(self.user)

    def test_dashboard_empty(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cognistudy")
        self.assertContains(response, "No Study Materials Yet")

    @patch('core.views.generate_study_material_with_gemini')
    def test_upload_text_material(self, mock_gemini):
        mock_gemini.return_value = {
            'summary': 'Python is a high-level language with readable syntax.',
            'mcqs': [{
                'question': 'What type of language is Python?',
                'options': ['Interpreted', 'Compiled', 'Assembly', 'Low-level'],
                'correct_answer': 'Interpreted',
                'explanation': 'Python is an interpreted language.'
            }],
            'short_answers': [{
                'question': 'What is Python known for?',
                'correct_answer': 'Readable syntax and versatility',
                'explanation': 'Syntax readability is core to Python.'
            }]
        }
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
        material = StudyMaterial.objects.filter(title='Introduction to Python', user=self.user).first()
        self.assertIsNotNone(material)
        self.assertEqual(material.source_type, 'Text')
        self.assertEqual(material.user, self.user)
        self.assertTrue(len(material.summary) > 0)

        quiz = material.quizzes.first()
        self.assertIsNotNone(quiz)
        questions = quiz.questions.all()
        self.assertTrue(questions.count() > 0)

    def test_quiz_and_result_flow(self):
        material = StudyMaterial.objects.create(
            user=self.user,
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
        attempt = UserAttempt.objects.filter(quiz=quiz, user=self.user).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.score, 100.0)
        self.assertEqual(attempt.user, self.user)
        self.assertEqual(attempt.answers.count(), 2)

        # Result page contains correct data
        self.assertContains(submit_response, "100.0%")
        self.assertContains(submit_response, "Outstanding Mastery!")

    def test_delete_material(self):
        material = StudyMaterial.objects.create(
            user=self.user,
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


class CognistudyAuthAndIsolationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(username='user_a', email='a@example.com', password='PasswordA123!')
        self.user_b = User.objects.create_user(username='user_b', email='b@example.com', password='PasswordB123!')

    def test_unauthenticated_redirects(self):
        """Unauthenticated requests to protected endpoints must redirect to login."""
        endpoints = [
            reverse('dashboard'),
            reverse('upload'),
            reverse('quiz', args=[1]),
            reverse('quiz_result', args=[1]),
            reverse('delete_material', args=[1]),
        ]
        for url in endpoints:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, f"Failed for {url}")
            self.assertTrue(response.url.startswith(reverse('login')))

    def test_user_registration(self):
        """Test valid user registration and automatic login."""
        payload = {
            'username': 'newstudent',
            'email': 'student@example.com',
            'password1': 'StrongPass2026!',
            'password2': 'StrongPass2026!',
        }
        response = self.client.post(reverse('register'), data=payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='newstudent').exists())
        # Check that user is now authenticated and on dashboard
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].username, 'newstudent')

    def test_user_login_and_logout(self):
        """Test authentication login and logout flows."""
        # Login with valid credentials
        login_response = self.client.post(reverse('login'), data={
            'username': 'user_a',
            'password': 'PasswordA123!'
        }, follow=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.context['user'].is_authenticated)

        # Logout
        logout_response = self.client.get(reverse('logout'), follow=True)
        self.assertEqual(logout_response.status_code, 200)
        self.assertFalse(logout_response.context['user'].is_authenticated)

    def test_user_data_isolation(self):
        """
        Verify that User B cannot access, view, take quizzes, or delete User A's records.
        """
        # User A creates a study material and quiz
        material_a = StudyMaterial.objects.create(
            user=self.user_a,
            title="User A Private Notes",
            source_type="Text",
            content="Private information belonging to User A",
            summary="User A Summary"
        )
        quiz_a = Quiz.objects.create(material=material_a, title="Quiz A")
        q1 = Question.objects.create(
            quiz=quiz_a,
            question_text="Sample Q for Quiz A",
            question_type="MCQ",
            options=["A", "B", "C", "D"],
            correct_answer="A",
            explanation="Explanation A"
        )
        attempt_a = UserAttempt.objects.create(
            user=self.user_a,
            quiz=quiz_a,
            score=100.0
        )
        UserAnswer.objects.create(
            attempt=attempt_a,
            question=q1,
            user_response="A",
            is_correct=True,
            ai_feedback="Great!"
        )

        # Now log in as User B
        self.client.force_login(self.user_b)

        # 1. Dashboard: User B should NOT see User A's material
        dash_response = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_response.status_code, 200)
        self.assertNotContains(dash_response, "User A Private Notes")

        # 2. Quiz view: User B cannot access User A's quiz (must return 404)
        quiz_response = self.client.get(reverse('quiz', args=[quiz_a.id]))
        self.assertEqual(quiz_response.status_code, 404)

        # 3. Quiz submission: User B cannot submit answers to User A's quiz (must return 404)
        submit_response = self.client.post(reverse('quiz', args=[quiz_a.id]), data={
            f"question_{q1.id}": "A"
        })
        self.assertEqual(submit_response.status_code, 404)

        # 4. Result view: User B cannot view User A's attempt results (must return 404)
        result_response = self.client.get(reverse('quiz_result', args=[attempt_a.id]))
        self.assertEqual(result_response.status_code, 404)

        # 5. Delete view: User B cannot delete User A's material (must return 404)
        delete_response = self.client.post(reverse('delete_material', args=[material_a.id]))
        self.assertEqual(delete_response.status_code, 404)

        # Verify Material A still exists intact
        self.assertTrue(StudyMaterial.objects.filter(id=material_a.id).exists())

    def test_pdf_file_size_validation(self):
        """Test that uploading a PDF exceeding 15MB raises a validation error."""
        self.client.force_login(self.user_a)
        # Create a dummy file exceeding 15MB
        oversized_content = b'%PDF-1.4 ' + b'0' * (16 * 1024 * 1024)
        oversized_file = SimpleUploadedFile("large_doc.pdf", oversized_content, content_type="application/pdf")

        response = self.client.post(reverse('upload'), data={
            'title': 'Too Big PDF',
            'source_type': 'PDF',
            'pdf_file': oversized_file
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "15 MB limit")


class CognistudyCRUDTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(username='carol', email='carol@example.com', password='PasswordC123!')
        self.user_b = User.objects.create_user(username='dave', email='dave@example.com', password='PasswordD123!')

        # Create a material for User A
        self.material_a = StudyMaterial.objects.create(
            user=self.user_a,
            title="Operating Systems Principles",
            source_type="Text",
            content="Original OS lecture text on processes, threads, and memory paging.",
            summary="Processes are running programs with isolated virtual memory."
        )
        self.quiz_a = Quiz.objects.create(
            material=self.material_a,
            title="Operating Systems Principles - Assessment Quiz"
        )
        self.question_a = Question.objects.create(
            quiz=self.quiz_a,
            question_text="What represents a running instance of a program?",
            question_type="MCQ",
            options=["Process", "Thread", "Kernel", "Page Table"],
            correct_answer="Process",
            explanation="A process is an instance of a program in execution."
        )

    def test_material_detail_view_owner(self):
        """Owner can view the material detail page with summary and raw content."""
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('material_detail', args=[self.material_a.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operating Systems Principles")
        self.assertContains(response, "Processes are running programs")
        self.assertContains(response, "Original Extracted Source Content")

    def test_material_detail_view_isolation(self):
        """Another user accessing the material detail page receives a 404."""
        self.client.force_login(self.user_b)
        response = self.client.get(reverse('material_detail', args=[self.material_a.id]))
        self.assertEqual(response.status_code, 404)

    def test_material_edit_view_owner(self):
        """Owner can update title and summary without altering raw content."""
        self.client.force_login(self.user_a)

        # GET edit page
        get_response = self.client.get(reverse('edit_material', args=[self.material_a.id]))
        self.assertEqual(get_response.status_code, 200)

        # POST updated title and refined summary
        updated_payload = {
            'title': 'Advanced Operating Systems',
            'summary': 'Updated notes: Virtual memory uses page tables and TLBs for fast lookups.'
        }
        post_response = self.client.post(
            reverse('edit_material', args=[self.material_a.id]),
            data=updated_payload,
            follow=True
        )
        self.assertEqual(post_response.status_code, 200)

        # Verify DB updates
        self.material_a.refresh_from_db()
        self.assertEqual(self.material_a.title, 'Advanced Operating Systems')
        self.assertEqual(self.material_a.summary, 'Updated notes: Virtual memory uses page tables and TLBs for fast lookups.')
        # Verify raw extracted content was preserved
        self.assertEqual(self.material_a.content, "Original OS lecture text on processes, threads, and memory paging.")

        # Verify quiz title was synchronized
        self.quiz_a.refresh_from_db()
        self.assertEqual(self.quiz_a.title, 'Advanced Operating Systems - Assessment Quiz')

    def test_material_edit_view_isolation(self):
        """Another user cannot edit material belonging to user A."""
        self.client.force_login(self.user_b)
        post_response = self.client.post(
            reverse('edit_material', args=[self.material_a.id]),
            data={'title': 'Hacked Title', 'summary': 'Hacked Summary'}
        )
        self.assertEqual(post_response.status_code, 404)

        # Verify material was not modified
        self.material_a.refresh_from_db()
        self.assertEqual(self.material_a.title, 'Operating Systems Principles')

    def test_material_delete_cascade(self):
        """Deleting a material removes its quizzes, questions, and attempt records."""
        self.client.force_login(self.user_a)
        attempt = UserAttempt.objects.create(user=self.user_a, quiz=self.quiz_a, score=100.0)
        UserAnswer.objects.create(attempt=attempt, question=self.question_a, user_response="Process", is_correct=True)

        delete_response = self.client.post(reverse('delete_material', args=[self.material_a.id]), follow=True)
        self.assertEqual(delete_response.status_code, 200)

        # Verify cascaded removal
        self.assertFalse(StudyMaterial.objects.filter(id=self.material_a.id).exists())
        self.assertFalse(Quiz.objects.filter(id=self.quiz_a.id).exists())
        self.assertFalse(Question.objects.filter(id=self.question_a.id).exists())
        self.assertFalse(UserAttempt.objects.filter(id=attempt.id).exists())


class CognistudySummarizationAndChunkingTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='elena', email='elena@example.com', password='PasswordE123!')
        self.client.force_login(self.user)

    def test_chunking_short_text(self):
        """Short text below max_chunk_size must return a single chunk."""
        text = "This is a short paragraph of study notes."
        chunks = chunk_text(text, max_chunk_size=1000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_chunking_long_text_preserves_content(self):
        """Long text must be partitioned across boundary breaks without mid-word splits."""
        paragraphs = [
            f"Paragraph {i}: Distributed systems require consensus protocols like Paxos and Raft to manage replicated state machines reliably across failure zones."
            for i in range(250)
        ]
        large_text = "\n\n".join(paragraphs)
        chunks = chunk_text(large_text, max_chunk_size=5000, overlap=300)
        self.assertTrue(len(chunks) > 4)
        self.assertIn("Paragraph 0", chunks[0])
        self.assertIn("Paragraph 249", chunks[-1])

    def test_summary_prompt_instructions(self):
        """Verify tailored pedagogical instructions for short, medium, and detailed levels."""
        short_instr = get_summary_prompt_instructions('short')
        self.assertIn("SHORT REVISION SUMMARY", short_instr)
        self.assertIn("Quick Overview", short_instr)

        med_instr = get_summary_prompt_instructions('medium')
        self.assertIn("BALANCED, WELL-STRUCTURED", med_instr)
        self.assertIn("Executive Overview", med_instr)

        detail_instr = get_summary_prompt_instructions('detailed')
        self.assertIn("EXHAUSTIVE, DETAILED", detail_instr)
        self.assertIn("Comprehensive Overview", detail_instr)

    def test_fallback_summary_depth_levels(self):
        """Verify fallback generator generates structured headings based on chosen level."""
        sample_text = (
            "Operating systems manage hardware resources and provide services for application programs. "
            "The kernel is the core component that operates in privileged mode. "
            "Processes represent execution units with their own address spaces. "
            "Threads share the process address space while maintaining independent program counters. "
            "Context switching incurs CPU overhead due to register state saving. "
            "Virtual memory maps logical addresses to physical RAM frames. "
            "Page faults trigger disk I/O to load missing memory pages. "
            "Scheduling algorithms like Round Robin ensure fair CPU time sharing."
        )

        short_data = generate_fallback_study_content(sample_text, "OS", summary_level='short')
        self.assertIn("Quick Overview", short_data["summary"])
        self.assertIn("Core Key Points", short_data["summary"])

        detail_data = generate_fallback_study_content(sample_text, "OS", summary_level='detailed')
        self.assertIn("Comprehensive Overview", detail_data["summary"])
        self.assertIn("Conceptual Breakdown", detail_data["summary"])

    @patch('core.views.generate_study_material_with_gemini')
    def test_upload_with_summary_level_selection(self, mock_gemini):
        """Test submitting form with 'detailed' summary level."""
        mock_gemini.return_value = {
            'summary': '### Comprehensive Overview\nOSI model defines seven distinct layers.',
            'mcqs': [{
                'question': 'How many layers are in the OSI model?',
                'options': ['7', '4', '5', '6'],
                'correct_answer': '7',
                'explanation': 'The OSI model has 7 layers.'
            }],
            'short_answers': [{
                'question': 'What is the role of the transport layer?',
                'correct_answer': 'Reliable end-to-end communication',
                'explanation': 'Transport layer ensures reliable data transmission.'
            }]
        }
        payload = {
            'title': 'Computer Networks Architecture',
            'source_type': 'Text',
            'summary_level': 'detailed',
            'text_content': (
                "The Open Systems Interconnection model defines seven networking layers. "
                "The physical layer transmits unstructured raw bit streams over a physical medium. "
                "The data link layer handles node-to-node data transfer and error detection. "
                "The network layer routes packets using logical IP addressing. "
                "The transport layer provides reliable end-to-end communication via TCP."
            )
        }
        response = self.client.post(reverse('upload'), data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        material = StudyMaterial.objects.filter(title='Computer Networks Architecture', user=self.user).first()
        self.assertIsNotNone(material)
        self.assertTrue(len(material.summary) > 0)
        self.assertIn("Comprehensive Overview", material.summary)


class CognistudyPDFAndOCRTest(TestCase):
    def test_extract_text_from_pdf_text_based(self):
        """Standard text-based PDF pages are extracted directly without OCR."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, "Page 1: Artificial intelligence and neural network fundamentals in modern computing.")
        c.showPage()
        c.drawString(72, 720, "Page 2: Deep learning structures utilize multiple stacked hidden layers for feature hierarchy.")
        c.save()
        buf.seek(0)

        extracted = extract_text_from_pdf(buf)
        self.assertIn("Page 1: Artificial intelligence", extracted)
        self.assertIn("Page 2: Deep learning structures", extracted)

    def test_extract_text_from_pdf_unreadable_raises_value_error(self):
        """A PDF with empty pages and no OCR extractable text raises a helpful ValueError."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.showPage()
        c.save()
        buf.seek(0)

        with self.assertRaises(ValueError) as ctx:
            extract_text_from_pdf(buf)
        self.assertIn("does not contain readable text", str(ctx.exception))

    def test_ocr_image_data_offline_returns_none(self):
        """Calling ocr_image_data with no tesseract and no valid API key returns None gracefully."""
        img = Image.new('RGB', (100, 100), color='white')
        img_buf = io.BytesIO()
        img.save(img_buf, format='PNG')

        with patch.dict('os.environ', {'GEMINI_API_KEY': ''}):
            result = ocr_image_data(img_buf.getvalue(), mime_type='image/png')
            self.assertIsNone(result)

    @patch('core.utils.ocr_image_data')
    def test_hybrid_pdf_extraction_mixed_with_ocr(self, mock_ocr):
        """
        Verify hybrid PDF extraction:
        Page 1: Regular text extracted via pypdf.
        Page 2: Scanned image with no direct text, extracted via OCR service.
        Results combined in exact page order.
        """
        mock_ocr.return_value = "Page 2 OCR: Transcribed text from scanned document diagram."

        img = Image.new('RGB', (120, 120), color='blue')
        img_buf = io.BytesIO()
        img.save(img_buf, format='JPEG')
        img_buf.seek(0)

        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, "Page 1 Text: Foundational principles of software architecture and domain design.")
        c.showPage()
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(img_buf), 72, 500, width=120, height=120)
        c.showPage()
        c.save()
        buf.seek(0)

        result = extract_text_from_pdf(buf)
        self.assertIn("Page 1 Text: Foundational principles", result)
        self.assertIn("Page 2 OCR: Transcribed text from scanned document diagram.", result)
        idx_p1 = result.find("Page 1 Text")
        idx_p2 = result.find("Page 2 OCR")
        self.assertTrue(idx_p1 < idx_p2)


