from django import forms

from .models import Cliente

INPUT_CLASS = (
    "w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm "
    "text-slate-900 placeholder-slate-400 focus:border-blue-500 "
    "focus:outline-none focus:ring-1 focus:ring-blue-500"
)


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = (
            "nome",
            "cpf_cnpj",
            "email",
            "telefone",
            "endereco",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "estado",
            "cep",
            "observacoes",
            "ativo",
        )
        widgets = {
            "nome": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: Maria da Silva"}
            ),
            "cpf_cnpj": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: 123.456.789-00",
                    "inputmode": "numeric",
                    "maxlength": 14,
                }
            ),
            "email": forms.EmailInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: maria@email.com"}
            ),
            "telefone": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: (11) 99999-9999"}
            ),
            "endereco": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Rua, avenida..."}
            ),
            "numero": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "complemento": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "bairro": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "cidade": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "estado": forms.Select(
                attrs={"class": INPUT_CLASS},
                choices=[("", "Selecione")] + Cliente.UF.choices,
            ),
            "cep": forms.TextInput(
                attrs={"class": INPUT_CLASS, "inputmode": "numeric", "maxlength": 8}
            ),
            "observacoes": forms.Textarea(
                attrs={"class": INPUT_CLASS, "rows": 3, "maxlength": 255}
            ),
            "ativo": forms.Select(choices=[(True, "Ativo"), (False, "Inativo")]),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ativo"].widget.attrs["class"] = INPUT_CLASS

    def clean_cpf_cnpj(self):
        valor = (self.cleaned_data.get("cpf_cnpj") or "").strip()
        return "".join(caractere for caractere in valor if caractere.isdigit())

    def clean_cep(self):
        valor = (self.cleaned_data.get("cep") or "").strip()
        return "".join(caractere for caractere in valor if caractere.isdigit())

    def clean(self):
        cleaned = super().clean()
        cpf_cnpj = cleaned.get("cpf_cnpj")
        if cpf_cnpj:
            duplicado = (
                Cliente.objects.for_tenant(self.instance.tenant)
                .filter(cpf_cnpj=cpf_cnpj)
                .exclude(pk=self.instance.pk)
                .exists()
                if self.instance.tenant_id
                else False
            )
            if duplicado:
                self.add_error(
                    "cpf_cnpj", "Já existe um cliente com este CPF/CNPJ."
                )
        return cleaned
