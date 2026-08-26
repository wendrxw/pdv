"""Context processors do projeto."""


def sidebar_ativa(request):
    """Item ativo da sidebar, derivado do caminho (nunca do frontend)."""
    caminho = request.path
    ativo = ""
    if caminho.startswith("/app/pdv/"):
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
