"""Servidor simulado para testar o print-agent.exe no CI Windows.

Responde /api/print-agent/pair/ com uma credencial fake. Usado pelo
workflow build-windows-agent para executar o BINÁRIO de verdade e
verificar o fluxo de pareamento ponta a ponta.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORTA = 8791


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        corpo = self.rfile.read(tamanho)
        dados = json.loads(corpo or b"{}")
        if self.path == "/api/print-agent/pair/":
            if dados.get("codigo") == "TESTE123":
                resposta = {
                    "estacao": "aaaaaaaa-1111-4bbb-8ccc-123456789abc",
                    "token": "token-de-teste-e2e",
                    "nome": "Estação CI",
                    "loja": "Loja CI",
                }
                self._responder(200, resposta)
            else:
                self._responder(400, {"erro": "Código de pareamento inválido."})
        elif self.path == "/api/print-agent/poll/":
            self._responder(200, {"job": None, "disponivel": True})
        elif self.path.endswith("/api/print-agent/etiquetas/poll/"):
            self._responder(200, {"job": None, "disponivel": True})
        else:
            self._responder(404, {"erro": "não encontrado"})

    def _responder(self, status, dados):
        corpo = json.dumps(dados).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args):
        pass


def main():
    servidor = HTTPServer(("127.0.0.1", PORTA), Handler)
    print(f"mock na porta {PORTA}", flush=True)
    servidor.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
