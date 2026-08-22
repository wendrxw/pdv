from django import forms

from apps.financial.models import ContaFinanceira, FormaPagamento


class AbrirCaixaForm(forms.Form):
    conta_financeira = forms.ModelChoiceField(
        label="Conta do caixa",
        queryset=ContaFinanceira.objects.none(),
    )
    saldo_inicial = forms.DecimalField(
        label="Saldo inicial (troco)",
        max_digits=14,
        decimal_places=2,
        min_value=0,
        initial=0,
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["conta_financeira"].queryset = (
                ContaFinanceira.objects.for_tenant(tenant).filter(ativo=True)
            )


class MovimentacaoCaixaForm(forms.Form):
    valor = forms.DecimalField(
        label="Valor", max_digits=14, decimal_places=2, min_value=0.01
    )
    motivo = forms.CharField(label="Motivo", max_length=255, required=False)


class FecharCaixaForm(forms.Form):
    saldo_informado = forms.DecimalField(
        label="Saldo contado no caixa",
        max_digits=14,
        decimal_places=2,
        min_value=0,
    )
    observacao = forms.CharField(
        label="Observação", widget=forms.Textarea, required=False
    )


class PagamentoVendaForm(forms.Form):
    forma_pagamento = forms.ModelChoiceField(
        label="Forma de pagamento",
        queryset=FormaPagamento.objects.none(),
    )
    valor = forms.DecimalField(
        label="Valor", max_digits=14, decimal_places=2, min_value=0.01
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["forma_pagamento"].queryset = (
                FormaPagamento.objects.for_tenant(tenant).filter(ativo=True)
            )
