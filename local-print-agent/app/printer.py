"""Abstração do dispositivo de impressão.

Plataformas suportadas:

- **Linux:** ``UsbPrinterDevice`` escreve direto em ``/dev/usb/lp0``
  (grupo ``lp``, sem sudo);
- **Windows:** ``WindowsRawPrinterDevice`` envia os bytes pelo spooler
  (win32print, datatype RAW) usando o NOME da impressora instalada —
  funciona com o driver/utility da Elgin sem transformar os dados EPL2.

Os testes usam ``FakePrinterDevice``, que apenas captura os bytes — nenhum
teste da suíte padrão toca a impressora física.
"""

import os
import sys
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


def criar_dispositivo(identificador: str) -> PrinterDevice:
    """Seleciona o dispositivo conforme a plataforma.

    - Windows: ``identificador`` é o NOME da impressora (ex.: "Elgin L42 PRO");
    - Linux/outros: ``identificador`` é o caminho do dispositivo
      (ex.: ``/dev/usb/lp0``).
    """
    if sys.platform == "win32":
        return WindowsRawPrinterDevice(identificador)
    return UsbPrinterDevice(identificador)


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


class WindowsRawPrinterDevice(PrinterDevice):
    """Impressora Windows via spooler (win32print, datatype RAW).

    O envio em RAW ignora transformações do driver — necessário para
    EPL2 (etiquetas) e ESC/POS (comprovantes) chegarem intactos ao
    firmware.
    """

    def __init__(self, nome):
        self.nome = nome

    def _win32print(self):
        try:
            import win32print
        except ImportError as exc:
            raise PrinterError(
                "pywin32 não está instalado. Execute: pip install pywin32"
            ) from exc
        return win32print

    def disponivel(self):
        win32print = self._win32print()
        try:
            handle = win32print.OpenPrinter(self.nome)
        except Exception:
            return False
        win32print.ClosePrinter(handle)
        return True

    def escrever(self, dados: bytes) -> None:
        win32print = self._win32print()
        try:
            handle = win32print.OpenPrinter(self.nome)
        except Exception as exc:
            raise PrinterError(
                f"Não foi possível abrir a impressora '{self.nome}': {exc}"
            ) from exc
        try:
            try:
                win32print.StartDocPrinter(handle, 1, ("PDV print-agent", None, "RAW"))
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, dados)
                win32print.EndPagePrinter(handle)
                win32print.EndDocPrinter(handle)
            except Exception as exc:
                raise PrinterError(
                    f"Falha ao enviar para '{self.nome}': {exc}"
                ) from exc
        finally:
            win32print.ClosePrinter(handle)


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
