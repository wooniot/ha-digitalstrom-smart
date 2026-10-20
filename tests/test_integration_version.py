#!/usr/bin/env python3
"""Toetst de versie-bepaling van de telemetrie zonder Home Assistant te installeren.

De methode _integration_version staat in coordinator.py, dat bij het importeren
Home Assistant nodig heeft. Daarom halen we hier de BRONTEKST van die ene methode
op en voeren we die uit met nagebootste onderdelen. Zo toetsen we de echte code,
niet een kopie ervan.

Drie gevallen:
  1. de manifest geeft een versie   -> die wordt gemeld
  2. het opzoeken mislukt            -> terugval op de constante
  3. tweede aanroep                  -> uit de cache, geen tweede opzoeking
"""
import asyncio
import ast
import pathlib
import sys
import types

BRON = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "digitalstrom_smart" / "coordinator.py"


def laad_methode(naam="_integration_version"):
    boom = ast.parse(BRON.read_text())
    for klasse in [n for n in ast.walk(boom) if isinstance(n, ast.ClassDef)]:
        for f in klasse.body:
            if isinstance(f, ast.AsyncFunctionDef) and f.name == naam:
                module = ast.Module(body=[f], type_ignores=[])
                waarschuwingen = []
                ruimte = {
                    "INTEGRATION_VERSION": "0.0.0-terugval",
                    "DOMAIN": "digitalstrom_smart",
                    "_LOGGER": types.SimpleNamespace(
                        debug=lambda *a, **k: None,
                        warning=lambda *a, **k: waarschuwingen.append(a),
                    ),
                }
                exec(compile(module, str(BRON), "exec"), ruimte)
                return ruimte[naam], waarschuwingen
    raise AssertionError(f"methode {naam} niet gevonden in {BRON}")


class NepCoordinator:
    def __init__(self):
        self._version_cache = ""
        self.hass = object()


def zet_loader(versie=None, kapot=False):
    """Zet een nagebootste homeassistant.loader in sys.modules."""
    aanroepen = {"n": 0}

    async def async_get_integration(hass, domein):
        aanroepen["n"] += 1
        if kapot:
            raise RuntimeError("integration not found")
        return types.SimpleNamespace(version=versie)

    ha = types.ModuleType("homeassistant")
    loader = types.ModuleType("homeassistant.loader")
    loader.async_get_integration = async_get_integration
    ha.loader = loader
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.loader"] = loader
    return aanroepen


def main():
    methode, waarschuwingen = laad_methode()
    fouten = []

    # 1. versie uit de manifest
    zet_loader(versie="4.2.3")
    c = NepCoordinator()
    uit = asyncio.run(methode(c))
    print("manifest geeft 4.2.3 ->", uit)
    if uit != "4.2.3":
        fouten.append(f"verwacht 4.2.3, kreeg {uit}")

    # 2. opzoeken mislukt -> terugval
    zet_loader(kapot=True)
    c = NepCoordinator()
    uit = asyncio.run(methode(c))
    print("opzoeken mislukt  ->", uit, "| waarschuwingen:", len(waarschuwingen))
    if uit != "0.0.0-terugval":
        fouten.append(f"verwachtte terugval, kreeg {uit}")
    if not waarschuwingen:
        fouten.append("mislukte opzoeking moet een waarschuwing loggen, niet alleen debug")

    # 3. cache: tweede aanroep zoekt niet opnieuw op
    aanroepen = zet_loader(versie="4.2.3")
    c = NepCoordinator()
    asyncio.run(methode(c))
    asyncio.run(methode(c))
    print("aanroepen van de opzoeker bij 2x vragen:", aanroepen["n"])
    if aanroepen["n"] != 1:
        fouten.append(f"cache werkt niet: {aanroepen['n']} opzoekingen")

    if fouten:
        print("MISLUKT:", "; ".join(fouten))
        sys.exit(1)
    print("alle drie de gevallen goed")


if __name__ == "__main__":
    main()
