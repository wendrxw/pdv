from django.test import TestCase

from ..chave import (
    MODELO_NFCE,
    ChaveAcesso,
    ChaveInvalida,
    calcular_dv,
    decompor,
    validar,
)

# Base de 43 dígitos com DV calculado à mão (soma 550, resto 0 → DV 0).
BASE_VERIFICADA = "3526081234567800019565001000000123100000042"


class DvTest(TestCase):
    def test_vetor_calculado_a_mao(self):
        self.assertEqual(calcular_dv(BASE_VERIFICADA), 0)

    def test_base_toda_zeros(self):
        self.assertEqual(calcular_dv("0" * 43), 0)

    def test_base_curta_rejeitada(self):
        with self.assertRaises(ChaveInvalida):
            calcular_dv("123")

    def test_base_nao_numerica_rejeitada(self):
        with self.assertRaises(ChaveInvalida):
            calcular_dv("a" * 43)


class ChaveAcessoTest(TestCase):
    def test_chave_completa_valida(self):
        chave = ChaveAcesso(
            cuf="35",
            aamm="2608",
            cnpj="12345678000195",
            serie=1,
            numero=123,
            cnf="00000042",
        )
        self.assertEqual(len(chave.completa), 44)
        self.assertTrue(validar(chave.completa))
        self.assertEqual(chave.base, BASE_VERIFICADA)
        self.assertEqual(chave.dv, 0)

    def test_modelo_65_fixo(self):
        chave = ChaveAcesso(cuf="35", aamm="2608", cnpj="1" * 14)
        self.assertEqual(chave.modelo, MODELO_NFCE)
        self.assertIn("65", chave.completa)

    def test_cnpj_tamanho_errado_rejeitado(self):
        with self.assertRaises(ChaveInvalida):
            ChaveAcesso(cuf="35", aamm="2608", cnpj="123")

    def test_serie_fora_do_range(self):
        with self.assertRaises(ChaveInvalida):
            ChaveAcesso(cuf="35", aamm="2608", cnpj="1" * 14, serie=1000)

    def test_numero_zero_rejeitado(self):
        with self.assertRaises(ChaveInvalida):
            ChaveAcesso(cuf="35", aamm="2608", cnpj="1" * 14, numero=0)


class ValidacaoEDecomposicaoTest(TestCase):
    def test_validar_rejeita_tamanho(self):
        self.assertFalse(validar("123"))

    def test_validar_rejeita_nao_numerico(self):
        self.assertFalse(validar("x" * 44))

    def test_dv_errado_invalido(self):
        chave = ChaveAcesso(cuf="35", aamm="2608", cnpj="1" * 14)
        adulterada = chave.completa[:-1] + (
            "0" if chave.dv != 0 else "1"
        )
        self.assertFalse(validar(adulterada))

    def test_decompor_roundtrip(self):
        chave = ChaveAcesso(
            cuf="35", aamm="2608", cnpj="12345678000195", numero=987654321
        )
        campos = decompor(chave.completa)
        self.assertEqual(campos["cuf"], "35")
        self.assertEqual(campos["cnpj"], "12345678000195")
        self.assertEqual(campos["numero"], 987654321)
        self.assertEqual(campos["dv"], chave.dv)

    def test_da_string_reconstrói_e_confere_dv(self):
        original = ChaveAcesso(
            cuf="35", aamm="2608", cnpj="12345678000195", numero=555
        )
        reconstruida = ChaveAcesso.da_string(original.completa)
        self.assertEqual(reconstruida.completa, original.completa)

    def test_da_string_rejeita_invalida(self):
        with self.assertRaises(ChaveInvalida):
            ChaveAcesso.da_string("0" * 44)
