"""Testes de formatação do comprovante (sem impressora física)."""

import unittest

from app.receipt import (
    formatar_cnpj,
    formatar_dados_comprovante,
    formatar_moeda,
    formatar_quantidade,
    largura_papel,
    quebrar_linha,
)


def payload(**sobrescritas):
    dados = {
        "largura_mm": "58",
        "cabecalho": {
            "nome": "Minha Loja",
            "cnpj": "00000000000100",
            "endereco": "Rua das Flores, 100, Centro, São Paulo-SP",
            "telefone": "(11) 99999-9999",
        },
        "venda": {"numero": 123, "data": "2026-08-23T17:42:00-03:00"},
        "itens": [
            {
                "nome": "Coca-Cola 350ml",
                "quantidade": "2.000",
                "preco_unitario": "5.00",
                "subtotal": "10.00",
            },
            {
                "nome": "Salgadinho",
                "quantidade": "1.000",
                "preco_unitario": "8.50",
                "subtotal": "8.50",
            },
        ],
        "totais": {"subtotal": "18.50", "desconto": "0.00", "total": "18.50"},
        "pagamentos": [{"forma": "PIX", "valor": "18.50"}],
        "valor_recebido": "0.00",
        "troco": "0.00",
        "mensagem_final": "Obrigado pela preferência!",
    }
    dados.update(sobrescritas)
    return dados


def texto(linhas):
    return "\n".join(linha for linha, _estilo in linhas)


class FormatarMoedaTest(unittest.TestCase):
    def test_centavos(self):
        self.assertEqual(formatar_moeda("5.00"), "5,00")
        self.assertEqual(formatar_moeda("30.50"), "30,50")
        self.assertEqual(formatar_moeda("8.05"), "8,05")

    def test_milhares(self):
        self.assertEqual(formatar_moeda("1234.56"), "1.234,56")

    def test_invalido_nao_explode(self):
        self.assertEqual(formatar_moeda("abc"), "0,00")


class FormatarQuantidadeTest(unittest.TestCase):
    def test_inteiro(self):
        self.assertEqual(formatar_quantidade("2.000"), "2")

    def test_fracionada(self):
        self.assertEqual(formatar_quantidade("2.500"), "2,5")
        self.assertEqual(formatar_quantidade("0.250"), "0,25")


class FormatarCnpjTest(unittest.TestCase):
    def test_mascara(self):
        self.assertEqual(formatar_cnpj("00000000000100"), "00.000.000/0001-00")

    def test_vazio_permanece_vazio(self):
        self.assertEqual(formatar_cnpj(""), "")


class LarguraPapelTest(unittest.TestCase):
    def test_58_e_80(self):
        self.assertEqual(largura_papel("58"), 32)
        self.assertEqual(largura_papel("80"), 48)
        self.assertEqual(largura_papel("999"), 32)


class ComprovanteTest(unittest.TestCase):
    def test_produto_unico(self):
        dados = payload(itens=payload()["itens"][:1])
        resultado = texto(formatar_dados_comprovante(dados))
        self.assertIn("MINHA LOJA", resultado.upper())
        self.assertIn("CNPJ: 00.000.000/0001-00", resultado)
        self.assertIn("Venda: #000123", resultado)
        self.assertIn("Data: 23/08/2026 17:42", resultado)
        self.assertIn("Coca-Cola 350ml", resultado)
        self.assertIn("2 x 5,00", resultado)
        self.assertIn("10,00", resultado)
        self.assertIn("PIX 18,50", resultado)
        self.assertIn("Obrigado pela preferência!", resultado)

    def test_varios_produtos(self):
        resultado = texto(formatar_dados_comprovante(payload()))
        self.assertIn("Coca-Cola 350ml", resultado)
        self.assertIn("Salgadinho", resultado)

    def test_valores_com_centavos(self):
        dados = payload(
            itens=[
                {
                    "nome": "Chocolate",
                    "quantidade": "3.000",
                    "preco_unitario": "4.00",
                    "subtotal": "12.00",
                }
            ],
            totais={"subtotal": "12.00", "desconto": "0.00", "total": "12.00"},
            pagamentos=[{"forma": "Dinheiro", "valor": "12.00"}],
        )
        resultado = texto(formatar_dados_comprovante(dados))
        self.assertIn("3 x 4,00", resultado)
        self.assertIn("12,00", resultado)

    def test_desconto_exibido(self):
        dados = payload(
            totais={"subtotal": "18.50", "desconto": "2.00", "total": "16.50"}
        )
        resultado = texto(formatar_dados_comprovante(dados))
        self.assertIn("DESCONTO", resultado)
        self.assertIn("2,00", resultado)

    def test_troco_exibido_quando_positivo(self):
        dados = payload(
            pagamentos=[{"forma": "Dinheiro", "valor": "18.50"}],
            valor_recebido="20.00",
            troco="1.50",
        )
        resultado = texto(formatar_dados_comprovante(dados))
        self.assertIn("RECEBIDO", resultado)
        self.assertIn("20,00", resultado)
        self.assertIn("TROCO", resultado)
        self.assertIn("1,50", resultado)

    def test_acentos_e_utf8(self):
        dados = payload(
            itens=[
                {
                    "nome": "Café da Manhã — Água com Gás 500ml",
                    "quantidade": "1.000",
                    "preco_unitario": "3.50",
                    "subtotal": "3.50",
                }
            ],
            mensagem_final="Volte sempre! ☺",
        )
        resultado = texto(formatar_dados_comprovante(dados))
        self.assertIn("Café da Manhã", resultado)
        self.assertIn("Água com Gás", resultado)
        self.assertIn("Volte sempre! ☺", resultado)

    def test_nome_muito_longo_quebra_sem_estourar_58(self):
        nome = "Produto Super Especial Importado Edição Limitada Coletor 2026"
        dados = payload(
            itens=[
                {
                    "nome": nome,
                    "quantidade": "1.000",
                    "preco_unitario": "9.90",
                    "subtotal": "9.90",
                }
            ]
        )
        for linha, _estilo in formatar_dados_comprovante(dados):
            self.assertLessEqual(len(linha), 32)

    def test_nome_muito_longo_quebra_sem_estourar_80(self):
        nome = "X" * 100
        dados = payload(
            largura_mm="80",
            itens=[
                {
                    "nome": nome,
                    "quantidade": "1.000",
                    "preco_unitario": "9.90",
                    "subtotal": "9.90",
                }
            ],
        )
        for linha, _estilo in formatar_dados_comprovante(dados):
            self.assertLessEqual(len(linha), 48)

    def test_sem_mensagem_final_nao_quebra(self):
        dados = payload(mensagem_final="")
        resultado = texto(formatar_dados_comprovante(dados))
        self.assertNotIn("Obrigado", resultado)

    def test_quebrar_linha(self):
        self.assertEqual(quebrar_linha("abcdef", 3), ["abc", "def"])
        self.assertEqual(quebrar_linha("", 5), [""])


if __name__ == "__main__":
    unittest.main()
