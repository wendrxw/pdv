"""Núcleo do Local Print Agent: loop, deduplicação e retry.

Garantias:
- nunca imprime duas vezes o mesmo job (log local de uuids processados —
  idempotência mesmo se a conexão cair entre a impressão e o reporte);
- impressora desligada/desconectada: o trabalho continua na fila do
  servidor (o agente informa ``disponivel=False`` e não consome o job);
- falha de impressão: reporta FAILED com o erro; quem agenda o retry é o
  servidor (backoff por tentativa).
"""

import json
import time

from .escpos import (
    CODEPAGEM_PARA_ENCODING,
    EscPosPrinter,
    normalizar_texto,
    selecionar_codepage,
)
from .labels import LabelError, gerar_epl2_job
from .printer import PrinterError, UsbPrinterDevice
from .receipt import formatar_dados_comprovante, largura_papel

MAX_PROCESSADOS = 500

BACKOFF_REDE = [5, 15, 30, 60]


def carregar_credencial(config):
    """Lê estacao/token do disco (None se nunca pareou)."""
    try:
        dados = json.loads(config.caminho_credencial.read_text("utf-8"))
        if dados.get("estacao") and dados.get("token"):
            return dados
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return None


def salvar_credencial(config, credencial):
    """Persiste a credencial com permissão restrita (0600)."""
    config.state_dir.mkdir(parents=True, exist_ok=True)
    arquivo = config.caminho_credencial
    arquivo.write_text(json.dumps(credencial, ensure_ascii=False), "utf-8")
    try:
        arquivo.chmod(0o600)
    except OSError:
        pass


def _carregar_processados(config):
    try:
        linhas = config.caminho_processados.read_text("utf-8").splitlines()
    except OSError:
        return {}
    processados = {}
    for linha in linhas:
        try:
            registro = json.loads(linha)
            processados[registro["uuid"]] = registro["resultado"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return processados


def _registrar_processado(config, job_uuid, resultado):
    config.state_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(config.caminho_processados, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps({"uuid": job_uuid, "resultado": resultado}) + "\n")
    except OSError:
        pass
    _podar_processados(config)


def _podar_processados(config):
    """Mantém apenas os MAX_PROCESSADOS registros mais recentes."""
    caminho = config.caminho_processados
    try:
        linhas = caminho.read_text("utf-8").splitlines()
    except OSError:
        return
    if len(linhas) <= MAX_PROCESSADOS:
        return
    try:
        caminho.write_text("\n".join(linhas[-MAX_PROCESSADOS:]) + "\n", "utf-8")
    except OSError:
        pass


class PrintAgent:
    """Pareia com o servidor, faz polling e imprime comprovantes."""

    def __init__(
        self, config, cliente, impressora, logger=None, impressora_etiquetas=None
    ):
        import logging

        self.config = config
        self.cliente = cliente
        self.impressora = impressora
        self.log = logger or logging.getLogger("print-agent")
        self.processados = _carregar_processados(config)
        self.impressora_etiquetas = impressora_etiquetas or (
            UsbPrinterDevice(config.label_device) if config.label_device else None
        )

    def ciclo(self):
        """Uma rodada de polling. Retorna 'impresso', 'ocioso' ou 'ignorado'."""
        resultado_comprovante = self._ciclo_comprovantes()
        if self.impressora_etiquetas is not None:
            self._ciclo_etiquetas()
        return resultado_comprovante

    def _ciclo_comprovantes(self):
        """Comprovantes (térmica 58/80mm)."""
        disponivel = self.impressora.disponivel()
        resposta = self.cliente.poll(disponivel=disponivel)
        job = (resposta or {}).get("job")
        if not job:
            return "ocioso"
        job_uuid = str(job["uuid"])
        anterior = self.processados.get(job_uuid)
        if anterior == "PRINTED":
            # Reporte se perdeu no caminho: converge sem reimprimir.
            self.log.info("Job %s já impresso localmente; reconfirmando.", job_uuid)
            self.cliente.reportar_resultado(job_uuid, "PRINTED")
            return "ignorado"
        if anterior == "FAILED":
            self.log.info(
                "Job %s já falhou neste agente; aguardando ação do operador.",
                job_uuid,
            )
            return "ignorado"
        if not disponivel:
            # Não deveria acontecer (poll já informa disponivel=False),
            # mas garante que não consumimos o job sem impressora.
            return "ocioso"

        payload = job.get("payload") or {}
        try:
            largura = largura_papel(
                payload.get("largura_mm", self.config.largura_padrao)
            )
            linhas = formatar_dados_comprovante(payload, largura_colunas=largura)
            impressora_escpos = EscPosPrinter(
                codepage=self.config.codepage,
                cortar_parcial=self.config.cortar_parcial,
            )
            if self.config.escpos:
                dados_impressao = impressora_escpos.render(
                    linhas,
                    alimentar_antes_de_cortar=self.config.alimentacao_final,
                )
            else:
                # Modo texto puro: mesmo efeito do comando
                #   printf "..." > /dev/usb/lp0
                # (impressoras sem ESC/POS confiável, ex.: Tomate MDK-080).
                # Os acentos seguem PRINTER_CODEPAGE — 1 byte por caractere
                # para firmware antigo; o prefixo ESC t n seleciona a
                # tabela (desativável com PRINTER_SELECIONAR_CODEPAGE=0).
                # Linhas em branco no fim dão folga para o corte/rasgo.
                encoding = CODEPAGEM_PARA_ENCODING.get(self.config.codepage, "utf-8")
                texto_comprovante = (
                    "\n".join(texto for texto, _estilo in linhas)
                    + "\n" * self.config.alimentacao_final
                )
                dados_impressao = normalizar_texto(texto_comprovante).encode(
                    encoding, errors="replace"
                )
                if self.config.selecionar_codepage:
                    dados_impressao = (
                        selecionar_codepage(self.config.codepage) + dados_impressao
                    )
            self.impressora.escrever(dados_impressao)
        except (PrinterError, OSError) as exc:
            self._falhou(job_uuid, f"Erro na impressão: {exc}")
            return "impresso"
        except Exception as exc:  # noqa: BLE001 - reporta qualquer falha
            self._falhou(job_uuid, f"Erro inesperado: {exc}")
            return "impresso"

        try:
            self.cliente.reportar_resultado(job_uuid, "PRINTED")
        except Exception as exc:  # noqa: BLE001 - reporte perdido → dedupe
            self.log.warning("Impresso, mas reporte falhou para %s: %s", job_uuid, exc)
        _registrar_processado(self.config, job_uuid, "PRINTED")
        self.processados[job_uuid] = "PRINTED"
        self.log.info("Comprovante %s impresso.", job_uuid)
        return "impresso"

    def _ciclo_etiquetas(self):
        """Etiquetas (Elgin L42 Pro Full, EPL2, duas por fileira).

        Mesmas garantias dos comprovantes: dedupe por uuid (com prefixo
        próprio), impressora desligada não consome o trabalho e falha é
        reportada para o servidor agendar retry.
        """
        disponivel = self.impressora_etiquetas.disponivel()
        resposta = self.cliente.poll_etiquetas(disponivel=disponivel)
        job = (resposta or {}).get("job")
        if not job:
            return
        job_uuid = str(job["uuid"])
        chave = f"etiqueta:{job_uuid}"
        anterior = self.processados.get(chave)
        if anterior == "PRINTED":
            self.log.info("EtiquetaJob %s já impresso; reconfirmando.", job_uuid)
            self.cliente.reportar_resultado_etiquetas(job_uuid, "PRINTED")
            return
        if anterior == "FAILED":
            self.log.info(
                "EtiquetaJob %s já falhou; aguardando ação do operador.", job_uuid
            )
            return
        if not disponivel:
            return

        payload = job.get("payload") or {}
        try:
            if self.config.label_linguagem != "epl2":
                raise LabelError(
                    f"Linguagem de etiquetas não suportada: "
                    f"{self.config.label_linguagem}"
                )
            dados_impressao = gerar_epl2_job(payload)
            self.impressora_etiquetas.escrever(dados_impressao)
        except (PrinterError, OSError) as exc:
            self._falhou_etiquetas(chave, job_uuid, f"Erro na impressão: {exc}")
            return
        except Exception as exc:  # noqa: BLE001 - reporta qualquer falha
            self._falhou_etiquetas(chave, job_uuid, f"Erro inesperado: {exc}")
            return

        try:
            self.cliente.reportar_resultado_etiquetas(job_uuid, "PRINTED")
        except Exception as exc:  # noqa: BLE001 - reporte perdido → dedupe
            self.log.warning(
                "Etiquetas impressas, mas reporte falhou para %s: %s",
                job_uuid,
                exc,
            )
        _registrar_processado(self.config, chave, "PRINTED")
        self.processados[chave] = "PRINTED"
        self.log.info("EtiquetaJob %s impresso.", job_uuid)

    def _falhou_etiquetas(self, chave, job_uuid, erro):
        self.log.error("EtiquetaJob %s falhou: %s", job_uuid, erro)
        try:
            self.cliente.reportar_resultado_etiquetas(job_uuid, "FAILED", erro)
        except Exception as exc:  # noqa: BLE001 - não perde o estado local
            self.log.warning(
                "Reporte de falha de etiquetas perdido para %s: %s",
                job_uuid,
                exc,
            )
        _registrar_processado(self.config, chave, "FAILED")
        self.processados[chave] = "FAILED"

    def _falhou(self, job_uuid, erro):
        self.log.error("Job %s falhou: %s", job_uuid, erro)
        try:
            self.cliente.reportar_resultado(job_uuid, "FAILED", erro)
        except Exception as exc:  # noqa: BLE001 - não perde o estado local
            self.log.warning("Reporte de falha perdido para %s: %s", job_uuid, exc)
        _registrar_processado(self.config, job_uuid, "FAILED")
        self.processados[job_uuid] = "FAILED"

    def executar(self, ciclos=None):
        """Loop principal. Levanta AuthError para credencial inválida."""
        from .client import AuthError, PrintAgentClientError

        rodadas = 0
        falhas_rede = 0
        while ciclos is None or rodadas < ciclos:
            try:
                self.ciclo()
                espera = self.config.poll_interval
                falhas_rede = 0
            except AuthError:
                raise
            except PrintAgentClientError as exc:
                indice = min(falhas_rede, len(BACKOFF_REDE) - 1)
                espera = BACKOFF_REDE[indice]
                falhas_rede += 1
                self.log.warning(
                    "Servidor indisponível (%s); nova tentativa em %ss.",
                    exc,
                    espera,
                )
            rodadas += 1
            if ciclos is None or rodadas < ciclos:
                time.sleep(espera)
