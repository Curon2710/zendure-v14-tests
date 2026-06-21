# zendure-v14-tests

Python-Testsuite für die **Zendure V14.2.2 Home Assistant Automation**.

## Zweck

Die Automation regelt den Zendure SolarFlow 800 Pro über das Output-Limit
(`number.solarflow_800_pro_no_2_output_limit`).  
Master-Regelwert ist der Shelly 3EM Pro Netzpunkt
(`sensor.ug_zentrale_pro3em_leistung`).  
Ziel: Netzpunkt nahe **−15 W** (Sweetspot).

Da die eigentliche Automation-Logik in Jinja2/YAML geschrieben ist, wird sie
hier als reines Python nachgebaut und mit pytest getestet –
**ohne echte Home Assistant-Abhängigkeiten**.

## Projektstruktur

```
zendure-v14-tests/
├── README.md
├── requirements.txt          # pytest
├── zendure/
│   └── automation.py         # alle Berechnungsfunktionen als Python
└── tests/
    └── test_automation.py    # 42 pytest-Szenarien
```

## Setup

```bash
pip install -r requirements.txt
```

## Tests ausführen

```bash
pytest -v
```

Alle 42 Szenarien sollten ohne Fehler durchlaufen.

## Getestete Bereiche

| Gruppe | Szenarien |
|---|---|
| Deadband | 1–5 |
| `should_update` | 6–10 |
| `selling_allowed` | 11–15 |
| MPPT-Bonus | 16–22 |
| `target_output` Clamp | 23–25 |
| Reserve-SOC | 26–30 |
| Soll-SOC (inkl. FIX 3) | 31–35 |
| Vollständige Integration | 36–42 |
