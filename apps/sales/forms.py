from django import forms

from apps.financial.models import FormaPagamento

INPUT_CLASS = (
    "w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm "
    "text-slate-900 placeholder-slate-400 focus:border-blue-500 "
    "focus:outline-none focus:ring-1 focus:ring-blue-500"
)


class AbrirCaixaForm(forms.Form):
    saldo_inicial = forms.DecimalField(
        label="Saldo inicial (troco)",
        max_digits=14,
        decimal_places=2,
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}),
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
        to_field_name="uuid",
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
        self.fields["forma_pagamento"].widget.attrs["class"] = (
            "mt-1 w-full rounded-xl border border-slate-300 px-3 py-3 text-sm "
            "focus:border-emerald-500 focus:outline-none focus:ring-2 "
            "focus:ring-emerald-100"
        )
