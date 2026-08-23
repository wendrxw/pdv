"""Abstração do dispositivo de impressão.

A implementação real (``UsbPrinterDevice``) escreve direto em
``/dev/usb/lp0`` (grupo ``lp``, sem sudo). Os testes usam
``FakePrinterDevice``, que apenas captura os bytes — nenhum teste da
suíte padrão toca a impressora física.
"""

import os
from abc import ABC, abstractmethod


class PrinterError(Exception):
    """Falha ao acessar/escrever no dispositivo de impressão."""


class PrinterDevice(ABC):
    """Interface do dispositivo físico."""

    @abstractmethod
    def disponivel(self):
        """True se a impressora está conectada e gravável."""

    @abstractmethod
    def escrever(self, dados: bytes) -> None:
        """Envia os bytes para a impressora (pode levantar PrinterError)."""


class UsbPrinterDevice(PrinterDevice):
    """Impressora térmica USB via usblp (ex.: /dev/usb/lp0)."""

    def __init__(self, caminho="/dev/usb/lp0"):
        self.caminho = caminho

    def disponivel(self):
        try:
            return os.path.exists(self.caminho) and os.access(self.caminho, os.W_OK)
        except OSError:
            return False

    def escrever(self, dados: bytes) -> None:
        if not self.disponivel():
            raise PrinterError(
                f"Dispositivo indisponível ou sem permissão: {self.caminho}"
            )
        try:
            with open(self.caminho, "wb") as impressora:
                impressora.write(dados)
                impressora.flush()
        except OSError as exc:
            raise PrinterError(f"Falha ao escrever em {self.caminho}: {exc}") from exc


class FakePrinterDevice(PrinterDevice):
    """Dispositivo falso para testes: captura os bytes enviados."""

    def __init__(self, disponivel=True):
        self._disponivel = disponivel
        self.escritas = []
        self.falhas = []

    def disponivel(self):
        return self._disponivel

    def escrever(self, dados: bytes) -> None:
        if not self._disponivel:
            raise PrinterError("Dispositivo indisponível (fake).")
        self.escritas.append(dados)

    def texto_recebido(self, codepage="utf8"):
        """Concatena e decodifica tudo que foi escrito (para asserts)."""
        texto = b"".join(self.escritas)
        return texto.decode(codepage, errors="replace")
