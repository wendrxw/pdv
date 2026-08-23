from django import forms

from .models import ClientePlataforma, Onboarding


class ClientePlataformaForm(forms.ModelForm):
    senha = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        required=False,
        help_text="Deixe em branco para manter a senha atual.",
    )

    class Meta:
        model = ClientePlataforma
        fields = "__all__"

    def clean_status(self):
        status = self.cleaned_data["status"]
        if status != ClientePlataforma.Status.ATIVO:
            return status
        atual = self.instance.status
        if (
            atual != ClientePlataforma.Status.SUSPENSO
            and not Onboarding.objects.filter(
                cliente=self.instance, tenant__isnull=False
            ).exists()
        ):
            raise forms.ValidationError(
                "A ativação deve ser feita pela ação de ativação, "
                "que cria o tenant automaticamente."
            )
        return status

    def save(self, commit=True):
        senha_atual = self.instance.senha
        cliente = super().save(commit=False)
        senha_digitada = self.cleaned_data.get("senha")
        if senha_digitada:
            cliente.set_password(senha_digitada)
        elif cliente.pk:
            cliente.senha = senha_atual
        if commit:
            cliente.save()
            self._save_m2m()
        return cliente
