#!/usr/bin/env python3
"""Faalt als const.INTEGRATION_VERSION en manifest.json uit elkaar lopen.

Waarom dit bestaat: tussen augustus en oktober 2026 meldde elke installatie
versie 4.1.9 terwijl 4.2.0 t/m 4.2.2 al in het veld stonden. De constante werd
met de hand bijgewerkt en dat werd vergeten, waardoor het vlootoverzicht
maandenlang een verkeerd beeld gaf. De telemetrie leest de versie nu uit de
manifest; deze controle houdt de terugvalwaarde daaraan gelijk.
"""
import json
import pathlib
import re
import sys

WORTEL = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "digitalstrom_smart"

manifest = json.loads((WORTEL / "manifest.json").read_text())["version"]
const_tekst = (WORTEL / "const.py").read_text()
treffer = re.search(r'INTEGRATION_VERSION\s*=\s*"([^"]+)"', const_tekst)

if not treffer:
    print("FOUT: INTEGRATION_VERSION niet gevonden in const.py")
    sys.exit(1)

if treffer.group(1) != manifest:
    print(f"FOUT: manifest.json zegt {manifest}, const.py zegt {treffer.group(1)}")
    sys.exit(1)

print(f"versies gelijk: {manifest}")
