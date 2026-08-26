"""Camada ESC/POS: linhas estilizadas → bytes para a impressora térmica.

Comandos padrão ESC/POS (ESC/POS é o dialeto usado pela esmagadora maioria
das térmicas vendidas no Brasil — Elgin, Bematech, Epson, Tomate etc.). A
camada fica isolada do negócio: ReceiptFormatter produz linhas;
EscPosPrinter codifica comandos; UsbPrinterDevice escreve no dispositivo.

Codificação (acentos):
- ``utf8`` (padrão): envia UTF-8 direto (firmware moderno suporta);
- ``cp850``/``cp860``/``cp1252``/``latin1``: seleciona a tabela na
  impressora com ``ESC t n`` e codifica em 1 byte por caractere — é o
  caminho para impressoras de firmware antigo (ex.: Tomate MDK-080) que
  interpretam UTF-8 como lixo.
- Caracteres fora da tabela (ex.: travessão U+2014) são normalizados
  (→ hífen) antes de codificar, em vez de virar ``?``.

Se a impressora não suportar ESC/POS, desative com PRINTER_ESCPOS=0 e o
agente envia apenas o texto (ainda com o prefixo opcional de seleção de
codepage, controlado por PRINTER_SELECIONAR_CODEPAGE).
"""

INIT = b"\x1b@"
ALINHAR = b"\x1ba"
NEGRITO = b"\x1bE"
CODEPAGE = b"\x1bt"
CORTAR = b"\x1dv"
ALIMENTAR = b"\x1bd"

# Tabelas de 1 byte com acentos de pt-BR (números padrão ESC/POS).
CODEPAGE_ESC_POS = {"cp850": 2, "cp860": 3, "cp1252": 16}
CODEPAGEM_PARA_ENCODING = {
    "utf8": "utf-8",
    "cp850": "cp850",
    "cp860": "cp860",
    "cp1252": "cp1252",
    "latin1": "latin-1",
}

ESTILOS = {"normal", "central", "direita", "negrito", "central_negrito"}

_SUBSTITUICOES = {
    "\u2014": "-",  # travessão
    "\u2013": "-",  # meia-risca
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
}


def normalizar_texto(texto):
    """Substitui caracteres sem representação nas codepages alvo."""
    for original, substituto in _SUBSTITUICOES.items():
        texto = texto.replace(original, substituto)
    return texto


def selecionar_codepage(codepage):
    """Bytes do comando de seleção de codepage (vazio para utf8/latin1)."""
    numero = CODEPAGE_ESC_POS.get(codepage)
    if numero is None:
        return b""
    return CODEPAGE + bytes([numero])


class EscPosPrinter:
    """Monta um documento ESC/POS a partir de linhas estilizadas."""

    def __init__(self, codepage="utf8", cortar_parcial=True):
        self.codepage = codepage
        self.cortar_parcial = bool(cortar_parcial)

    def _codificar(self, texto):
        encoding = CODEPAGEM_PARA_ENCODING.get(self.codepage, "utf-8")
        return normalizar_texto(str(texto)).encode(encoding, errors="replace")

    def inicializar(self):
        comando = bytearray(INIT)
        comando += selecionar_codepage(self.codepage)
        return bytes(comando)

    def alinhar(self, estilo):
        if estilo in ("central", "central_negrito"):
            return ALINHAR + b"\x01"
        if estilo == "direita":
            return ALINHAR + b"\x02"
        return ALINHAR + b"\x00"

    def negrito(self, estilo):
        if estilo in ("negrito", "central_negrito"):
            return NEGRITO + b"\x01"
        return NEGRITO + b"\x00"

    def render(self, linhas, alimentar_antes_de_cortar=8):
        """``linhas``: lista de (texto, estilo) → bytes completos do job.

        ``alimentar_antes_de_cortar`` são as linhas em branco no fim, para
        que o corte não caia sobre o conteúdo impresso.
        """
        saida = bytearray()
        saida += self.inicializar()
        for texto, estilo in linhas:
            if estilo not in ESTILOS:
                estilo = "normal"
            saida += self.alinhar(estilo)
            saida += self.negrito(estilo)
            saida += self._codificar(texto)
            saida += b"\n"
        saida += ALIMENTAR + bytes([alimentar_antes_de_cortar])
        modo_corte = 1 if self.cortar_parcial else 0
        saida += CORTAR + bytes([66, modo_corte])
        return bytes(saida)
