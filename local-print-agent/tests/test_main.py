"""Testes das páginas de diagnóstico (test e codepage-test)."""

import unittest

from app.config import Config
from app.main import montar_pagina_codepage, montar_pagina_teste


class PaginaTesteTest(unittest.TestCase):
    def config(self, **sobrescritas):
        valores = {"server_url": "http://servidor", "device": "/dev/usb/lp0"}
        valores.update(sobrescritas)
        return Config(**valores)

    def test_pagina_teste_em_modo_texto_com_cp850(self):
        dados = montar_pagina_teste(self.config(escpos=False, codepage="cp850"))
        self.assertTrue(dados.startswith(b"\x1bt\x02"))
        self.assertIn("ÁÉÍÓÚÇ".encode("cp850"), dados)

    def test_pagina_teste_em_escpos(self):
        dados = montar_pagina_teste(self.config(escpos=True, codepage="cp850"))
        self.assertTrue(dados.startswith(b"\x1b@"))
        self.assertIn(b"\x1bt\x02", dados)

    def test_pagina_codepage_rotula_todas_as_candidatas(self):
        dados = montar_pagina_codepage(self.config())
        self.assertIn(b"UTF-8 (padrao):", dados)
        self.assertIn(b"CP850:", dados)
        self.assertIn(b"CP860 (portugues):", dados)
        self.assertIn(b"CP1252 (Windows):", dados)
        self.assertIn(b"\x1bt\x02", dados)
        self.assertIn(b"\x1bt\x03", dados)
        self.assertIn(b"\x1bt\x10", dados)
        self.assertIn("Café".encode("utf-8"), dados)
        self.assertIn("Café".encode("cp850"), dados)

    def test_pagina_codepage_tem_folga_no_fim(self):
        config = self.config(alimentacao_final=5)
        dados = montar_pagina_codepage(config)
        self.assertTrue(dados.endswith(b"\n" * 5))


if __name__ == "__main__":
    unittest.main()
