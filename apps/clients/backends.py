from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import ClientePlataforma, Onboarding


class ClientePlataformaBackend(ModelBackend):
    """Autentica clientes da plataforma por e-mail + senha.

    A sessão do Django exige uma instância do AUTH_USER_MODEL, então no
    primeiro login criamos (ou reutilizamos) uma conta User vinculada ao
    cliente, com senha inutilizável: a senha válida continua sendo a do
    ClientePlataforma, única fonte de verdade.

    A cada autenticação, o tenant do usuário é sincronizado com o tenant
    do onboarding do cliente, garantindo acesso ao ambiente correto.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        cliente = ClientePlataforma.objects.filter(
            email__iexact=username.strip()
        ).first()
        if cliente is None or not cliente.check_password(password):
            return None
        user = cliente.usuario or self._obter_ou_criar_usuario(cliente)
        self._sincronizar_tenant(cliente, user)
        return user if self.user_can_authenticate(user) else None

    def _sincronizar_tenant(self, cliente, user):
        onboarding = Onboarding.objects.filter(cliente=cliente).first()
        tenant_id = onboarding.tenant_id if onboarding else None
        if user.tenant_id != tenant_id:
            user.tenant_id = tenant_id
            user.save(update_fields=["tenant"])

    def _obter_ou_criar_usuario(self, cliente):
        User = get_user_model()
        user = User.objects.filter(username=cliente.email).first()
        if user is not None and not user.is_staff and not user.is_superuser:
            cliente.usuario = user
            cliente.save(update_fields=["usuario"])
            return user
        username = cliente.email
        contador = 1
        while User.objects.filter(username=username).exists():
            contador += 1
            username = f"{cliente.email}+{contador}"
        user = User.objects.create_user(username=username, email=cliente.email)
        cliente.usuario = user
        cliente.save(update_fields=["usuario"])
        return user
