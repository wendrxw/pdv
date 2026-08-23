"""Camada ESC/POS: linhas estilizadas → bytes para a impressora térmica.

Comandos padrão ESC/POS (ESC/POS é o dialeto usado pela esmagadora maioria
das térmicas vendidas no Brasil — Elgin, Bematech, Epson etc.). A camada
fica isolada do negócio: ReceiptFormatter produz linhas; EscPosPrinter
codifica comandos; UsbPrinterDevice escreve no dispositivo.

Codificação:
- ``utf8`` (padrão): envia UTF-8 direto (firmware moderno suporta);
- ``cp850``: seleciona a tabela CP850 (ESC t 2), com acentos de pt-BR.

Se a impressora não suportar ESC/POS, desative com PRINTER_ESCPOS=0 e o
agente envia apenas o texto puro (sem comandos de realce/corte).
"""

INIT = b"\x1b@"
ALINHAR = b"\x1ba"
NEGRITO = b"\x1bE"
CODEPAGE = b"\x1bt"
CORTAR = b"\x1dv"
ALIMENTAR = b"\x1bd"

CP850 = 2

ESTILOS = {"normal", "central", "direita", "negrito", "central_negrito"}


class EscPosPrinter:
    """Monta um documento ESC/POS a partir de linhas estilizadas."""

    def __init__(self, codepage="utf8", cortar_parcial=True):
        self.codepage = codepage
        self.cortar_parcial = bool(cortar_parcial)

    def _codificar(self, texto):
        if self.codepage == "cp850":
            return str(texto).encode("cp850", errors="replace")
        return str(texto).encode("utf-8", errors="replace")

    def inicializar(self):
        comando = bytearray(INIT)
        if self.codepage == "cp850":
            comando += CODEPAGE + bytes([CP850])
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
