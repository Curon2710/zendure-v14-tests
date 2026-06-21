"""
Zendure V14.2.2 Home Assistant Automation – Python port.

Regelt den Zendure SolarFlow 800 Pro über das Output-Limit.
Master-Regelwert: Shelly 3EM Pro Netzpunkt.
Ziel: Netzpunkt nahe -15 W (Sweetspot).

Alle Berechnungsfunktionen sind einzeln testbar exportiert.
Keine echten Home Assistant-Abhängigkeiten.
"""

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

SWEETSPOT: float = -15
DEADBAND_LOW: float = -35
DEADBAND_HIGH: float = -5


# ---------------------------------------------------------------------------
# Deadband & Regler
# ---------------------------------------------------------------------------


def compute_deadband(grid_w: float) -> bool:
    """Gibt True zurück, wenn der Netzpunkt im Deadband liegt."""
    return DEADBAND_LOW <= grid_w <= DEADBAND_HIGH


def compute_regulator_target(grid_w: float, output_now: float) -> float:
    """
    P-Regler: Berechnet den Soll-Output (W).

    Im Deadband wird der aktuelle Output beibehalten.
    Außerhalb wird der Fehler (grid_w - sweetspot) addiert.
    """
    if compute_deadband(grid_w):
        return output_now
    error = grid_w - SWEETSPOT
    return output_now + error


# ---------------------------------------------------------------------------
# Zeit- und Energieberechnungen
# ---------------------------------------------------------------------------


def compute_hours_to_target(now_hour: float, evening_start: float) -> float:
    """Stunden bis zum nächsten Tagesziel (08:00 Uhr)."""
    if now_hour >= 22:
        return 8 - now_hour + 24
    elif now_hour < 8:
        return 8 - now_hour
    elif now_hour < evening_start:
        return evening_start - now_hour
    else:
        return 22 - now_hour


def compute_house_hours(now_hour: float, evening_start: float) -> float:
    """Verbleibende Hausstunden bis evening_start."""
    if now_hour >= 22:
        return (24 - now_hour) + evening_start
    return max(evening_start - now_hour, 0)


# ---------------------------------------------------------------------------
# Export / Verkaufslogik
# ---------------------------------------------------------------------------


def compute_selling_allowed(soc: float, reserve_soc: float, soll_soc: float) -> bool:
    """True, wenn aktiver Verkauf (Export) erlaubt ist."""
    return soc > reserve_soc and soc > soll_soc


# ---------------------------------------------------------------------------
# MPPT-Bonus
# ---------------------------------------------------------------------------


def compute_mppt_bonus(solar_input: float) -> float:
    """
    MPPT-Überschuss-Bonus in echten 50-W-Stufen, gedeckelt auf 800 W.

    Oberhalb von 1920 W Solar-Input wird der Überschuss in 50-W-Schritten
    als zusätzlicher Output-Bonus gerechnet, um MPPT-Clipping zu vermeiden.
    """
    if solar_input >= 1920:
        over = solar_input - 1920
        stepped = int(over / 50) * 50
        return min(stepped, 800)
    return 0


# ---------------------------------------------------------------------------
# Output-Limit Berechnung
# ---------------------------------------------------------------------------


def compute_target_output(raw_target: float) -> int:
    """Klemmt raw_target auf [0, 800] W und rundet auf Ganzzahl."""
    return round(min(max(raw_target, 0), 800))


def compute_should_update(output_now: float, target_output: float) -> bool:
    """
    True, wenn das Output-Limit ans Gerät geschrieben werden soll.

    Sonderfall Einschalten: beim Wechsel aus dem Standby (output_now < 5 W)
    muss der neue Zielwert >= 35 W sein, um Mikro-Zyklen zu vermeiden.
    Sonst: Änderung nur bei Differenz >= 5 W.
    """
    diff = abs(target_output - output_now)
    switching_on_discharge = output_now < 5 and target_output >= 5
    if switching_on_discharge:
        return target_output >= 35
    return diff >= 5


# ---------------------------------------------------------------------------
# sensor.zendure_soc_reserve
# ---------------------------------------------------------------------------


def compute_reserve_soc(month: int, day1: float, day2: float) -> float:
    """
    Reserve-SOC aus Jahreszeit und Kurzzeit-Solarprognose.

    Basis: 10 % im Sommer (Apr–Sep), 40 % im Winter.
    +10 % fester Offset: Automation stoppt aktiven Verkauf bei Reserve-SOC,
        der Zendure-Hardware-Min (10 %) erlaubt danach noch passive
        Hauslastdeckung bis zur HW-Grenze (Pufferzone).
    +10 % je Schlechtwettertag (Prognose < 7 kWh).
    """
    base = 10 if 4 <= month <= 9 else 40
    bad_days = (1 if day1 < 7 else 0) + (1 if day2 < 7 else 0)
    return base + 10 + bad_days * 10


# ---------------------------------------------------------------------------
# sensor.zendure_soc_sollwert_jetzt  (FIX 3 beachten!)
# ---------------------------------------------------------------------------


def compute_soll_soc(
    now_hour: float,
    day_end: float,
    target_soc: float,
    soc: float,
    capacity: float,
    forecast_kwh: float,
    reserve_soc: float,
) -> float:
    """
    Zeitabhängiger SOC-Sollwert (sensor.zendure_soc_sollwert_jetzt).

    Nacht  (22–08 Uhr): linearer Rückgang von 100 % auf target_soc.
    Abend  (day_end–22 Uhr): 100 %.
    Tag    (08–day_end): linearer Anstieg von dynamisch berechnetem
                         start_soc auf 100 %.

    FIX 3: span wird auf mindestens 0.01 geklemmt, damit keine
           Division durch null auftreten kann, wenn day_end == 8.
    """
    if now_hour >= 22 or now_hour < 8:
        night_elapsed = (now_hour - 22) if now_hour >= 22 else (now_hour + 2)
        progress = min(max(night_elapsed / 10, 0), 1)
        return 100 + (target_soc - 100) * progress
    elif now_hour >= day_end:
        return 100.0
    else:
        house_hours = max(day_end - now_hour, 0)
        expected_house = house_hours * 0.34
        free_capacity = ((100 - soc) / 100) * capacity
        excess = max(forecast_kwh - free_capacity - expected_house, 0)
        excess_soc = (excess / capacity) * 100
        start_soc = max(soc - excess_soc, reserve_soc)
        span = max(day_end - 8, 0.01)  # FIX 3: verhindert Division durch null
        progress = min(max((now_hour - 8) / span, 0), 1)
        return start_soc + (100 - start_soc) * progress


# ---------------------------------------------------------------------------
# sensor.zendure_soc_ziel
# ---------------------------------------------------------------------------


def compute_ziel_soc(
    now_hour: float,
    day_end: float,
    soc: float,
    capacity: float,
    fc_today: float,
    fc_tomorrow: float,
    reserve_soc: float,
) -> float:
    """
    Nacht-SOC-Zielwert (sensor.zendure_soc_ziel).

    Tagsüber immer 100 %.
    Nachts berechnet die Automation, wie viel Solarüberschuss erwartet wird,
    und senkt den Zielwert entsprechend, um Platz zu schaffen.

    Nacht >= 22 Uhr: Prognose von morgen (fc_tomorrow).
    Nacht <  8 Uhr: Prognose von heute  (fc_today).
    """
    # Tagsüber: immer 100 %
    if 8 <= now_hour < 22:
        return 100.0

    if now_hour >= 22:
        forecast = fc_tomorrow
        house_hours = (24 - now_hour) + day_end
    else:  # now_hour < 8
        forecast = fc_today
        house_hours = max(day_end - now_hour, 0)

    free_capacity = ((100 - soc) / 100) * capacity
    expected_house = house_hours * 0.34
    excess = max(forecast - free_capacity - expected_house, 0)
    excess_soc = (excess / capacity) * 100
    target = soc - excess_soc
    return max(target, reserve_soc)


# ---------------------------------------------------------------------------
# Vollständige Automation-Pipeline
# ---------------------------------------------------------------------------


def compute_automation(
    grid_w: float,
    output_now: float,
    now_hour: float,
    evening_start: float,
    soc: float,
    reserve_soc: float,
    soll_soc: float,
    solar_input: float,
    forecast_kwh: float,
    capacity: float,
) -> dict:
    """
    Führt die komplette Automation-Berechnung aus.

    Gibt ein Dict mit allen Zwischen- und Endwerten zurück,
    damit Tests jeden Schritt prüfen können.

    Hinweis: ``soll_soc`` wird vom Aufrufer vorbereitet übergeben, weil die
    vollständige Berechnung zusätzlich den aktiven Forecast ``fc_today_rest``
    benötigt, der nicht Teil dieses Funktions-Interfaces ist.
    """
    in_deadband = compute_deadband(grid_w)
    regulator_target = compute_regulator_target(grid_w, output_now)

    hours_to_target = compute_hours_to_target(now_hour, evening_start)
    house_hours = compute_house_hours(now_hour, evening_start)
    house_energy_kwh = house_hours * 0.34
    free_capacity_kwh = ((100 - soc) / 100) * capacity
    expected_surplus_kwh = max(forecast_kwh - house_energy_kwh - free_capacity_kwh, 0)

    if hours_to_target > 0:
        planned_export_w = (expected_surplus_kwh * 1000) / hours_to_target
    else:
        planned_export_w = 0.0

    selling_allowed = compute_selling_allowed(soc, reserve_soc, soll_soc)
    export_bonus = planned_export_w if selling_allowed else 0.0

    mppt_bonus = compute_mppt_bonus(solar_input)

    raw_target = regulator_target + export_bonus + mppt_bonus
    target_output = compute_target_output(raw_target)

    should_update = compute_should_update(output_now, target_output)

    return {
        "in_deadband": in_deadband,
        "regulator_target": regulator_target,
        "hours_to_target": hours_to_target,
        "house_energy_kwh": house_energy_kwh,
        "expected_surplus_kwh": expected_surplus_kwh,
        "planned_export_w": planned_export_w,
        "selling_allowed": selling_allowed,
        "export_bonus": export_bonus,
        "mppt_bonus": mppt_bonus,
        "raw_target": raw_target,
        "target_output": target_output,
        "should_update": should_update,
    }
