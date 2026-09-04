from django import forms

from .barcode import BarcodeError, BarcodeService
from .models import Categoria, Marca, Produto

INPUT_CLASS = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 "
    "placeholder-slate-400 focus:border-indigo-500 focus:outline-none "
    "focus:ring-1 focus:ring-indigo-500"
)

TAMANHO_MAXIMO_IMAGEM = 5 * 1024 * 1024
EXTENSOES_PERMITIDAS_IMAGEM = {"png", "jpg", "jpeg", "webp"}


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

    imagem = forms.FileField(
        required=False,
        label="Imagem do produto",
        help_text="PNG, JPG ou WEBP — tamanho máximo 5MB.",
    )

    class Meta:
        model = Produto
        fields = (
            "nome",
            "sku",
            "codigo_barras",
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
            "ncm",
            "cest",
            "cfop",
            "origem",
            "imagem",
            "ativo",
        )
        widgets = {
            "nome": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: Coca-Cola 350ml"}
            ),
            "sku": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ex.: CAM-001-PRETO-M"}
            ),
            "codigo_barras": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: 7891234567890",
                    "inputmode": "numeric",
                    "maxlength": 13,
                    "data-barcode-input": True,
                }
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
            "ncm": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: 21069030",
                    "inputmode": "numeric",
                    "maxlength": 8,
                }
            ),
            "cest": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: 2801000",
                    "inputmode": "numeric",
                    "maxlength": 7,
                }
            ),
            "cfop": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Ex.: 5102",
                    "inputmode": "numeric",
                    "maxlength": 4,
                }
            ),
            "origem": forms.Select(attrs={"class": INPUT_CLASS}),
            "ativo": forms.Select(
                choices=[(True, "Ativo"), (False, "Inativo")]
            ),
            "descricao": forms.Textarea(
                attrs={
                    "class": INPUT_CLASS,
                    "rows": 4,
                    "placeholder": "Descrição detalhada do produto...",
                    "maxlength": 255,
                }
            ),
            "observacao": forms.Textarea(
                attrs={
                    "class": INPUT_CLASS,
                    "rows": 4,
                    "placeholder": "Informações adicionais...",
                    "maxlength": 255,
                }
            ),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant is not None:
            self.fields["categoria"].queryset = Categoria.objects.for_tenant(tenant)
            self.fields["marca"].queryset = Marca.objects.for_tenant(tenant)
        self.fields["categoria"].empty_label = "Selecione uma categoria"
        self.fields["marca"].empty_label = "Selecione uma marca"
        for campo in ("categoria", "marca", "unidade_medida", "ativo"):
            self.fields[campo].widget.attrs["class"] = INPUT_CLASS
        # Nenhum campo é obrigatório nesta tela, exceto nome e preço de
        # venda (conforme diretriz do produto).
        self.fields["unidade_medida"].required = False
        self.fields["categoria"].required = False
        self.fields["marca"].required = False

    def clean_unidade_medida(self):
        valor = self.cleaned_data.get("unidade_medida")
        if not valor:
            return Produto.UnidadeMedida.UN
        return valor

    def clean_imagem(self):
        arquivo = self.cleaned_data.get("imagem")
        if not arquivo:
            return None
        extensao = (
            arquivo.name.rsplit(".", 1)[-1].lower() if "." in arquivo.name else ""
        )
        if extensao not in EXTENSOES_PERMITIDAS_IMAGEM:
            raise forms.ValidationError(
                "Formato não suportado. Use PNG, JPG ou WEBP."
            )
        if arquivo.size > TAMANHO_MAXIMO_IMAGEM:
            raise forms.ValidationError("A imagem deve ter no máximo 5MB.")
        return arquivo

    def clean_ncm(self):
        ncm = (self.cleaned_data.get("ncm") or "").strip()
        if ncm and not ncm.isdigit():
            raise forms.ValidationError("O NCM deve conter apenas dígitos.")
        return ncm

    def clean_cest(self):
        cest = (self.cleaned_data.get("cest") or "").strip()
        if cest and not cest.isdigit():
            raise forms.ValidationError("O CEST deve conter apenas dígitos.")
        return cest

    def clean_cfop(self):
        cfop = (self.cleaned_data.get("cfop") or "").strip()
        if cfop and not cfop.isdigit():
            raise forms.ValidationError("O CFOP deve conter apenas dígitos.")
        return cfop

    def clean_codigo_barras(self):
        codigo = (self.cleaned_data.get("codigo_barras") or "").strip()
        if not codigo:
            return ""
        if not codigo.isdigit():
            raise forms.ValidationError(
                "O código de barras deve conter apenas dígitos."
            )
        try:
            valido = BarcodeService.validate(codigo)
        except BarcodeError:
            valido = False
        if not valido:
            raise forms.ValidationError(
                "EAN-13 inválido: verifique os 13 dígitos e o dígito verificador."
            )
        return codigo

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
            codigo = cleaned.get("codigo_barras")
            if codigo:
                duplicado = (
                    Produto.objects.for_tenant(tenant)
                    .filter(codigo_barras=codigo)
                    .exclude(pk=self.instance.pk)
                    .exists()
                )
                if duplicado:
                    self.add_error(
                        "codigo_barras",
                        "Este código de barras já está em uso no seu tenant.",
                    )
        return cleaned
