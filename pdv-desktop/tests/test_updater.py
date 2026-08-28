"""Stub do updater (Fase 14 implementa testes reais de download/sha256)."""

import unittest


class UpdaterStubTest(unittest.TestCase):
    def test_modulo_importavel(self):
        from pdv_desktop import updater

        self.assertTrue(updater)
