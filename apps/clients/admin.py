import django.contrib.admin as admin
from django.contrib import messages

from .models import (
    ClienteHistorico,
    ClientePlataforma,
    LeadContato,
    Onboarding,
)
from .services import (
    ClientServiceError,
    alterar_status,
    ativar_cliente,
    converter_lead,
)


class ClienteHistoricoInline(admin.TabularInline):
    model = ClienteHistorico
    extra = 0
    can_delete = False
    readonly_fields = (
        "uuid",
        "usuario",
        "acao",
        "status_anterior",
        "status_novo",
        "descricao",
        "data",
    )
    verbose_name_plural = "Histórico"

    def has_add_permission(self, request, obj=None):
        return False


class OnboardingInline(admin.StackedInline):
    model = Onboarding
    extra = 0
    max_num = 1
    readonly_fields = ("uuid", "data_inicio")


@admin.register(ClientePlataforma)
class ClientePlataformaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "tipo_pessoa",
        "cpf_cnpj",
        "email",
        "telefone_celular",
        "status",
        "origem",
        "usuario_responsavel",
        "data_cadastro",
    )
    list_filter = ("status", "tipo_pessoa", "origem", "data_cadastro")
    search_fields = ("nome", "razao_social", "nome_fantasia", "email", "cpf_cnpj")
    ordering = ("-data_cadastro",)
    readonly_fields = ("uuid", "data_cadastro", "data_atualizacao")
    inlines = (OnboardingInline, ClienteHistoricoInline)
    date_hierarchy = "data_cadastro"
    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "uuid",
                    "tipo_pessoa",
                    "nome",
                    "razao_social",
                    "nome_fantasia",
                    "cpf_cnpj",
                )
            },
        ),
        ("Contato", {"fields": ("email", "telefone_celular")}),
        (
            "Comercial",
            {"fields": ("status", "origem", "usuario_responsavel", "observacao")},
        ),
        (
            "Endereço",
            {
                "classes": ("collapse",),
                "fields": (
                    "cep",
                    "logradouro",
                    "numero",
                    "complemento",
                    "bairro",
                    "cidade",
                    "estado",
                ),
            },
        ),
        (
            "Auditoria",
            {"fields": ("data_cadastro", "data_atualizacao")},
        ),
    )
    actions = (
        "marcar_em_analise",
        "marcar_pendente",
        "ativar_selecionados",
        "suspender_selecionados",
        "cancelar_selecionados",
    )

    @admin.action(description="Marcar como em análise")
    def marcar_em_analise(self, request, queryset):
        self._aplicar_transicao(
            request, queryset, ClientePlataforma.Status.EM_ANALISE
        )

    @admin.action(description="Marcar como pendente")
    def marcar_pendente(self, request, queryset):
        self._aplicar_transicao(request, queryset, ClientePlataforma.Status.PENDENTE)

    @admin.action(description="Ativar selecionados (cria tenant)")
    def ativar_selecionados(self, request, queryset):
        ativados = 0
        for cliente in queryset:
            try:
                ativar_cliente(cliente, usuario=request.user)
                ativados += 1
            except ClientServiceError as erro:
                self.message_user(
                    request,
                    f"{cliente.nome}: {erro}",
                    level=messages.ERROR,
                )
        if ativados:
            self.message_user(
                request, f"{ativados} cliente(s) ativado(s).", level=messages.SUCCESS
            )

    @admin.action(description="Suspender selecionados")
    def suspender_selecionados(self, request, queryset):
        self._aplicar_transicao(request, queryset, ClientePlataforma.Status.SUSPENSO)

    @admin.action(description="Cancelar selecionados")
    def cancelar_selecionados(self, request, queryset):
        self._aplicar_transicao(request, queryset, ClientePlataforma.Status.CANCELADO)

    def _aplicar_transicao(self, request, queryset, novo_status):
        sucesso = 0
        for cliente in queryset:
            try:
                alterar_status(cliente, novo_status, usuario=request.user)
                sucesso += 1
            except ClientServiceError as erro:
                self.message_user(
                    request,
                    f"{cliente.nome}: {erro}",
                    level=messages.ERROR,
                )
        if sucesso:
            self.message_user(
                request,
                f"{sucesso} cliente(s) atualizado(s).",
                level=messages.SUCCESS,
            )


@admin.register(LeadContato)
class LeadContatoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "email",
        "telefone",
        "empresa",
        "status",
        "cliente_convertido",
        "data_criacao",
    )
    list_filter = ("status", "data_criacao")
    search_fields = ("nome", "email", "empresa", "telefone")
    ordering = ("-data_criacao",)
    readonly_fields = ("uuid", "ip_origem", "data_criacao")
    actions = ("converter_em_cliente", "descartar_selecionados")

    @admin.action(description="Converter em cliente da plataforma")
    def converter_em_cliente(self, request, queryset):
        convertidos = 0
        for lead in queryset:
            try:
                converter_lead(lead, usuario=request.user)
                convertidos += 1
            except ClientServiceError as erro:
                self.message_user(
                    request, f"{lead.nome}: {erro}", level=messages.ERROR
                )
        if convertidos:
            self.message_user(
                request,
                f"{convertidos} lead(s) convertido(s) em cliente.",
                level=messages.SUCCESS,
            )

    @admin.action(description="Descartar selecionados")
    def descartar_selecionados(self, request, queryset):
        queryset.update(status=LeadContato.Status.DESCARTADO)
