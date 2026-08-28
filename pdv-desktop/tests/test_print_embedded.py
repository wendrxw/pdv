"""Stub da impressão embutida (Fase 10 reutiliza local-print-agent/app)."""

import unittest


class PrintEmbeddedStubTest(unittest.TestCase):
    def test_modulo_importavel(self):
        from pdv_desktop import print_embedded

        self.assertTrue(print_embedded)
