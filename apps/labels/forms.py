"""Formulários do módulo de etiquetas."""

from django import forms

from .models import ConfiguracaoEtiqueta


class ConfiguracaoEtiquetaForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoEtiqueta
        fields = [
            "nome_impressora",
            "dpi",
            "largura_etiqueta",
            "altura_etiqueta",
            "gap_horizontal",
            "gap_vertical",
            "margem_esquerda",
            "margem_superior",
            "offset_horizontal",
            "offset_vertical",
            "mostrar_texto_codigo",
            "quantidade_padrao",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in (
            "nome_impressora",
            "dpi",
            "largura_etiqueta",
            "altura_etiqueta",
            "gap_horizontal",
            "gap_vertical",
            "margem_esquerda",
            "margem_superior",
            "offset_horizontal",
            "offset_vertical",
            "quantidade_padrao",
        ):
            self.fields[campo].widget.attrs.setdefault(
                "class",
                "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm",
            )
