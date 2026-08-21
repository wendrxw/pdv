from django import forms

from apps.products.models import Produto

from .models import Fornecedor

INPUT_CLASS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
    "placeholder-slate-400 focus:border-indigo-500 focus:outline-none "
    "focus:ring-1 focus:ring-indigo-500"
)


class EntradaEstoqueForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.none(), label="Produto"
    )
    quantidade = forms.DecimalField(
        label="Quantidade", min_value=0.001, decimal_places=3, max_digits=12
    )
    custo_unitario = forms.DecimalField(
        label="Custo unitário",
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=12,
    )
    fornecedor = forms.ModelChoiceField(
        queryset=Fornecedor.objects.none(),
        required=False,
        label="Fornecedor",
    )
    referencia = forms.CharField(
        label="Documento/referência", max_length=100, required=False
    )
    motivo = forms.CharField(label="Observação", max_length=200, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["produto"].queryset = Produto.objects.for_tenant(
                tenant
            ).filter(ativo=True)
            self.fields["fornecedor"].queryset = Fornecedor.objects.for_tenant(
                tenant
            ).filter(ativo=True)
        for campo in self.fields:
            self.fields[campo].widget.attrs.setdefault("class", INPUT_CLASS)

    def clean_produto(self):
        produto = self.cleaned_data["produto"]
        if not produto.ativo:
            raise forms.ValidationError("Produto inativo.")
        return produto


class SaidaEstoqueForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.none(), label="Produto"
    )
    quantidade = forms.DecimalField(
        label="Quantidade", min_value=0.001, decimal_places=3, max_digits=12
    )
    motivo = forms.CharField(label="Motivo", max_length=200, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["produto"].queryset = Produto.objects.for_tenant(
                tenant
            ).filter(ativo=True)
        for campo in self.fields:
            self.fields[campo].widget.attrs.setdefault("class", INPUT_CLASS)
