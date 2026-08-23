"""Cliente HTTP do agente (stdlib urllib — zero dependências).

O agente abre a conexão de SAÍDA com o servidor (funciona atrás de
NAT/CGNAT/firewall). Autenticação por estação via cabeçalhos
``X-Station-UUID`` e ``X-Station-Token``.
"""

import json
import urllib.error
import urllib.request


class PrintAgentClientError(Exception):
    """Erro de comunicação ou resposta inesperada do servidor."""


class AuthError(PrintAgentClientError):
    """Credencial recusada pelo servidor."""


class PrintAgentClient:
    """Fala com a API /api/print-agent/ do Django."""

    def __init__(
        self,
        base_url,
        estacao_uuid=None,
        token=None,
        timeout=30,
        abridor=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.estacao_uuid = estacao_uuid
        self.token = token
        self.timeout = timeout
        # Injeção para testes (default: urllib real).
        self._abridor = abridor or urllib.request.urlopen

    def _cabecalhos(self):
        cabecalhos = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.estacao_uuid and self.token:
            cabecalhos["X-Station-UUID"] = self.estacao_uuid
            cabecalhos["X-Station-Token"] = self.token
        return cabecalhos

    def _post(self, caminho, dados):
        url = f"{self.base_url}{caminho}"
        corpo = json.dumps(dados).encode("utf-8")
        requisicao = urllib.request.Request(
            url, data=corpo, headers=self._cabecalhos(), method="POST"
        )
        try:
            with self._abridor(requisicao, timeout=self.timeout) as resposta:
                conteudo = resposta.read()
                status = getattr(resposta, "status", None) or resposta.getcode()
        except urllib.error.HTTPError as exc:
            status = exc.code
            conteudo = exc.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PrintAgentClientError(f"Falha de rede: {exc}") from exc
        try:
            resultado = json.loads(conteudo or b"{}")
        except json.JSONDecodeError, UnicodeDecodeError:
            resultado = {}
        if status == 401:
            raise AuthError(str(resultado.get("erro", "Credencial inválida.")))
        if status >= 400:
            raise PrintAgentClientError(str(resultado.get("erro", f"HTTP {status}")))
        return resultado

    def pair(self, codigo):
        """Pareamento pelo código curto → {estacao, token, ...}."""
        return self._post("/api/print-agent/pair/", {"codigo": codigo})

    def poll(self, disponivel=True):
        """Consulta o próximo PrintJob (informa se a impressora está ok)."""
        return self._post("/api/print-agent/poll/", {"disponivel": bool(disponivel)})

    def reportar_resultado(self, job_uuid, status, erro=""):
        """Reporta PRINTED ou FAILED para o job."""
        return self._post(
            f"/api/print-agent/jobs/{job_uuid}/resultado/",
            {"status": status, "erro": erro},
        )
