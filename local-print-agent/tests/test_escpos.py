"""Testes da camada ESC/POS e do dispositivo falso."""

import os
import tempfile
import unittest

from app.escpos import EscPosPrinter
from app.printer import FakePrinterDevice, PrinterError, UsbPrinterDevice


class EscPosTest(unittest.TestCase):
    def test_inicializa_com_init(self):
        impressora = EscPosPrinter()
        dados = impressora.render([])
        self.assertTrue(dados.startswith(b"\x1b@"))

    def test_alinhamento_e_negrito(self):
        impressora = EscPosPrinter()
        dados = impressora.render(
            [
                ("esquerda", "normal"),
                ("meio", "central"),
                ("fim", "direita"),
                ("forte", "negrito"),
            ]
        )
        self.assertIn(b"\x1ba\x00", dados)
        self.assertIn(b"\x1ba\x01", dados)
        self.assertIn(b"\x1ba\x02", dados)
        self.assertIn(b"\x1bE\x01", dados)
        self.assertIn(b"\x1bE\x00", dados)

    def test_termina_com_alimentacao_e_corte(self):
        impressora = EscPosPrinter(cortar_parcial=True)
        dados = impressora.render([("linha", "normal")])
        # Padrão: 8 linhas de folga antes do corte (folga para o rasgo).
        self.assertTrue(dados.endswith(b"\x1bd\x08\x1dv\x42\x01"))
        total = EscPosPrinter(cortar_parcial=False).render(
            [("a", "normal")], alimentar_antes_de_cortar=3
        )
        self.assertTrue(total.endswith(b"\x1bd\x03\x1dv\x42\x00"))

    def test_utf8_com_acentos(self):
        impressora = EscPosPrinter(codepage="utf8")
        dados = impressora.render([("Café — Água", "normal")])
        self.assertIn("Café — Água".encode("utf-8"), dados)

    def test_cp850_seleciona_codepage_e_codifica(self):
        impressora = EscPosPrinter(codepage="cp850")
        dados = impressora.render([("Café", "normal")])
        self.assertIn(b"\x1bt\x02", dados)
        self.assertIn("Café".encode("cp850"), dados)


class FakePrinterDeviceTest(unittest.TestCase):
    def test_captura_bytes(self):
        dispositivo = FakePrinterDevice()
        dispositivo.escrever(b"abc")
        dispositivo.escrever(b"def")
        self.assertEqual(dispositivo.escritas, [b"abc", b"def"])
        self.assertEqual(dispositivo.texto_recebido(), "abcdef")

    def test_indisponivel_levanta_erro(self):
        dispositivo = FakePrinterDevice(disponivel=False)
        with self.assertRaises(PrinterError):
            dispositivo.escrever(b"x")


class UsbPrinterDeviceTest(unittest.TestCase):
    def test_escreve_no_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "lp0")
            open(caminho, "w").close()
            os.chmod(caminho, 0o600)
            dispositivo = UsbPrinterDevice(caminho)
            self.assertTrue(dispositivo.disponivel())
            dispositivo.escrever(b"TESTE\n")
            with open(caminho, "rb") as arquivo:
                self.assertEqual(arquivo.read(), b"TESTE\n")

    def test_inexistente_indisponivel(self):
        dispositivo = UsbPrinterDevice("/caminho/que/nao/existe")
        self.assertFalse(dispositivo.disponivel())
        with self.assertRaises(PrinterError):
            dispositivo.escrever(b"x")


if __name__ == "__main__":
    unittest.main()
