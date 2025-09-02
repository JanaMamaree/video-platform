from django import forms
from django.contrib.auth.models import User
from .models import Video


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password']
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match!")

class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)


class VideoUploadForm(forms.ModelForm):
    players = forms.CharField(
        max_length=500,
        help_text="Comma-separated player names"
    )

    class Meta:
        model = Video
        fields = ['title', 'file', 'players']
