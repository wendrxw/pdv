from django import forms

from apps.clients.models import LeadContato

INPUT_CLASS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
    "placeholder-slate-400 focus:border-indigo-500 focus:outline-none "
    "focus:ring-1 focus:ring-indigo-500"
)


class ContatoForm(forms.ModelForm):
    class Meta:
        model = LeadContato
        fields = ("nome", "email", "telefone", "empresa", "mensagem")
        widgets = {
            "nome": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Seu nome completo",
                    "required": True,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "voce@empresa.com.br",
                    "required": True,
                }
            ),
            "telefone": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "(16) 99999-9999",
                    "required": True,
                }
            ),
            "empresa": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Nome da empresa"}
            ),
            "mensagem": forms.Textarea(
                attrs={
                    "class": INPUT_CLASS,
                    "rows": 4,
                    "placeholder": "Conte um pouco sobre o seu negócio...",
                    "required": True,
                }
            ),
        }
