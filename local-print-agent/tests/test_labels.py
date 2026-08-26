"""Testes da geração EPL2 (Elgin L42 Pro Full) e do ciclo de etiquetas."""

import tempfile
import unittest

from app.agent import PrintAgent
from app.config import Config
from app.labels import (
    gerar_epl2_calibracao,
    gerar_epl2_job,
    mm_para_dots,
)
from app.printer import FakePrinterDevice, PrinterError


def payload(**sobrescritas):
    dados = {
        "versao": 1,
        "tipo": "etiquetas",
        "impressora": "Elgin L42 Pro Full",
        "dimensoes": {
            "largura_etiqueta": "40",
            "altura_etiqueta": "30",
            "gap_horizontal": "2",
            "gap_vertical": "2",
            "margem_esquerda": "2",
            "margem_superior": "1",
            "offset_horizontal": "0",
            "offset_vertical": "0",
            "dpi": 203,
        },
        "mostrar_texto_codigo": True,
        "fileiras": [
            [
                {"nome": "Produto A", "codigo_barras": "789000000001"},
                {"nome": "Produto B", "codigo_barras": "789000000002"},
            ],
            [
                {"nome": "Produto C", "codigo_barras": "789000000003"},
                None,
            ],
        ],
        "resumo": {
            "produtos": 3,
            "etiquetas": 3,
            "fileiras": 2,
            "posicoes_vazias": 1,
        },
    }
    dados.update(sobrescritas)
    return dados


class MmParaDotsTest(unittest.TestCase):
    def test_conversao_203dpi(self):
        self.assertEqual(mm_para_dots("40", 203), 320)
        self.assertEqual(mm_para_dots("2", 203), 16)


class Epl2Test(unittest.TestCase):
    def test_cabecalho_densidade_e_form(self):
        dados = gerar_epl2_job(payload()).decode("latin-1")
        self.assertIn("N\n", dados)
        self.assertIn("D8\n", dados)
        self.assertIn("q655\n", dados)  # 2×40+2mm em dots ≈ 655
        self.assertIn("Q240,16\n", dados)  # 30mm/2mm em dots

    def test_duas_colunas_esquerda_direita(self):
        dados = gerar_epl2_job(payload()).decode("latin-1")
        # Coluna 1: x0 = 2mm = 16 dots; coluna 2: x0 = 44mm ≈ 352 dots.
        self.assertIn("A16,", dados)
        self.assertIn("A352,", dados)
        self.assertIn("B16,", dados)
        self.assertIn("B352,", dados)

    def test_p1_por_etiqueta_inclusive_vazia(self):
        dados = gerar_epl2_job(payload()).decode("latin-1")
        # 3 etiquetas + 1 vazia = 4 avanços (uma posição vazia SEM conteúdo
        # entre o último comando e o P1 da direita da fileira 2).
        self.assertEqual(dados.count("P1"), 4)

    def test_posicao_vazia_sem_conteudo(self):
        dados = gerar_epl2_job(payload()).decode("latin-1")
        # Depois do código do Produto C vem o P1 e nenhum comando novo.
        posicao_c = dados.index('"789000000003"')
        trecho = dados[posicao_c : posicao_c + 80]
        self.assertIn("P1", trecho)
        self.assertNotIn("B352", trecho)

    def test_texto_codigo_abaixo_desativavel(self):
        com_texto = gerar_epl2_job(payload()).decode("latin-1")
        # Com texto: o código aparece no B (barcode) E no A (texto abaixo).
        self.assertGreaterEqual(com_texto.count("789000000001"), 2)
        sem_texto = gerar_epl2_job(payload(mostrar_texto_codigo=False)).decode(
            "latin-1"
        )
        self.assertEqual(sem_texto.count("789000000001"), 1)

    def test_codigo_largo_usa_narrow_1(self):
        dados = gerar_epl2_job(
            payload(
                fileiras=[
                    [
                        {"nome": "P", "codigo_barras": "789999999999999999999"},
                        None,
                    ]
                ]
            )
        ).decode("latin-1")
        # Largura do code128 com narrow=1 aparece em B...,1,2 (narrow,wide).
        self.assertIn(",1,2,N,", dados)

    def test_acentos_preservados_latin1(self):
        dados = gerar_epl2_job(
            payload(
                fileiras=[
                    [{"nome": "Café da Manhã", "codigo_barras": "789000000009"}, None]
                ]
            )
        )
        self.assertIn("Café da Manhã".encode("latin-1"), dados)

    def test_nome_longo_quebra_em_linhas_da_etiqueta(self):
        nome = "X" * 60
        dados = gerar_epl2_job(
            payload(fileiras=[[{"nome": nome, "codigo_barras": "789000000009"}, None]])
        ).decode("latin-1")
        # Máximo 2 linhas de nome; cada linha ≤ 40 caracteres (40mm, fonte 2).
        self.assertNotIn("X" * 41, dados.replace('"', ""))

    def test_calibracao_com_moldura_e_codigo(self):
        dados = gerar_epl2_calibracao(payload()).decode("latin-1")
        self.assertIn("CALIBRACAO", dados)
        self.assertIn("X16,", dados)
        self.assertIn("X352,", dados)
        self.assertIn("7891234567895", dados)
        self.assertEqual(dados.count("P1"), 2)


class FakeClienteEtiquetas:
    def __init__(self, respostas=None):
        self.respostas = list(respostas or [])
        self.reportes = []

    def poll(self, disponivel=True):
        return {"job": None}

    def poll_etiquetas(self, disponivel=True):
        if not disponivel:
            return {"job": None}
        if not self.respostas:
            return {"job": None}
        return self.respostas.pop(0)

    def reportar_resultado(self, *argumentos):
        return {"ok": True}

    def reportar_resultado_etiquetas(self, job_uuid, status, erro=""):
        self.reportes.append((job_uuid, status, erro))
        return {"ok": True}


class CicloEtiquetasTest(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

    def config(self, **sobrescritas):
        valores = {
            "server_url": "http://servidor",
            "state_dir": self.pasta.name,
            "label_device": "/dev/usb/lp1",
        }
        valores.update(sobrescritas)
        return Config(**valores)

    def test_imprime_e_reporta_sucesso(self):
        cliente = FakeClienteEtiquetas(
            [{"job": {"uuid": "et-1", "payload": payload()}}]
        )
        impressora = FakePrinterDevice()
        config = self.config()
        agente = PrintAgent(
            config,
            cliente,
            FakePrinterDevice(),
            impressora_etiquetas=impressora,
        )
        agente.ciclo()
        self.assertEqual(len(impressora.escritas), 1)
        self.assertTrue(impressora.escritas[0].startswith(b"N\nD8"))
        self.assertEqual(cliente.reportes, [("et-1", "PRINTED", "")])

    def test_mesmo_job_nao_reimprime(self):
        cliente = FakeClienteEtiquetas(
            [
                {"job": {"uuid": "et-1", "payload": payload()}},
                {"job": {"uuid": "et-1", "payload": payload()}},
            ]
        )
        impressora = FakePrinterDevice()
        agente = PrintAgent(
            self.config(), cliente, FakePrinterDevice(), impressora_etiquetas=impressora
        )
        agente.ciclo()
        agente.ciclo()
        self.assertEqual(len(impressora.escritas), 1)
        self.assertEqual(
            cliente.reportes, [("et-1", "PRINTED", ""), ("et-1", "PRINTED", "")]
        )

    def test_impressora_desligada_nao_consome(self):
        cliente = FakeClienteEtiquetas(
            [{"job": {"uuid": "et-1", "payload": payload()}}]
        )
        agente = PrintAgent(
            self.config(),
            cliente,
            FakePrinterDevice(),
            impressora_etiquetas=FakePrinterDevice(disponivel=False),
        )
        agente.ciclo()
        self.assertEqual(cliente.reportes, [])
        self.assertEqual(len(cliente.respostas), 1)  # job não consumido

    def test_falha_reporta_erro_e_nao_reimprime(self):
        class Quebrada(FakePrinterDevice):
            def escrever(self, dados):
                raise PrinterError("sem etiquetas")

        cliente = FakeClienteEtiquetas(
            [
                {"job": {"uuid": "et-9", "payload": payload()}},
                {"job": {"uuid": "et-9", "payload": payload()}},
            ]
        )
        agente = PrintAgent(
            self.config(),
            cliente,
            FakePrinterDevice(),
            impressora_etiquetas=Quebrada(),
        )
        agente.ciclo()
        self.assertEqual(cliente.reportes[0][1], "FAILED")
        self.assertIn("sem etiquetas", cliente.reportes[0][2])
        agente.ciclo()
        self.assertEqual(len(cliente.reportes), 1)

    def test_sem_label_device_nao_polla_etiquetas(self):
        cliente = FakeClienteEtiquetas(
            [{"job": {"uuid": "et-1", "payload": payload()}}]
        )
        agente = PrintAgent(
            self.config(label_device=""),
            cliente,
            FakePrinterDevice(),
        )
        agente.ciclo()
        self.assertEqual(len(cliente.respostas), 1)  # nada consumido


if __name__ == "__main__":
    unittest.main()
