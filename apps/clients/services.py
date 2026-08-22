"""Regras de negócio do módulo de clientes da plataforma.

Views e admin não devem conter regras complexas: utilizem estes serviços.
"""

from django.db import transaction

from apps.audit.models import registrar
from apps.companies.models import Tenant
from apps.core.validators import only_digits, validate_cpf_cnpj

from .models import ClienteHistorico, ClientePlataforma, LeadContato, Onboarding


class ClientServiceError(Exception):
    """Erro de domínio do módulo de clientes."""


def _registrar_historico(
    cliente,
    acao,
    usuario=None,
    status_anterior="",
    status_novo="",
    descricao="",
):
    ClienteHistorico.objects.create(
        cliente=cliente,
        usuario=usuario,
        acao=acao,
        status_anterior=status_anterior,
        status_novo=status_novo,
        descricao=descricao,
    )


@transaction.atomic
def criar_cliente(
    *,
    nome,
    cpf_cnpj,
    email,
    telefone_celular,
    tipo_pessoa=ClientePlataforma.TipoPessoa.PJ,
    origem=ClientePlataforma.Origem.OUTRO,
    status_inicial=ClientePlataforma.Status.LEAD,
    usuario_responsavel=None,
    **campos_extras,
):
    """Cria um cliente da plataforma com histórico inicial.

    O status inicial padrão é LEAD; o fluxo de aprovação é explícito.
    """
    cliente = ClientePlataforma(
        nome=nome,
        cpf_cnpj=cpf_cnpj,
        email=email,
        telefone_celular=telefone_celular,
        tipo_pessoa=tipo_pessoa,
        origem=origem,
        status=status_inicial,
        usuario_responsavel=usuario_responsavel,
        **campos_extras,
    )
    # Normaliza antes de validar para que máscaras não violem max_length.
    if cliente.cpf_cnpj:
        cliente.cpf_cnpj = only_digits(cliente.cpf_cnpj)
        validate_cpf_cnpj(cliente.cpf_cnpj)
    cliente.email = cliente.email.strip().lower()
    cliente.full_clean()
    cliente.save()
    _registrar_historico(
        cliente,
        ClienteHistorico.Acao.CRIADO,
        usuario=usuario_responsavel,
        status_novo=cliente.status,
        descricao=f"Cliente criado com status {cliente.get_status_display()}.",
    )
    registrar(
        "CLIENTE_CRIADO",
        entidade=cliente,
        usuario=usuario_responsavel,
        descricao=f"Cliente {cliente.uuid} criado.",
    )
    return cliente


@transaction.atomic
def alterar_status(cliente, novo_status, *, usuario=None, descricao=""):
    """Altera o status do cliente validando transições permitidas.

    Transições válidas:
        LEAD → EM_ANALISE → PENDENTE → ATIVO
        ATIVO → SUSPENSO | CANCELADO
        SUSPENSO → ATIVO
        EM_ANALISE/PENDENTE → CANCELADO
    """
    if novo_status == ClientePlataforma.Status.ATIVO and (
        cliente.status != ClientePlataforma.Status.SUSPENSO
        and not Onboarding.objects.filter(cliente=cliente, tenant__isnull=False).exists()
    ):
        raise ClientServiceError(
            "Ativação só pode ser feita pela ação de ativação "
            "(cria o tenant automaticamente)."
        )
    transicoes_validas = {
        ClientePlataforma.Status.LEAD: {
            ClientePlataforma.Status.EM_ANALISE,
            ClientePlataforma.Status.CANCELADO,
        },
        ClientePlataforma.Status.EM_ANALISE: {
            ClientePlataforma.Status.PENDENTE,
            ClientePlataforma.Status.CANCELADO,
        },
        ClientePlataforma.Status.PENDENTE: {
            ClientePlataforma.Status.ATIVO,
            ClientePlataforma.Status.CANCELADO,
        },
        ClientePlataforma.Status.ATIVO: {
            ClientePlataforma.Status.SUSPENSO,
            ClientePlataforma.Status.CANCELADO,
        },
        ClientePlataforma.Status.SUSPENSO: {
            ClientePlataforma.Status.ATIVO,
            ClientePlataforma.Status.CANCELADO,
        },
    }
    atual = cliente.status
    if novo_status == atual:
        return cliente
    permitidas = transicoes_validas.get(atual, set())
    if novo_status not in permitidas:
        raise ClientServiceError(
            f"Transição de status inválida: {atual} → {novo_status}."
        )

    status_anterior = cliente.status
    cliente.status = novo_status
    cliente.save(update_fields=["status", "data_atualizacao"])
    _registrar_historico(
        cliente,
        ClienteHistorico.Acao.STATUS_ALTERADO,
        usuario=usuario,
        status_anterior=status_anterior,
        status_novo=novo_status,
        descricao=descricao or f"Status alterado para {cliente.get_status_display()}.",
    )
    registrar(
        "CLIENTE_STATUS_ALTERADO",
        entidade=cliente,
        usuario=usuario,
        dados={"status_anterior": status_anterior, "status_novo": novo_status},
    )
    return cliente


@transaction.atomic
def ativar_cliente(cliente, *, usuario=None, nome_tenant=None):
    """Ativa o cliente criando (ou associando) o tenant de forma transacional.

    Garante consistência: se a criação do tenant falhar, nada é persistido —
    o cliente não fica parcialmente ativado.
    """
    onboarding = Onboarding.objects.filter(cliente=cliente).first()
    tem_tenant = getattr(onboarding, "tenant_id", None) is not None

    if cliente.status == ClientePlataforma.Status.ATIVO and tem_tenant:
        raise ClientServiceError("Cliente já está ativo.")
    if cliente.status not in {
        ClientePlataforma.Status.PENDENTE,
        ClientePlataforma.Status.ATIVO,
    }:
        raise ClientServiceError(
            "Somente clientes PENDENTES podem ser ativados. "
            "Mova o cliente pelo fluxo de aprovação primeiro."
        )
    if not cliente.cpf_cnpj:
        raise ClientServiceError(
            "Cliente sem CPF/CNPJ não pode ser ativado. Complete o cadastro."
        )
    try:
        validate_cpf_cnpj(cliente.cpf_cnpj)
    except ValueError as exc:
        raise ClientServiceError(f"Documento inválido: {exc}") from exc

    onboarding = Onboarding.objects.filter(cliente=cliente).first()

    if getattr(onboarding, "tenant_id", None):
        tenant = onboarding.tenant
    else:
        tenant = Tenant.objects.create(
            nome=nome_tenant or cliente.nome,
            status=Tenant.Status.ATIVO,
        )

    status_anterior = cliente.status
    cliente.status = ClientePlataforma.Status.ATIVO
    cliente.save(update_fields=["status", "data_atualizacao"])

    if onboarding is None:
        onboarding = Onboarding(cliente=cliente)
    onboarding.tenant = tenant
    onboarding.usuario_responsavel = onboarding.usuario_responsavel or usuario
    onboarding.save()

    _registrar_historico(
        cliente,
        ClienteHistorico.Acao.STATUS_ALTERADO,
        usuario=usuario,
        status_anterior=status_anterior,
        status_novo=ClientePlataforma.Status.ATIVO,
        descricao="Cliente ativado.",
    )
    _registrar_historico(
        cliente,
        ClienteHistorico.Acao.TENANT_ASSOCIADO,
        usuario=usuario,
        descricao=f"Tenant {tenant.nome} ({tenant.slug}) associado ao cliente.",
    )
    registrar(
        "CLIENTE_ATIVADO",
        entidade=cliente,
        usuario=usuario,
        tenant=tenant,
        descricao=f"Cliente ativado com tenant {tenant.slug}.",
    )
    return cliente


@transaction.atomic
def converter_lead(lead, *, usuario=None):
    """Converte um lead do site em cliente da plataforma (status LEAD).

    Não cria tenant nem usuário automaticamente.
    """
    if lead.status == LeadContato.Status.CONVERTIDO:
        raise ClientServiceError("Lead já foi convertido.")

    cliente = criar_cliente(
        nome=lead.empresa or lead.nome,
        cpf_cnpj="",
        email=lead.email,
        telefone_celular=lead.telefone,
        origem=ClientePlataforma.Origem.SITE,
        status_inicial=ClientePlataforma.Status.LEAD,
        usuario_responsavel=usuario,
        observacao=f"Lead convertido do site.\nMensagem original:\n{lead.mensagem}",
    )
    lead.status = LeadContato.Status.CONVERTIDO
    lead.cliente_convertido = cliente
    lead.save(update_fields=["status", "cliente_convertido"])
    registrar(
        "LEAD_CONVERTIDO",
        entidade=lead,
        usuario=usuario,
        descricao=f"Lead convertido no cliente {cliente.uuid}.",
    )
    return cliente
