"""Testes do dispositivo Windows (spooler RAW via win32print fake)."""

import sys
import types
import unittest
from unittest import mock

from app.printer import (
    PrinterError,
    WindowsRawPrinterDevice,
    criar_dispositivo,
)


def _injetar_win32print(escritas):
    """Fake do módulo win32print para os testes (não existe no Linux)."""
    fake = types.ModuleType("win32print")
    handle = object()

    def open_printer(nome):
        return handle

    def close_printer(h):
        pass

    def start_doc_printer(h, nivel, docinfo):
        escritas.append(("doc", docinfo))

    def start_page_printer(h):
        escritas.append(("page", None))

    def write_printer(h, dados):
        escritas.append(("dados", dados))

    def end_page_printer(h):
        escritas.append(("endpage", None))

    def end_doc_printer(h):
        escritas.append(("enddoc", None))

    fake.OpenPrinter = open_printer
    fake.ClosePrinter = close_printer
    fake.StartDocPrinter = start_doc_printer
    fake.StartPagePrinter = start_page_printer
    fake.WritePrinter = write_printer
    fake.EndPagePrinter = end_page_printer
    fake.EndDocPrinter = end_doc_printer
    sys.modules["win32print"] = fake
    return fake


class WindowsRawPrinterDeviceTest(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("win32print", None)

    def test_escrever_envia_raw_com_nome_da_impressora(self):
        escritas = []
        _injetar_win32print(escritas)
        dispositivo = WindowsRawPrinterDevice("Elgin L42 PRO")
        self.assertTrue(dispositivo.disponivel())
        dispositivo.escrever(b"\x1b@EPL2")
        self.assertIn(("dados", b"\x1b@EPL2"), escritas)
        docinfo = [e for e in escritas if e[0] == "doc"][0][1]
        self.assertEqual(docinfo[2], "RAW")

    def test_disponivel_falso_quando_impressora_nao_existe(self):
        fake = _injetar_win32print([])

        def open_printer(nome):
            raise Exception("impressora não encontrada")

        fake.OpenPrinter = open_printer
        dispositivo = WindowsRawPrinterDevice("Inexistente")
        self.assertFalse(dispositivo.disponivel())

    def test_erro_de_escrita_vira_printer_error(self):
        fake = _injetar_win32print([])

        def write_printer(h, dados):
            raise Exception("filha de impressão cheia")

        fake.WritePrinter = write_printer
        dispositivo = WindowsRawPrinterDevice("Elgin L42 PRO")
        with self.assertRaises(PrinterError):
            dispositivo.escrever(b"x")

    def test_sem_pywin32_instalado_avisa(self):
        with mock.patch.dict(sys.modules, {"win32print": None}):
            dispositivo = WindowsRawPrinterDevice("Elgin L42 PRO")
            with self.assertRaises(PrinterError):
                dispositivo.escrever(b"x")

    def test_factory_escolhe_usb_no_linux(self):
        with mock.patch.object(sys, "platform", "linux"):
            dispositivo = criar_dispositivo("/dev/usb/lp0")
            from app.printer import UsbPrinterDevice

            self.assertIsInstance(dispositivo, UsbPrinterDevice)

    def test_factory_escolhe_windows_no_win32(self):
        with mock.patch.object(sys, "platform", "win32"):
            dispositivo = criar_dispositivo("Elgin L42 PRO")
            self.assertIsInstance(dispositivo, WindowsRawPrinterDevice)


if __name__ == "__main__":
    unittest.main()
