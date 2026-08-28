"""Context processors do projeto."""

from pathlib import Path


def versao_deploy(request):
    """Commit em execução (escrito no deploy em .deploy-version).

    Permite confirmar visualmente qual build está em produção.
    """
    try:
        caminho = Path(__file__).resolve().parent.parent.parent / ".deploy-version"
        texto = caminho.read_text("utf-8").strip()
    except OSError:
        texto = ""
    return {"versao_deploy": texto[:12]}


def sidebar_ativa(request):
    """Item ativo da sidebar, derivado do caminho (nunca do frontend)."""
    caminho = request.path
    ativo = ""
    if caminho in ("/app/", "/app"):
        ativo = "dashboard"
    elif caminho.startswith("/app/pdv/") or caminho.startswith("/app/vendas/"):
        ativo = "venda"
    elif caminho.startswith("/app/produtos/"):
        ativo = "produtos"
    elif caminho.startswith("/app/clientes/"):
        ativo = "clientes"
    elif caminho.startswith("/app/caixa/"):
        ativo = "caixa"
    elif caminho.startswith("/app/relatorios/"):
        ativo = "relatorios"
    elif caminho.startswith("/app/financeiro/"):
        ativo = "financeiro"
    elif caminho.startswith("/app/impressao/"):
        ativo = "configuracoes"
    return {"sidebar_active": ativo}
