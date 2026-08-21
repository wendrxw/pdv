"""Contrato do cliente SEFAZ (SefazProvider por UF/ambiente).

O resto do sistema só conhece esta interface — implementações concretas
vivem em módulos separados (sp.py). Permite fakes nos testes sem rede.
"""

import abc


class SefazError(Exception):
    """Erro de comunicação/protocolo com a SEFAZ (não é rejeição)."""


class SefazClient(abc.ABC):
    """Operações NF-e 4.00 expostas pelo web service da SEFAZ."""

    @abc.abstractmethod
    def status_servico(self) -> "RetornoSefaz":  # noqa: F821
        """Consulta o status do serviço (cStat 107 = operacional)."""

    @abc.abstractmethod
    def autorizar(self, lote_xml: bytes, timeout: int | None = None):
        """Transmite lote de NFe; retorna RetornoSefaz.

        Timeout/conexão deve propagar SefazError — o chamador mantém a
        NFC-e em TRANSMITINDO e resolve depois por consulta.
        """

    @abc.abstractmethod
    def consultar_protocolo(self, chave_acesso: str):
        """Consulta situação de uma chave (recuperação idempotente)."""

    @abc.abstractmethod
    def receber_evento(self, evento_xml: bytes):
        """Envia evento assinado (cancelamento)."""

    @abc.abstractmethod
    def inutilizar(self, inutilizacao_xml: bytes):
        """Inutiliza faixa de numeração."""
