"""
Zendure V14.2.2 – pytest-Testsuite

42 Szenarien testen die Python-Portierung der Home Assistant Automation.
Keine echten HA-Abhängigkeiten – reines Python / pytest.
"""

import pytest

from zendure.automation import (
    compute_deadband,
    compute_regulator_target,
    compute_hours_to_target,
    compute_house_hours,
    compute_selling_allowed,
    compute_mppt_bonus,
    compute_target_output,
    compute_should_update,
    compute_reserve_soc,
    compute_soll_soc,
    compute_ziel_soc,
    compute_automation,
    DEADBAND_LOW,
    DEADBAND_HIGH,
    SWEETSPOT,
)


# ===========================================================================
# Deadband-Tests (1–5)
# ===========================================================================


def test_deadband_at_sweetspot():
    """Szenario 1: Netzpunkt exakt am Sweetspot → im Deadband, Output unverändert."""
    grid_w = -15
    output_now = 300
    assert compute_deadband(grid_w) is True
    assert compute_regulator_target(grid_w, output_now) == output_now


def test_deadband_just_above_high_boundary():
    """Szenario 2: Netzpunkt knapp oberhalb Deadband-Obergrenze → außerhalb."""
    grid_w = -4  # -4 > -5 = DEADBAND_HIGH
    assert compute_deadband(grid_w) is False
    # Regelung muss eingreifen: regulator_target != output_now
    assert compute_regulator_target(grid_w, 200) != 200


def test_deadband_just_below_low_boundary():
    """Szenario 3: Netzpunkt knapp unterhalb Deadband-Untergrenze → außerhalb."""
    grid_w = -36  # -36 < -35 = DEADBAND_LOW
    assert compute_deadband(grid_w) is False
    assert compute_regulator_target(grid_w, 200) != 200


def test_deadband_at_low_boundary():
    """Szenario 4: Netzpunkt exakt an der Untergrenze (-35 W) → noch im Deadband."""
    grid_w = -35
    assert compute_deadband(grid_w) is True


def test_deadband_at_high_boundary():
    """Szenario 5: Netzpunkt exakt an der Obergrenze (-5 W) → noch im Deadband."""
    grid_w = -5
    assert compute_deadband(grid_w) is True


# ===========================================================================
# should_update-Tests (6–10)
# ===========================================================================


def test_should_update_switching_on_high_target():
    """Szenario 6: Einschalten aus Standby, Ziel=40 W → should_update=True (>=35)."""
    output_now = 0
    target_output = 40
    assert compute_should_update(output_now, target_output) is True


def test_should_update_switching_on_low_target():
    """Szenario 7: Einschalten aus Standby, Ziel=30 W → should_update=False (<35)."""
    output_now = 0
    target_output = 30
    assert compute_should_update(output_now, target_output) is False


def test_should_update_large_diff():
    """Szenario 8: Laufender Betrieb, Differenz=6 W → should_update=True (>=5)."""
    output_now = 200
    target_output = 206
    assert compute_should_update(output_now, target_output) is True


def test_should_update_small_diff():
    """Szenario 9: Laufender Betrieb, Differenz=3 W → should_update=False (<5)."""
    output_now = 200
    target_output = 203
    assert compute_should_update(output_now, target_output) is False


def test_should_update_target_below_5w():
    """Szenario 10: output_now=0, target=4 W → kein switching_on (target<5), diff=4 <5 → False."""
    output_now = 0
    target_output = 4  # target < 5 → switching_on_discharge ist False
    assert compute_should_update(output_now, target_output) is False


# ===========================================================================
# selling_allowed-Tests (11–15)
# ===========================================================================


def test_selling_not_allowed_soc_below_soll():
    """Szenario 11: SOC=45, Reserve=20, Soll=60 → Verkauf gesperrt (SOC < Soll)."""
    assert compute_selling_allowed(soc=45, reserve_soc=20, soll_soc=60) is False


def test_selling_allowed_soc_above_both():
    """Szenario 12: SOC=65, Reserve=20, Soll=60 → Verkauf erlaubt."""
    assert compute_selling_allowed(soc=65, reserve_soc=20, soll_soc=60) is True


def test_selling_allowed_soc_just_above_both():
    """Szenario 13: SOC=21, Reserve=20, Soll=19 → Verkauf erlaubt (SOC knapp über beiden)."""
    assert compute_selling_allowed(soc=21, reserve_soc=20, soll_soc=19) is True


def test_selling_not_allowed_soc_below_reserve():
    """Szenario 14: SOC=19, Reserve=20 → Verkauf gesperrt (SOC unter Reserve)."""
    assert compute_selling_allowed(soc=19, reserve_soc=20, soll_soc=15) is False


def test_selling_not_allowed_soc_equals_reserve():
    """Szenario 15: SOC=20, Reserve=20 → Verkauf gesperrt (nicht strikt größer)."""
    assert compute_selling_allowed(soc=20, reserve_soc=20, soll_soc=15) is False


# ===========================================================================
# MPPT-Bonus-Tests (16–22)
# ===========================================================================


def test_mppt_bonus_below_threshold():
    """Szenario 16: Solar=1919 W → unter Schwelle, MPPT-Bonus=0."""
    assert compute_mppt_bonus(1919) == 0


def test_mppt_bonus_at_threshold():
    """Szenario 17: Solar=1920 W → genau Schwelle, over=0, MPPT-Bonus=0."""
    assert compute_mppt_bonus(1920) == 0


def test_mppt_bonus_one_50w_step():
    """Szenario 18: Solar=1970 W → over=50, stepped=50, MPPT-Bonus=50."""
    assert compute_mppt_bonus(1970) == 50


def test_mppt_bonus_truncated_to_50w_step():
    """Szenario 19: Solar=1980 W → over=60, abgerundet auf 50 W-Stufe → MPPT-Bonus=50."""
    assert compute_mppt_bonus(1980) == 50


def test_mppt_bonus_maximum_exact():
    """Szenario 20: Solar=2720 W → over=800, stepped=800, MPPT-Bonus=800 (Maximum)."""
    assert compute_mppt_bonus(2720) == 800


def test_mppt_bonus_capped_at_800w():
    """Szenario 21: Solar=2800 W → over=880, stepped=850, gedeckelt auf 800 W."""
    assert compute_mppt_bonus(2800) == 800


def test_mppt_bonus_80w_over():
    """Szenario 22: Solar=2000 W → over=80, stepped=50, MPPT-Bonus=50."""
    assert compute_mppt_bonus(2000) == 50


# ===========================================================================
# target_output Clamp-Tests (23–25)
# ===========================================================================


def test_target_output_clamp_negative():
    """Szenario 23: raw_target=-50 → target_output=0 (Clamp auf 0)."""
    assert compute_target_output(-50) == 0


def test_target_output_clamp_over_800():
    """Szenario 24: raw_target=850 → target_output=800 (Clamp auf 800)."""
    assert compute_target_output(850) == 800


def test_target_output_no_clamp():
    """Szenario 25: raw_target=400 → target_output=400 (kein Clamp nötig)."""
    assert compute_target_output(400) == 400


# ===========================================================================
# Reserve-SOC-Tests (26–30)
# ===========================================================================


def test_reserve_soc_summer_no_bad_days():
    """Szenario 26: Sommer (Monat=6), beide Prognosen gut → Reserve=20 %."""
    assert compute_reserve_soc(month=6, day1=8, day2=9) == 20


def test_reserve_soc_summer_one_bad_day():
    """Szenario 27: Sommer, ein Schlechtwettertag (day1=5) → Reserve=30 %."""
    assert compute_reserve_soc(month=6, day1=5, day2=9) == 30


def test_reserve_soc_summer_two_bad_days():
    """Szenario 28: Sommer, beide Tage schlecht (day1=5, day2=6) → Reserve=40 %."""
    assert compute_reserve_soc(month=6, day1=5, day2=6) == 40


def test_reserve_soc_winter_no_bad_days():
    """Szenario 29: Winter (Monat=1), gute Prognose → Reserve=50 %."""
    assert compute_reserve_soc(month=1, day1=8, day2=10) == 50


def test_reserve_soc_winter_two_bad_days():
    """Szenario 30: Winter, beide Tage schlecht → Reserve=70 %."""
    assert compute_reserve_soc(month=1, day1=3, day2=4) == 70


# ===========================================================================
# Soll-SOC-Tests (31–35, FIX 3)
# ===========================================================================


def test_soll_soc_fix3_no_division_by_zero():
    """Szenario 31: now_hour=8, day_end=8 → evening-Modus, Soll=100 (kein Division-durch-null).

    FIX 3 stellt sicher, dass span >= 0.01 ist, falls der Day-Branch
    mit day_end==8 erreicht würde. Mit now_hour==day_end greift hier
    der Evening-Branch (soll=100 %), kein Absturz.
    """
    result = compute_soll_soc(now_hour=8.0, day_end=8.0, target_soc=20, start_soc=20)
    assert result == 100.0


def test_soll_soc_night_start_progress_zero():
    """Szenario 32: now_hour=22 → Nacht-Beginn, progress=0, Soll=100 %."""
    result = compute_soll_soc(now_hour=22.0, day_end=16.0, target_soc=20, start_soc=20)
    assert result == 100.0


def test_soll_soc_night_midway_progress_half():
    """Szenario 33: now_hour=3 → Nacht-Mitte, night_elapsed=5, progress=0.5."""
    target_soc = 20
    result = compute_soll_soc(now_hour=3.0, day_end=16.0, target_soc=target_soc, start_soc=20)
    expected = 100 + (target_soc - 100) * 0.5  # = 60
    assert result == pytest.approx(expected)


def test_soll_soc_evening_mode():
    """Szenario 34: now_hour=16, day_end=16 → Abend-Modus, Soll=100 %."""
    result = compute_soll_soc(now_hour=16.0, day_end=16.0, target_soc=20, start_soc=20)
    assert result == 100.0


def test_soll_soc_day_mode_midway():
    """Szenario 35: now_hour=12, day_end=16 → Tagmodus, progress=(12-8)/8=0.5."""
    start_soc = 20
    result = compute_soll_soc(now_hour=12.0, day_end=16.0, target_soc=20, start_soc=start_soc)
    expected = start_soc + (100 - start_soc) * 0.5  # = 60
    assert result == pytest.approx(expected)


# ===========================================================================
# Vollständige Integrations-Szenarien (36–42)
# ===========================================================================


def test_integration_neutral_feed_in():
    """Szenario 36: Netzpunkt=-15 W, SOC=70 %, kein Solarüberschuss → kein Update."""
    # Kein Überschuss, weil forecast=0
    result = compute_automation(
        grid_w=-15,
        output_now=300,
        now_hour=14.0,
        evening_start=16.0,
        soc=70,
        reserve_soc=20,
        soll_soc=60,
        solar_input=500,
        forecast_kwh=0,
        capacity=5.0,
    )
    assert result["in_deadband"] is True
    assert result["regulator_target"] == 300  # unverändert im Deadband
    assert result["export_bonus"] == 0.0      # kein Überschuss
    assert result["should_update"] is False   # diff=0 < 5


def test_integration_grid_consumption_compensation():
    """Szenario 37: Netzbezug +100 W → Regler erhöht Output um Fehler."""
    result = compute_automation(
        grid_w=100,
        output_now=200,
        now_hour=14.0,
        evening_start=16.0,
        soc=70,
        reserve_soc=20,
        soll_soc=60,
        solar_input=0,
        forecast_kwh=0,
        capacity=5.0,
    )
    assert result["in_deadband"] is False
    # error = 100 - (-15) = 115 → regulator_target = 200 + 115 = 315
    assert result["regulator_target"] == pytest.approx(315)
    assert result["target_output"] == 315


def test_integration_mppt_protection_active():
    """Szenario 38: Solar=2100 W → MPPT-Bonus=150 W (over=180→stepped=150)."""
    result = compute_automation(
        grid_w=-15,
        output_now=400,
        now_hour=14.0,
        evening_start=16.0,
        soc=90,
        reserve_soc=20,
        soll_soc=50,
        solar_input=2100,
        forecast_kwh=0,
        capacity=5.0,
    )
    assert result["mppt_bonus"] == 150
    # in Deadband → regulator_target=400, raw=400+0+150=550
    assert result["target_output"] == 550


def test_integration_make_room_export():
    """Szenario 39: Platz schaffen – Überschuss=2 kWh, hours=4 → export_bonus=500 W."""
    # soc=80, capacity=5 → free_capacity = 1 kWh
    # evening_start=14, now_hour=10 → house_hours=4, house_energy=1.36 kWh
    # forecast = 1.36 + 1.0 + 2.0 = 4.36 kWh → expected_surplus=2 kWh
    # hours_to_target = 14-10 = 4 → planned_export = 2000/4 = 500 W
    result = compute_automation(
        grid_w=-15,
        output_now=0,
        now_hour=10.0,
        evening_start=14.0,
        soc=80,
        reserve_soc=20,
        soll_soc=60,
        solar_input=500,
        forecast_kwh=4.36,
        capacity=5.0,
    )
    assert result["selling_allowed"] is True
    assert result["expected_surplus_kwh"] == pytest.approx(2.0, abs=1e-6)
    assert result["export_bonus"] == pytest.approx(500.0, abs=1e-3)


def test_integration_no_export_below_soll():
    """Szenario 40: SOC=55 < Soll=60 → selling_allowed=False, export_bonus=0 W."""
    result = compute_automation(
        grid_w=-15,
        output_now=0,
        now_hour=10.0,
        evening_start=14.0,
        soc=55,
        reserve_soc=20,
        soll_soc=60,
        solar_input=500,
        forecast_kwh=4.36,
        capacity=5.0,
    )
    assert result["selling_allowed"] is False
    assert result["export_bonus"] == 0.0


def test_integration_winter_night_two_bad_days():
    """Szenario 41: Winter Nacht, 2 Schlechtwettertage → Reserve=70 %."""
    # Reserve-Berechnung
    reserve = compute_reserve_soc(month=1, day1=4, day2=3)
    assert reserve == 70

    # Stunden-Logik für now_hour=23
    hours = compute_hours_to_target(now_hour=23.0, evening_start=16.0)
    assert hours == pytest.approx(9.0)  # 8 - 23 + 24 = 9


def test_integration_midnight_edge_case():
    """Szenario 42: Mitternacht (now_hour=0) → hours_to_target=8, Nachtlogik aktiv."""
    hours = compute_hours_to_target(now_hour=0.0, evening_start=16.0)
    assert hours == pytest.approx(8.0)  # 8 - 0 = 8

    # Soll-SOC liegt im Nacht-Zweig
    soll = compute_soll_soc(now_hour=0.0, day_end=16.0, target_soc=20, start_soc=20)
    # night_elapsed = 0 + 2 = 2 → progress = 0.2
    expected_soll = 100 + (20 - 100) * 0.2  # = 84
    assert soll == pytest.approx(expected_soll)
