"""Importabilidade dos stubs (serão substituídos por testes reais nas fases)."""

import unittest


class StubsTest(unittest.TestCase):
    def test_modulos_importaveis(self):
        import pdv_desktop.print_embedded
        import pdv_desktop.session
        import pdv_desktop.tray
        import pdv_desktop.updater
        import pdv_desktop.window

        self.assertTrue(pdv_desktop.window)
        self.assertTrue(pdv_desktop.tray)
        self.assertTrue(pdv_desktop.session)
        self.assertTrue(pdv_desktop.updater)
        self.assertTrue(pdv_desktop.print_embedded)

    def test_offline_html_incluido_no_pacote(self):
        from pathlib import Path

        import pdv_desktop

        caminho = Path(pdv_desktop.__file__).parent / "offline.html"
        self.assertTrue(caminho.exists())
        texto = caminho.read_text("utf-8")
        self.assertIn("Sem conexão com o servidor", texto)
        self.assertIn("Tentar novamente", texto)
