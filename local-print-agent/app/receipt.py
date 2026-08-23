"""Formatação do comprovante (somente texto — sem ESC/POS e sem dispositivo).

Recebe o payload JSON do servidor (snapshot da venda) e devolve uma lista
de linhas estilizadas: tuplas (texto, estilo). Estilos suportados:

    normal, central, direita, negrito, central_negrito

A largura respeita o papel configurado (58 mm → 32 colunas; 80 mm → 48)
e nomes longos são quebrados em várias linhas sem estourar a coluna.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

LARGURA_POR_MM = {"58": 32, "80": 48}
LARGURA_PADRAO = 32


def largura_papel(largura_mm):
    """Colunas de texto para a largura do papel térmico."""
    return LARGURA_POR_MM.get(str(largura_mm), LARGURA_PADRAO)


def _decimal(valor, padrao="0.00"):
    try:
        return Decimal(str(valor))
    except InvalidOperation, TypeError, ValueError:
        return Decimal(padrao)


def formatar_moeda(valor):
    """Decimal → "1.234,56" (pt-BR, sempre com 2 casas)."""
    valor = _decimal(valor).quantize(Decimal("0.01"))
    negativo = valor < 0
    inteiro, _, centavos = f"{abs(valor):f}".partition(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    resultado = ".".join(grupos) + "," + centavos
    return ("-" if negativo else "") + resultado


def formatar_quantidade(valor):
    """Decimal → "2", "2,5", "2,25" (sem zeros à direita)."""
    valor = _decimal(valor)
    if valor == valor.to_integral_value():
        return str(int(valor))
    texto = f"{valor:.3f}".rstrip("0")
    return texto.replace(".", ",")


def formatar_cnpj(cnpj):
    """14 dígitos → 00.000.000/0001-00 (vazio permanece vazio)."""
    cnpj = (cnpj or "").strip()
    if len(cnpj) != 14 or not cnpj.isdigit():
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"


def formatar_data_iso(data_iso):
    """ISO 8601 → dd/mm/yyyy HH:MM (local do servidor)."""
    try:
        momento = datetime.fromisoformat(str(data_iso))
    except ValueError, TypeError:
        return ""
    return momento.strftime("%d/%m/%Y %H:%M")


def quebrar_linha(texto, largura):
    """Quebra o texto em pedaços de até ``largura`` caracteres."""
    texto = str(texto or "")
    if not texto:
        return [""]
    return [texto[i : i + largura] for i in range(0, len(texto), largura)]


def centralizar(texto, largura):
    texto = str(texto or "")[:largura]
    espacos = largura - len(texto)
    esquerda = espacos // 2
    return " " * esquerda + texto + " " * (espacos - esquerda)


def alinhar_direita(texto, largura):
    return str(texto or "")[:largura].rjust(largura)


def separador(largura, caractere):
    return caractere * largura


def _data_venda(dados):
    return formatar_data_iso((dados.get("venda") or {}).get("data"))


def _numero_venda(dados):
    numero = (dados.get("venda") or {}).get("numero")
    try:
        return f"#{int(numero):06d}"
    except TypeError, ValueError:
        return f"#{numero}"


def formatar_dados_comprovante(dados, largura_colunas=None):
    """Payload do servidor → linhas estilizadas do comprovante."""
    largura = largura_colunas or largura_papel(dados.get("largura_mm"))
    linhas = []

    cabecalho = dados.get("cabecalho") or {}
    nome = (cabecalho.get("nome") or "").strip()
    cnpj = formatar_cnpj(cabecalho.get("cnpj"))
    endereco = (cabecalho.get("endereco") or "").strip()
    telefone = (cabecalho.get("telefone") or "").strip()

    linha_dupla = separador(largura, "=")
    linha_simples = separador(largura, "-")

    linhas.append((linha_dupla, "normal"))
    for parte in quebrar_linha(nome, largura):
        linhas.append((centralizar(parte, largura), "central_negrito"))
    if cnpj:
        linhas.append((centralizar(f"CNPJ: {cnpj}", largura), "central"))
    if endereco:
        for parte in quebrar_linha(endereco, largura):
            linhas.append((centralizar(parte, largura), "central"))
    if telefone:
        linhas.append((centralizar(f"Tel: {telefone}", largura), "central"))
    linhas.append((linha_dupla, "normal"))

    linhas.append((f"Venda: {_numero_venda(dados)}", "normal"))
    data = _data_venda(dados)
    if data:
        linhas.append((f"Data: {data}", "normal"))
    linhas.append((linha_simples, "normal"))

    for item in dados.get("itens") or []:
        nome = str(item.get("nome") or "")
        quantidade = formatar_quantidade(item.get("quantidade"))
        unitario = formatar_moeda(item.get("preco_unitario"))
        subtotal = formatar_moeda(item.get("subtotal"))
        for parte in quebrar_linha(nome, largura):
            linhas.append((parte, "normal"))
        esquerda = f"  {quantidade} x {unitario}"
        direita = subtotal
        espacos = largura - len(esquerda) - len(direita)
        if espacos < 1:
            espacos = 1
        linhas.append((esquerda + " " * espacos + direita, "normal"))

    totais = dados.get("totais") or {}
    desconto = _decimal(totais.get("desconto"), "0.00")
    linhas.append((linha_simples, "normal"))
    if desconto > 0:
        linhas.append(
            (
                "DESCONTO".ljust(largura - len(formatar_moeda(desconto)))
                + formatar_moeda(desconto),
                "normal",
            )
        )
    linhas.append(
        (
            "TOTAL".ljust(largura - len(formatar_moeda(totais.get("total"))))
            + formatar_moeda(totais.get("total")),
            "negrito",
        )
    )
    linhas.append((linha_simples, "normal"))

    for pagamento in dados.get("pagamentos") or []:
        forma = str(pagamento.get("forma") or "Pagamento")
        valor = formatar_moeda(pagamento.get("valor"))
        linhas.append(
            (
                f"{forma[: largura - len(valor) - 1]} {valor}".ljust(largura),
                "normal",
            )
        )

    valor_recebido = _decimal(dados.get("valor_recebido"), "0.00")
    troco = _decimal(dados.get("troco"), "0.00")
    if valor_recebido > 0:
        linhas.append(
            (
                "RECEBIDO".ljust(largura - len(formatar_moeda(valor_recebido)))
                + formatar_moeda(valor_recebido),
                "normal",
            )
        )
    if troco > 0:
        linhas.append(
            (
                "TROCO".ljust(largura - len(formatar_moeda(troco)))
                + formatar_moeda(troco),
                "negrito",
            )
        )

    mensagem = (dados.get("mensagem_final") or "").strip()
    if mensagem:
        linhas.append((linha_simples, "normal"))
        for parte in quebrar_linha(mensagem, largura):
            linhas.append((centralizar(parte, largura), "central"))
        linhas.append((linha_dupla, "normal"))
    else:
        linhas.append((linha_dupla, "normal"))

    linhas.append(("", "normal"))
    return linhas
