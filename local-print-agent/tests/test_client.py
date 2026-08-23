"""Testes do cliente HTTP (urllib injetada, sem rede)."""

import json
import unittest

from app.client import AuthError, PrintAgentClient, PrintAgentClientError


class FakeResposta:
    def __init__(self, corpo, status=200):
        self._corpo = corpo
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *argumentos):
        return False

    def read(self):
        return self._corpo

    def getcode(self):
        return self.status


class FakeAbridor:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.requisicoes = []

    def __call__(self, requisicao, timeout=None):
        self.requisicoes.append(requisicao)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def requisicao_para_dict(requisicao):
    return {
        "url": requisicao.full_url,
        "metodo": requisicao.get_method(),
        "cabecalhos": dict(requisicao.header_items()),
        "corpo": json.loads(requisicao.data or b"{}"),
    }


class PrintAgentClientTest(unittest.TestCase):
    def test_pair_envia_codigo(self):
        abridor = FakeAbridor(
            [
                FakeResposta(
                    json.dumps(
                        {"estacao": "uuid-1", "token": "tok", "nome": "Caixa 01"}
                    ).encode()
                )
            ]
        )
        cliente = PrintAgentClient("http://servidor", abridor=abridor)
        resposta = cliente.pair("ABC123")
        self.assertEqual(resposta["token"], "tok")
        pedido = requisicao_para_dict(abridor.requisicoes[0])
        self.assertEqual(pedido["url"], "http://servidor/api/print-agent/pair/")
        self.assertEqual(pedido["corpo"], {"codigo": "ABC123"})

    def test_poll_envia_cabecalhos_de_autenticacao(self):
        abridor = FakeAbridor([FakeResposta(b'{"job": null}')])
        cliente = PrintAgentClient(
            "http://servidor",
            estacao_uuid="uuid-1",
            token="tok",
            abridor=abridor,
        )
        cliente.poll(disponivel=False)
        pedido = requisicao_para_dict(abridor.requisicoes[0])
        self.assertEqual(pedido["cabecalhos"]["X-station-uuid"], "uuid-1")
        self.assertEqual(pedido["cabecalhos"]["X-station-token"], "tok")
        self.assertEqual(pedido["corpo"], {"disponivel": False})

    def test_reportar_resultado(self):
        abridor = FakeAbridor([FakeResposta(b'{"ok": true}')])
        cliente = PrintAgentClient(
            "http://servidor",
            estacao_uuid="uuid-1",
            token="tok",
            abridor=abridor,
        )
        cliente.reportar_resultado("job-1", "FAILED", erro="Sem papel")
        pedido = requisicao_para_dict(abridor.requisicoes[0])
        self.assertTrue(
            pedido["url"].endswith("/api/print-agent/jobs/job-1/resultado/")
        )
        self.assertEqual(
            pedido["corpo"],
            {"status": "FAILED", "erro": "Sem papel"},
        )

    def test_401_levanta_auth_error(self):
        abridor = FakeAbridor(
            [
                FakeResposta(
                    json.dumps({"erro": "Credencial da estação inválida."}).encode(
                        "utf-8"
                    ),
                    401,
                )
            ]
        )
        cliente = PrintAgentClient("http://servidor", abridor=abridor)
        with self.assertRaises(AuthError):
            cliente.poll()

    def test_erro_de_rede_levanta_client_error(self):
        abridor = FakeAbridor([OSError("recusado")])
        cliente = PrintAgentClient("http://servidor", abridor=abridor)
        with self.assertRaises(PrintAgentClientError):
            cliente.poll()


if __name__ == "__main__":
    unittest.main()
