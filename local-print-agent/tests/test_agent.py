"""Testes do núcleo do agente: deduplicação, indisponibilidade e retry."""

import json
import tempfile
import unittest

from app.agent import PrintAgent, salvar_credencial
from app.client import AuthError
from app.config import Config
from app.printer import FakePrinterDevice, PrinterError


def payload_venda():
    return {
        "largura_mm": "58",
        "cabecalho": {"nome": "Loja Teste", "cnpj": "", "endereco": "", "telefone": ""},
        "venda": {"numero": 1, "data": "2026-08-23T17:42:00-03:00"},
        "itens": [
            {
                "nome": "Café",
                "quantidade": "1.000",
                "preco_unitario": "3.50",
                "subtotal": "3.50",
            }
        ],
        "totais": {"subtotal": "3.50", "desconto": "0.00", "total": "3.50"},
        "pagamentos": [{"forma": "Dinheiro", "valor": "3.50"}],
        "valor_recebido": "3.50",
        "troco": "0.00",
        "mensagem_final": "Volte sempre!",
    }


class FakeCliente:
    def __init__(self, respostas=None):
        self.respostas = list(respostas or [])
        self.polls = []
        self.reportes = []

    def poll(self, disponivel=True):
        self.polls.append(disponivel)
        if not self.respostas:
            return {"job": None}
        return self.respostas.pop(0)

    def reportar_resultado(self, job_uuid, status, erro=""):
        self.reportes.append((job_uuid, status, erro))
        return {"ok": True}


class BaseAgentTest(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.config = Config(
            server_url="http://servidor",
            device="/dev/usb/lp0",
            poll_interval=0,
            state_dir=self.pasta.name,
        )
        self.impressora = FakePrinterDevice()

    def montar(self, cliente):
        return PrintAgent(self.config, cliente, self.impressora)


class ImpressaoTest(BaseAgentTest):
    def test_imprime_e_reporta_sucesso(self):
        cliente = FakeCliente([{"job": {"uuid": "job-1", "payload": payload_venda()}}])
        agente = self.montar(cliente)
        self.assertEqual(agente.ciclo(), "impresso")
        self.assertEqual(len(self.impressora.escritas), 1)
        self.assertIn("Loja Teste", self.impressora.texto_recebido())
        self.assertEqual(cliente.reportes, [("job-1", "PRINTED", "")])

    def test_mesmo_job_nao_reimprime(self):
        cliente = FakeCliente(
            [
                {"job": {"uuid": "job-1", "payload": payload_venda()}},
                {"job": {"uuid": "job-1", "payload": payload_venda()}},
            ]
        )
        agente = self.montar(cliente)
        agente.ciclo()
        self.assertEqual(agente.ciclo(), "ignorado")
        # Só uma escrita na impressora; reporte de sucesso reconfirmado.
        self.assertEqual(len(self.impressora.escritas), 1)
        self.assertEqual(
            cliente.reportes,
            [("job-1", "PRINTED", ""), ("job-1", "PRINTED", "")],
        )

    def test_dedupe_persiste_entre_processos(self):
        cliente = FakeCliente([{"job": {"uuid": "job-1", "payload": payload_venda()}}])
        agente = self.montar(cliente)
        agente.ciclo()
        # "Novo processo": mesmo diretório de estado, impressora zerada.
        novo_cliente = FakeCliente(
            [{"job": {"uuid": "job-1", "payload": payload_venda()}}]
        )
        novo_agente = PrintAgent(self.config, novo_cliente, FakePrinterDevice())
        self.assertEqual(novo_agente.ciclo(), "ignorado")
        self.assertEqual(novo_cliente.reportes, [("job-1", "PRINTED", "")])

    def test_impressora_indisponivel_nao_consome_job(self):
        cliente = FakeCliente([])
        self.impressora = FakePrinterDevice(disponivel=False)
        agente = self.montar(cliente)
        self.assertEqual(agente.ciclo(), "ocioso")
        self.assertEqual(cliente.polls, [False])
        self.assertEqual(len(self.impressora.escritas), 0)

    def test_falha_reporta_erro_e_nao_reimprime_sozinho(self):
        class Quebrada(FakePrinterDevice):
            def escrever(self, dados):
                raise PrinterError("Sem papel")

        cliente = FakeCliente(
            [
                {"job": {"uuid": "job-9", "payload": payload_venda()}},
                {"job": {"uuid": "job-9", "payload": payload_venda()}},
            ]
        )
        agente = PrintAgent(self.config, cliente, Quebrada(disponivel=True))
        agente.ciclo()
        self.assertEqual(cliente.reportes[0][0], "job-9")
        self.assertEqual(cliente.reportes[0][1], "FAILED")
        self.assertIn("Sem papel", cliente.reportes[0][2])
        # Segunda entrega do mesmo job: não tenta imprimir de novo.
        self.assertEqual(agente.ciclo(), "ignorado")
        self.assertEqual(len(cliente.reportes), 1)

    def test_auth_error_propaga(self):
        class Recusa(FakeCliente):
            def poll(self, disponivel=True):
                raise AuthError("credencial inválida")

        agente = self.montar(Recusa())
        with self.assertRaises(AuthError):
            agente.ciclo()


class CredencialTest(unittest.TestCase):
    def test_salva_e_carrega_credencial(self):
        with tempfile.TemporaryDirectory() as pasta:
            config = Config(server_url="http://servidor", state_dir=pasta)
            from app.agent import carregar_credencial

            salvar_credencial(
                config,
                {"estacao": "uuid-1", "token": "tok", "nome": "Caixa 01"},
            )
            self.assertEqual(carregar_credencial(config)["token"], "tok")
            with open(config.caminho_credencial, encoding="utf-8") as arquivo:
                self.assertIn("tok", json.load(arquivo)["token"])


if __name__ == "__main__":
    unittest.main()
