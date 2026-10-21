# scripts/

## check_version_sync.py

Faalt als `manifest.json` en `INTEGRATION_VERSION` in `const.py` niet dezelfde versie
noemen. Draai dit vóór elke release, samen met de toets op de versiebepaling:

    python3 scripts/check_version_sync.py
    python3 tests/test_integration_version.py

Waarom: tussen augustus en oktober 2026 bleef de constante op 4.1.9 staan terwijl
4.2.0 t/m 4.2.2 werden uitgebracht. De telemetrie stuurde die constante mee, dus
meldde vrijwel de hele vloot maandenlang een versie die nergens op sloeg.

## Nog in CI te zetten

Deze twee controles horen in `.github/workflows/validate.yml`, maar de GitHub-token
op de werkplek heeft geen `workflow`-recht; die workflow is van hieruit dus niet bij
te werken. Eenmalig, in een terminal met browsertoegang:

    gh auth refresh -h github.com -s workflow

Daarna dit blok onderaan `.github/workflows/validate.yml` plakken:

```yaml
  validate-version:
    runs-on: "ubuntu-latest"
    steps:
      - uses: "actions/checkout@v4"
      - name: manifest en const.py moeten dezelfde versie noemen
        run: python3 scripts/check_version_sync.py
      - name: versiebepaling van de telemetrie toetsen
        run: python3 tests/test_integration_version.py
```

Tot die tijd draait dezelfde controle lokaal via de pre-commit-haak in `.githooks/`:

    git config core.hooksPath .githooks
