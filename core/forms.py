from django import forms
from .models import StudyMaterial


class StudyMaterialUploadForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'e.g., Intro to Machine Learning, Photosynthesis, Operating Systems...',
            'required': 'required'
        })
    )

    source_type = forms.ChoiceField(
        choices=StudyMaterial.SOURCE_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-lg',
            'id': 'sourceTypeSelect',
            'required': 'required'
        })
    )

    text_content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 8,
            'placeholder': 'Paste your study notes, lecture transcript, or study material text here...'
        })
    )

    pdf_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf',
            'id': 'pdfFileInput'
        })
    )

    youtube_url = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., https://www.youtube.com/watch?v=dQw4w9WgXcQ or https://youtu.be/...',
            'id': 'youtubeUrlInput'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        source_type = cleaned_data.get('source_type')
        text_content = cleaned_data.get('text_content')
        pdf_file = cleaned_data.get('pdf_file')
        youtube_url = cleaned_data.get('youtube_url')

        if source_type == 'Text':
            if not text_content or not text_content.strip():
                self.add_error('text_content', 'Please provide the text content to process.')
        elif source_type == 'PDF':
            if not pdf_file:
                self.add_error('pdf_file', 'Please upload a PDF file.')
            elif not pdf_file.name.lower().endswith('.pdf'):
                self.add_error('pdf_file', 'Only PDF files are supported.')
        elif source_type == 'YouTube':
            if not youtube_url or not youtube_url.strip():
                self.add_error('youtube_url', 'Please enter a valid YouTube video URL or ID.')

        return cleaned_data
