# Desktop — Fase 0: decisões, esqueleto do shell e Tailwind estático

**Task:** `tasks/TSK_00014.md` · **Branch:** `feat/desktop-fase0-esqueleto`
**Estudo:** `docs/migracao-desktop.md`

## 1. Decisões do proprietário (aplicadas)

| Questão | Decisão |
|---|---|
| Modelo de dados | **Central** — SaaS como hoje; desktop é cliente rico do Django central |
| SOs alvo | **Linux e Windows (64-bit)** |
| Gatilho NFC-e | **Investigar na Fase 12** — nenhuma mudança fiscal agora |
| Gaveta de dinheiro | **Não integrar** |
| Janelas | **Janela única na v1** |

## 2. Entregues nesta fase

### 2.1 Esqueleto `pdv-desktop/` (nenhum código do Django alterado)

```
pdv-desktop/
├── pyproject.toml          # pywebview>=5, pywin32 (Windows), hatchling
├── launcher.py             # entry point PyInstaller (padrão do print-agent)
├── README.md
├── src/pdv_desktop/
│   ├── __init__.py         # __version__ = "0.1.0"
│   ├── main.py             # bootstrap (--version/--help; janela na Fase 1)
│   ├── config.py           # Config: env PDV_DESKTOP_* > ~/.pdv-desktop/config.json (0600)
│   ├── window.py           # stub — Fase 1
│   ├── tray.py             # stub — Fase 3
│   ├── offline.html        # tela "Sem conexão" (sem dependência externa)
│   ├── session.py          # stub — Fase 2
│   ├── updater.py          # stub — Fase 14
│   └── print_embedded.py   # stub — Fase 10
└── tests/                  # 13 testes (unittest, padrão do local-print-agent)
```

Convenções: mesmo estilo do `local-print-agent` (unittest, launcher na raiz,
hatchling, entrada de CLI `pdv-desktop`). Testes:

```bash
cd pdv-desktop && PYTHONPATH=src python -m unittest discover -s tests
```

### 2.2 Tailwind estático (fim do Play CDN)

- `frontend/static/css/tailwind.config.js` — config extraída 1:1 do `base.html`
  (paletas navy/brand, fonte Inter); content scanning inclui templates **e**
  `apps/**/*.py` (classes de forms em constantes `INPUT_CLASS`).
- `frontend/static/css/input.css` + `tailwind.css` compilado (34,5 KB minificado)
  com **Tailwind v3.4.17 standalone** (mesma geração do Play CDN — zero mudança
  visual; o v4 mudaria paleta/estilos).
- `frontend/build-tailwind.sh` — rebuilda o CSS (baixa o CLI uma vez em
  `frontend/.tools/`, git-ignored).
- Fontes **Inter servidas localmente**: `frontend/static/fonts/inter/*.woff2` +
  `frontend/static/css/fonts.css` (35 blocos @font-face; subsets latin,
  latin-ext, cyrillic, greek, vietnamese). Regenerar com:
  `uv run python frontend/fetch-fonts.py`.
- `base.html` agora só linka `css/tailwind.css` e `css/fonts.css` com
  cache-busting `?v={{ versao_deploy }}`. **Zero referências a CDN/Google Fonts.**

### 2.3 Verificações

- Suíte Django completa: **456 testes OK**.
- `manage.py check`: OK. Ruff limpo em `pdv-desktop/` e `frontend/`.
- Cobertura de classes: 470 classes reais extraídas dos templates/forms —
  todas presentes no CSS compilado (arbitrary values incluídos, ex.
  `bg-[#001B3D]`, `min-h-[2.5rem]`, `w-[240px]`).
- `runserver` serve `tailwind.css`, `fonts.css` e woff2 com 200.

## 3. Achados pré-existentes (não regressões — documentados para a Fase 3)

- `apps/printing/templates/printing/estacoes.html:89` usa `border-brand-200`
  (a paleta brand não tem 200 → nunca teve estilo, nem com o CDN).
- `apps/inventory/templates/inventory/saldos.html:29` usa `hover:text-brand-800`
  (idem — sem efeito hoje). Avaliar trocar por tons válidos na Fase 3.
- `class="group"` no `pdv_shell.html` é classe-marcador sem estilo (idem ao CDN).

## 4. Como rebuildar o CSS

```bash
./frontend/build-tailwind.sh          # recompila tailwind.css
uv run python frontend/fetch-fonts.py # re-baixa Inter (se necessário)
```

> Em produção: `collectstatic` já copia `frontend/static/` (STATICFILES_DIRS)
> e o nginx já serve `/static/` — nenhuma mudança de infra.

## 5. Próximo passo

**Fase 1 — Shell base:** janela PyWebview com tamanho mínimo, carregamento de
`Config.server_url`, bridge `js_api` (whitelist), bloqueio de F5/reload e
detecção de offline (a `offline.html` já existe).
