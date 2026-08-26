"""Geração de etiquetas em EPL2 (Elgin L42 Pro Full, 203 DPI).

A Elgin L42 Pro fala EPL2 (emulação). A bobina tem DUAS etiquetas por
fileira: o payload do servidor traz as fileiras prontas
([[etiqueta|None, etiqueta|None], ...]) — exatamente o que o preview
mostrou. Cada posição é impressa com um comando P1 (uma etiqueta); a
posição vazia não recebe conteúdo, mas o P1 avança a etiqueta física.

Dimensões chegam em mm e são convertidas para dots (mm × DPI / 25,4).
O código de barras é Code 128 (compatível com EAN-13 já usado no PDV) e
nunca ultrapassa a área da etiqueta (estreitamento automático).
"""

MM_POR_POLEGADA = 25.4

DPI_PADRAO = 203

# Fonte EPL2 aproximada: largura do caractere em dots (fonte 2, mult 1).
DOTS_POR_CARACTERE_FONTE2 = 8
DOTS_POR_CARACTERE_FONTE1 = 6


class LabelError(Exception):
    """Erro ao montar o trabalho de etiquetas."""


def mm_para_dots(mm, dpi=DPI_PADRAO):
    return max(int(round(float(mm) * dpi / MM_POR_POLEGADA)), 0)


def _dimensoes(payload):
    return payload.get("dimensoes") or {}


def _dpi(payload):
    try:
        return int(_dimensoes(payload).get("dpi", DPI_PADRAO))
    except TypeError, ValueError:
        return DPI_PADRAO


def _valor(dimensoes, chave, padrao="0"):
    return float(dimensoes.get(chave) or padrao)


def _colunas_por_linha(largura_dots, fonte=DOTS_POR_CARACTERE_FONTE2):
    return max(int(largura_dots / fonte), 1)


def _quebrar_texto(texto, largura_dots, fonte=DOTS_POR_CARACTERE_FONTE2):
    """Quebra o texto em linhas que cabem na largura da etiqueta."""
    texto = str(texto or "")
    maximo = _colunas_por_linha(largura_dots, fonte)
    return [texto[i : i + maximo] for i in range(0, len(texto), maximo)] or [""]


def _largura_codigo128(dados, narrow):
    # Code 128: 11 módulos por caractere + códigos de início/fim/checksum.
    return 11 * (len(dados) + 3) * narrow


def _texto_epl2(x, y, texto, fonte=2, multiplicador=1):
    return f'A{x},{y},0,{fonte},{multiplicador},{multiplicador},N,"{str(texto)}"\n'


def _codigo_barras_epl2(x, y, dados, altura_dots, largura_disponivel_dots):
    if not dados:
        return ""
    narrow = 2
    if _largura_codigo128(dados, narrow) > largura_disponivel_dots:
        narrow = 1
    if _largura_codigo128(dados, narrow) > largura_disponivel_dots:
        # Mesmo no mínimo não cabe: corta para caber (regra: nunca
        # ultrapassar a etiqueta).
        maximo = int(largura_disponivel_dots / (11 * narrow)) - 3
        dados = dados[: max(1, maximo)]
    return f'B{x},{y},0,1,{altura_dots},{narrow},2,N,"{dados}"\n'


def _etiqueta_epl2(etiqueta, coluna, dimensoes, dpi):
    """Comandos de UMA etiqueta (sem o P1 final).

    ``etiqueta`` é o dict {nome, codigo_barras} ou None (posição vazia).
    """
    largura = _valor(dimensoes, "largura_etiqueta", "40")
    altura = _valor(dimensoes, "altura_etiqueta", "30")
    gap_horizontal = _valor(dimensoes, "gap_horizontal", "2")
    margem_esquerda = _valor(dimensoes, "margem_esquerda", "2")
    margem_superior = _valor(dimensoes, "margem_superior", "1")
    offset_horizontal = _valor(dimensoes, "offset_horizontal", "0")
    offset_vertical = _valor(dimensoes, "offset_vertical", "0")

    x0 = mm_para_dots(
        margem_esquerda + offset_horizontal + coluna * (largura + gap_horizontal),
        dpi,
    )
    y0 = mm_para_dots(margem_superior + offset_vertical, dpi)
    largura_dots = mm_para_dots(largura, dpi)
    altura_dots = mm_para_dots(altura, dpi)

    if not etiqueta:
        return ""

    comandos = []
    nome = str(etiqueta.get("nome") or "")[:60]
    linhas = _quebrar_texto(nome, largura_dots)[:2]
    y = y0
    for linha in linhas:
        comandos.append(_texto_epl2(x0, y, linha))
        y += mm_para_dots(4, dpi)
    codigo = str(etiqueta.get("codigo_barras") or "")
    if codigo:
        altura_codigo = int(altura_dots * 0.35)
        comandos.append(_codigo_barras_epl2(x0, y, codigo, altura_codigo, largura_dots))
        y += altura_codigo + mm_para_dots(1.5, dpi)
    return "".join(comandos)


def _cabecalho_form(payload):
    """Comandos de setup: densidade, largura e tamanho do label/gap."""
    dimensoes = _dimensoes(payload)
    dpi = _dpi(payload)
    largura = _valor(dimensoes, "largura_etiqueta", "40")
    altura = _valor(dimensoes, "altura_etiqueta", "30")
    gap_horizontal = _valor(dimensoes, "gap_horizontal", "2")
    gap_vertical = _valor(dimensoes, "gap_vertical", "2")
    largura_maxima = mm_para_dots(2 * largura + gap_horizontal, dpi)
    altura_dots = mm_para_dots(altura, dpi)
    gap_dots = mm_para_dots(gap_vertical, dpi)
    densidade = 8 if dpi == 203 else 12
    return (
        "N\n"
        f"D{densidade}\n"
        f"q{largura_maxima}\n"
        f"Q{altura_dots},{gap_dots}\n"
        "P2\n"  # sem texto automático sob o código (controlamos à mão)
    )


def gerar_epl2_job(payload):
    """Payload do servidor (fileiras + dimensões) → bytes EPL2 completos."""
    if payload.get("tipo") == "calibracao":
        return gerar_epl2_calibracao(payload)
    dimensoes = _dimensoes(payload)
    dpi = _dpi(payload)
    largura = _valor(dimensoes, "largura_etiqueta", "40")
    altura = _valor(dimensoes, "altura_etiqueta", "30")
    gap_horizontal = _valor(dimensoes, "gap_horizontal", "2")
    margem_esquerda = _valor(dimensoes, "margem_esquerda", "2")
    margem_superior = _valor(dimensoes, "margem_superior", "1")
    offset_horizontal = _valor(dimensoes, "offset_horizontal", "0")
    offset_vertical = _valor(dimensoes, "offset_vertical", "0")
    mostrar_texto = bool(payload.get("mostrar_texto_codigo", True))
    altura_dots = mm_para_dots(altura, dpi)

    saida = [_cabecalho_form(payload)]
    for fileira in payload.get("fileiras") or []:
        for coluna, etiqueta in enumerate(fileira[:2]):
            saida.append(_etiqueta_epl2(etiqueta, coluna, dimensoes, dpi))
            if etiqueta and mostrar_texto:
                codigo = str(etiqueta.get("codigo_barras") or "")
                if codigo:
                    x0 = mm_para_dots(
                        margem_esquerda
                        + offset_horizontal
                        + coluna * (largura + gap_horizontal),
                        dpi,
                    )
                    y_texto = mm_para_dots(
                        margem_superior + offset_vertical, dpi
                    ) + int(altura_dots * 0.75)
                    saida.append(_texto_epl2(x0, y_texto, codigo, fonte=1))
            saida.append("P1\n")
    return ("".join(saida)).encode("latin-1", errors="replace")


def gerar_epl2_calibracao(payload):
    """Etiqueta de calibração: moldura + cruz + código de barras de teste.

    Serve para validar início/fim da etiqueta, distância entre colunas,
    offsets e legibilidade do código.
    """
    dimensoes = _dimensoes(payload)
    dpi = _dpi(payload)
    largura = _valor(dimensoes, "largura_etiqueta", "40")
    altura = _valor(dimensoes, "altura_etiqueta", "30")
    gap_horizontal = _valor(dimensoes, "gap_horizontal", "2")
    margem_esquerda = _valor(dimensoes, "margem_esquerda", "2")
    margem_superior = _valor(dimensoes, "margem_superior", "1")
    largura_dots = mm_para_dots(largura, dpi)
    altura_dots = mm_para_dots(altura, dpi)

    saida = [_cabecalho_form(payload)]
    for coluna in (0, 1):
        x0 = mm_para_dots(margem_esquerda + coluna * (largura + gap_horizontal), dpi)
        y0 = mm_para_dots(margem_superior, dpi)
        saida.append(f"X{x0},{y0},2,{largura_dots},{altura_dots}\n")
        saida.append(
            _texto_epl2(
                x0 + mm_para_dots(2, dpi), y0 + mm_para_dots(2, dpi), "CALIBRACAO"
            )
        )
        saida.append(
            _codigo_barras_epl2(
                x0 + mm_para_dots(2, dpi),
                y0 + mm_para_dots(8, dpi),
                "7891234567895",
                int(altura_dots * 0.35),
                largura_dots - mm_para_dots(4, dpi),
            )
        )
        saida.append("P1\n")
    return ("".join(saida)).encode("latin-1", errors="replace")
