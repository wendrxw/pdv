"""Verifica estações de impressão ativas sem atividade recente.

Uso (cron/monitoramento do servidor):

    python manage.py check_print_agents --minutos 10

Sai com código 1 se alguma estação ativa estiver sem atividade há mais
que o limite (agente caído/loja offline). Nenhuma saída de dados
sensíveis.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.printing.models import EstacaoImpressao


class Command(BaseCommand):
    help = "Lista estações de impressão ativas sem atividade recente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutos",
            type=int,
            default=10,
            help=(
                "Tempo máximo sem atividade para considerar saudável "
                "(padrão: 10 minutos)."
            ),
        )

    def handle(self, *args, **opcoes):
        minutos = opcoes["minutos"]
        limite = timezone.now() - timedelta(minutes=minutos)
        problematicas = (
            EstacaoImpressao.objects.filter(status=EstacaoImpressao.Status.ATIVA)
            .exclude(ultima_atividade__gte=limite)
            .select_related("tenant")
            .order_by("tenant__nome", "nome")
        )
        if not problematicas.exists():
            self.stdout.write("Todas as estações ativas responderam recentemente.")
            return
        for estacao in problematicas:
            ultima = (
                estacao.ultima_atividade.strftime("%d/%m/%Y %H:%M")
                if estacao.ultima_atividade
                else "nunca"
            )
            self.stdout.write(
                self.style.WARNING(
                    f"[{estacao.tenant.nome}] {estacao.nome}: "
                    f"última atividade {ultima} (há mais de {minutos} min)"
                )
            )
        raise SystemExit(1)
