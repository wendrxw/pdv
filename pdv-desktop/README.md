# pdv-desktop

Shell desktop do PDV: cliente rico em **PyWebview** que carrega o sistema
Django central em uma janela nativa e executa serviços locais (impressão
embutida, bandeja, atualização automática).

Estudo completo: `docs/migracao-desktop.md`.

## Desenvolvimento

```bash
cd pdv-desktop
PYTHONPATH=src python launcher.py --version
PYTHONPATH=src python -m unittest discover -s tests
```

## Empacotamento (Fase 13)

```bash
pyinstaller --onefile --name pdv-desktop \
  --paths src \
  --add-data "src/pdv_desktop/offline.html:pdv_desktop" \
  launcher.py
```
