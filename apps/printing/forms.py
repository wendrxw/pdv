"""Formulários do módulo de impressão."""

from django import forms

from .models import ConfiguracaoImpressao, EstacaoImpressao


class ConfiguracaoImpressaoForm(forms.ModelForm):
    """Edição da configuração de impressão da loja."""

    class Meta:
        model = ConfiguracaoImpressao
        fields = [
            "largura",
            "impressao_automatica",
            "estacao_padrao",
            "tentativas_maximas",
            "nome_loja",
            "cnpj",
            "endereco",
            "telefone",
            "mensagem_final",
        ]
        widgets = {
            "nome_loja": forms.TextInput(attrs={"placeholder": "Nome da loja"}),
            "cnpj": forms.TextInput(
                attrs={"placeholder": "Somente números (ex.: 00000000000100)"}
            ),
            "endereco": forms.TextInput(
                attrs={"placeholder": "Rua, número, bairro, cidade-UF"}
            ),
            "telefone": forms.TextInput(attrs={"placeholder": "(11) 99999-9999"}),
            "mensagem_final": forms.TextInput(
                attrs={"placeholder": "Obrigado pela preferência!"}
            ),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant is not None:
            self.fields[
                "estacao_padrao"
            ].queryset = EstacaoImpressao.objects.for_tenant(tenant)
        for campo in (
            "largura",
            "impressao_automatica",
            "estacao_padrao",
            "tentativas_maximas",
            "nome_loja",
            "cnpj",
            "endereco",
            "telefone",
            "mensagem_final",
        ):
            self.fields[campo].widget.attrs.setdefault(
                "class",
                "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm",
            )
        self.fields["impressao_automatica"].widget.attrs.pop("class", None)
