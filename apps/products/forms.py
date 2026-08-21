from django import forms

from .models import Categoria, Marca, Produto

INPUT_CLASS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
    "placeholder-slate-400 focus:border-indigo-500 focus:outline-none "
    "focus:ring-1 focus:ring-indigo-500"
)


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ("nome", "descricao", "ativo")
        widgets = {
            "nome": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "descricao": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }


class MarcaForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ("nome", "ativo")
        widgets = {
            "nome": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }


class ProdutoForm(forms.ModelForm):
    """Formulário de produto com querysets restritos ao tenant."""

    class Meta:
        model = Produto
        fields = (
            "nome",
            "sku",
            "categoria",
            "marca",
            "tamanho",
            "unidade_medida",
            "preco_custo",
            "preco_venda",
            "estoque_minimo",
            "estoque_maximo",
            "descricao",
            "observacao",
            "ativo",
        )
        widgets = {
            "nome": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Nome do produto"}
            ),
            "sku": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: CAM-001-PRETO-M"}
            ),
            "tamanho": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: M, 500ml"}
            ),
            "preco_custo": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.01"}
            ),
            "preco_venda": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.01"}
            ),
            "estoque_minimo": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.001"}
            ),
            "estoque_maximo": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "step": "0.001"}
            ),
            "descricao": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
            "observacao": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant is not None:
            self.fields["categoria"].queryset = Categoria.objects.for_tenant(tenant)
            self.fields["marca"].queryset = Marca.objects.for_tenant(tenant)
        for campo in ("categoria", "marca"):
            self.fields[campo].widget.attrs["class"] = INPUT_CLASS

    def clean(self):
        cleaned = super().clean()
        tenant = getattr(self.instance, "tenant", None) or self.tenant
        categoria = cleaned.get("categoria")
        marca = cleaned.get("marca")
        if tenant is not None:
            if categoria is not None and categoria.tenant_id != tenant.id:
                self.add_error("categoria", "Categoria não pertence ao tenant.")
            if marca is not None and marca.tenant_id != tenant.id:
                self.add_error("marca", "Marca não pertence ao tenant.")
        return cleaned
