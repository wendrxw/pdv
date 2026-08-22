"""Geração e renderização de códigos de barras EAN-13 internos.

Os códigos gerados aqui usam o prefixo 2 (faixa 200–299), reservada pelo
GS1 para uso interno da loja. NÃO são GTINs oficialmente registrados —
servem apenas para leitura no PDV do próprio tenant.

O código numérico é a fonte da verdade; a imagem é gerada dinamicamente
e nunca armazenada no banco.
"""

import secrets

from .models import Produto


class BarcodeError(Exception):
    """Erro de domínio para códigos de barras inválidos."""


class BarcodeService:
    """Operações sobre códigos de barras EAN-13."""

    PREFIXO_INTERNO = "2"
    TAMANHO = 13

    @staticmethod
    def calculate_check_digit(doze_digitos: str) -> str:
        """Calcula o dígito verificador EAN-13 para 12 dígitos.

        Soma dos dígitos em posições ímpares (1ª, 3ª, ...) × 1 e pares × 3;
        dígito = (10 - soma % 10) % 10.
        """
        if len(doze_digitos) != 12 or not doze_digitos.isdigit():
            raise BarcodeError("Base do código deve conter exatamente 12 dígitos.")
        soma = sum(
            int(digito) * (3 if pos % 2 else 1)
            for pos, digito in enumerate(doze_digitos)
        )
        return str((10 - soma % 10) % 10)

    @classmethod
    def validate(cls, codigo: str) -> bool:
        """Valida formato e dígito verificador de um EAN-13."""
        if not codigo or len(codigo) != cls.TAMANHO or not codigo.isdigit():
            return False
        return (
            cls.calculate_check_digit(codigo[:12]) == codigo[12]
        )

    @classmethod
    def generate(cls, tenant) -> str:
        """Gera um EAN-13 interno único dentro do tenant.

        Usa prefixo 2 + 11 dígitos aleatórios + dígito verificador.
        Códigos de produtos excluídos logicamente não são reutilizados,
        pois a verificação considera todos os produtos do tenant.
        """
        while True:
            corpo = cls.PREFIXO_INTERNO + "".join(
                secrets.choice("0123456789") for _ in range(11)
            )
            codigo = corpo + cls.calculate_check_digit(corpo)
            existe = Produto.objects.for_tenant(tenant).filter(
                codigo_barras=codigo
            ).exists()
            if not existe:
                return codigo


# Tabelas oficiais de codificação EAN-13.
_L = {
    "0": "0001101", "1": "0011001", "2": "0010011", "3": "0111101",
    "4": "0100011", "5": "0110001", "6": "0101111", "7": "0111011",
    "8": "0110111", "9": "0001011",
}
_G = {
    "0": "0100111", "1": "0110011", "2": "0011011", "3": "0100001",
    "4": "0011101", "5": "0111001", "6": "0000101", "7": "0010001",
    "8": "0001001", "9": "0010111",
}
_R = {d: "".join("1" if b == "0" else "0" for b in v) for d, v in _L.items()}
_PARIDADE_PRIMEIRO_DIGITO = {
    "0": "LLLLLL", "1": "LLGLGG", "2": "LLGGLG", "3": "LLGGGL",
    "4": "LGLLGG", "5": "LGGLLG", "6": "LGGGLL", "7": "LGLGLG",
    "8": "LGLGGL", "9": "LGGLGL",
}


class BarcodeRenderer:
    """Renderiza um EAN-13 como SVG (sem dependências externas)."""

    LARGURA_MODULO = 2  # px por módulo
    ALTURA = 90
    MARGEM_X = 10

    @classmethod
    def to_svg(cls, codigo: str) -> str:
        """Gera o SVG do código de barras com dígitos legíveis abaixo."""
        if not BarcodeService.validate(codigo):
            raise BarcodeError("Código de barras inválido para renderização.")

        bits = cls._codificar(codigo)
        largura_total = len(bits) * cls.LARGURA_MODULO + 2 * cls.MARGEM_X
        altura_total = cls.ALTURA + 24

        barras = []
        x = cls.MARGEM_X
        for bit in bits:
            if bit == "1":
                barras.append(
                    f'<rect x="{x}" y="0" width="{cls.LARGURA_MODULO}" '
                    f'height="{cls.ALTURA}"/>'
                )
            x += cls.LARGURA_MODULO

        largura_texto = len(bits) * cls.LARGURA_MODULO
        digitos = (
            f'<text x="{cls.MARGEM_X}" y="{altura_total - 4}" '
            f'font-family="monospace" font-size="14" '
            f'textLength="{largura_texto}">'
            f"{codigo}</text>"
        )
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {largura_total} {altura_total}" '
            f'width="{largura_total}" height="{altura_total}" '
            'shape-rendering="crispEdges" role="img" '
            f'aria-label="Código de barras {codigo}">'
            f'<g fill="#000">{"".join(barras)}{digitos}</g></svg>'
        )

    @classmethod
    def _codificar(cls, codigo: str) -> str:
        """Converte os 13 dígitos na sequência binária de barras EAN-13."""
        primeiro = codigo[0]
        esquerda = codigo[1:7]
        direita = codigo[7:]

        paridade = _PARIDADE_PRIMEIRO_DIGITO[primeiro]
        bits_esquerda = "".join(
            (_L if modo == "L" else _G)[digito]
            for modo, digito in zip(paridade, esquerda, strict=True)
        )
        bits_direita = "".join(_R[digito] for digito in direita)

        guarda = "101"
        separador = "01010"
        return guarda + bits_esquerda + separador + bits_direita + guarda
