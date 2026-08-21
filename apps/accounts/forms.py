from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Usuário",
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-lg border border-slate-300 px-3 py-2 "
                "focus:border-indigo-500 focus:outline-none focus:ring-1 "
                "focus:ring-indigo-500",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full rounded-lg border border-slate-300 px-3 py-2 "
                "focus:border-indigo-500 focus:outline-none focus:ring-1 "
                "focus:ring-indigo-500",
            }
        ),
    )
