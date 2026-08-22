from django import forms

from .models import (
    CategoriaFinanceira,
    ContaFinanceira,
    Entrada,
    FormaPagamento,
    Saida,
)
from .services import dividir_em_parcelas


class CategoriaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = CategoriaFinanceira
        fields = ["nome", "tipo", "categoria_pai", "descricao"]

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = CategoriaFinanceira.objects.filter(categoria_pai__isnull=True)
        if tenant is not None:
            qs = qs.for_tenant(tenant)
        self.fields["categoria_pai"].queryset = qs


class ContaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = ContaFinanceira
        fields = [
            "nome",
            "tipo",
            "saldo_inicial",
            "permitir_saldo_negativo",
            "ativo",
        ]


class FormaPagamentoForm(forms.ModelForm):
    class Meta:
        model = FormaPagamento
        fields = ["nome", "codigo", "taxa_percentual", "gera_conta_receber"]


class EntradaForm(forms.ModelForm):
    class Meta:
        model = Entrada
        fields = [
            "descricao",
            "valor",
            "categoria",
            "conta_financeira",
            "forma_pagamento",
            "data_competencia",
            "data_prevista",
            "observacao",
        ]
        widgets = {
            "data_competencia": forms.DateInput(attrs={"type": "date"}),
            "data_prevista": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            categorias = CategoriaFinanceira.objects.for_tenant(tenant).filter(
                ativo=True, tipo__in=[
                    CategoriaFinanceira.Tipo.ENTRADA,
                    CategoriaFinanceira.Tipo.AMBOS,
                ]
            )
            contas = ContaFinanceira.objects.for_tenant(tenant).filter(ativo=True)
            formas = FormaPagamento.objects.for_tenant(tenant).filter(ativo=True)
        else:
            categorias = ContaFinanceira.objects.none()
            contas = categorias
            formas = categorias
        self.fields["categoria"].queryset = categorias
        self.fields["conta_financeira"].queryset = contas
        self.fields["forma_pagamento"].queryset = formas

    def clean_valor(self):
        valor = self.cleaned_data.get("valor")
        if valor is not None and valor <= 0:
            raise forms.ValidationError("Valor deve ser positivo.")
        return valor


class SaidaForm(forms.ModelForm):
    class Meta:
        model = Saida
        fields = [
            "descricao",
            "valor",
            "categoria",
            "conta_financeira",
            "data_competencia",
            "data_vencimento",
            "observacao",
        ]
        widgets = {
            "data_competencia": forms.DateInput(attrs={"type": "date"}),
            "data_vencimento": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            categorias = CategoriaFinanceira.objects.for_tenant(tenant).filter(
                ativo=True, tipo__in=[
                    CategoriaFinanceira.Tipo.SAIDA,
                    CategoriaFinanceira.Tipo.AMBOS,
                ]
            )
            contas = ContaFinanceira.objects.for_tenant(tenant).filter(ativo=True)
        else:
            categorias = ContaFinanceira.objects.none()
            contas = categorias
        self.fields["categoria"].queryset = categorias
        self.fields["conta_financeira"].queryset = contas

    def clean_valor(self):
        valor = self.cleaned_data.get("valor")
        if valor is not None and valor <= 0:
            raise forms.ValidationError("Valor deve ser positivo.")
        return valor


class ContaReceberForm(forms.Form):
    descricao = forms.CharField(max_length=200)
    cliente_nome = forms.CharField(max_length=200, required=False)
    valor_total = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0.01)
    quantidade_parcelas = forms.IntegerField(min_value=1, max_value=48, initial=1)
    primeiro_vencimento = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"})
    )

    def parcelas_valores(self):
        return dividir_em_parcelas(
            self.cleaned_data["valor_total"],
            self.cleaned_data["quantidade_parcelas"],
        )
