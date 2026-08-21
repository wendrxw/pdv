# PDV

Sistema SaaS multi-tenant para gestão de PDV: produtos, estoque, vendas,
financeiro e módulo fiscal NFC-e.

## Stack

- Python + Django + Django REST Framework
- PostgreSQL (produção) / SQLite (desenvolvimento)
- Django Templates + TailwindCSS
- Redis + Celery (fases futuras)

## Desenvolvimento

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Testes e lint:

```bash
uv run python manage.py test
uv run ruff check apps config manage.py
```

## Documentação

- [Arquitetura](docs/architecture.md)
- [Multi-tenancy](docs/multi-tenancy.md)
- [Clientes da plataforma](docs/clients.md)
