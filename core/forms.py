from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import StudyMaterial


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'name@example.com',
            'required': 'required'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            self.fields['username'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Choose a username',
                'required': 'required'
            })
            self.fields['username'].help_text = 'Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'
        if 'password1' in self.fields:
            self.fields['password1'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Create a strong password',
                'required': 'required'
            })
        if 'password2' in self.fields:
            self.fields['password2'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Confirm your password',
                'required': 'required'
            })

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email address already exists.')
        return email


class UserLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            self.fields['username'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Enter username',
                'required': 'required'
            })
        if 'password' in self.fields:
            self.fields['password'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Enter password',
                'required': 'required'
            })


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

    SUMMARY_LEVEL_CHOICES = [
        ('short', 'Short Summary (Quick 2-minute overview & key points)'),
        ('medium', 'Medium Summary (Balanced structured concepts & definitions)'),
        ('detailed', 'Detailed Study Notes (In-depth comprehensive breakdown)'),
    ]

    summary_level = forms.ChoiceField(
        choices=SUMMARY_LEVEL_CHOICES,
        initial='medium',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'summaryLevelSelect'
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
            elif pdf_file.size > 15 * 1024 * 1024:
                self.add_error('pdf_file', 'The PDF file size exceeds the 15 MB limit. Please upload a smaller file.')
        elif source_type == 'YouTube':
            if not youtube_url or not youtube_url.strip():
                self.add_error('youtube_url', 'Please enter a valid YouTube video URL or ID.')

        return cleaned_data


class StudyMaterialUpdateForm(forms.ModelForm):
    class Meta:
        model = StudyMaterial
        fields = ['title', 'summary']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Material Title',
                'required': 'required'
            }),
            'summary': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 12,
                'placeholder': 'Refine or customize your study summary notes here...',
                'required': 'required'
            }),
        }

