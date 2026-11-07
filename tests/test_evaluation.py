"""Tests der Verbrauchs-/Tankungslogik (ohne Home Assistant lauffähig)."""

from datetime import date, timedelta
import importlib.util
from pathlib import Path
import sys

_spec = importlib.util.spec_from_file_location(
    "evaluation",
    Path(__file__).parents[1] / "custom_components" / "oilview" / "evaluation.py",
)
evaluation = importlib.util.module_from_spec(_spec)
sys.modules["evaluation"] = evaluation  # nötig für @dataclass
_spec.loader.exec_module(evaluation)


def _reihe(start: date, tage: int, stand: float, pro_tag: float, rauschen=(0,)):
    werte = {}
    for i in range(tage):
        werte[(start + timedelta(days=i)).isoformat()] = (
            stand - pro_tag * i + rauschen[i % len(rauschen)]
        )
    return werte


def test_verbrauch_unter_schwelle_geht_nicht_verloren():
    start = date(2026, 1, 1)
    werte = _reihe(start, 31, 2000, 3)  # 3 l/Tag < 5 l Schwelle
    punkte = evaluation.build_points(werte, start, date(2026, 1, 31), None)
    b = evaluation.evaluate(punkte, 5, 50)
    # 30 Tage x 3 l = 90 l, Zählung in 6-l-Schritten -> 90 l
    assert b.wert("monate", "2026-01", "verbrauch") == 90


def test_rauschen_wird_ignoriert():
    start = date(2026, 1, 1)
    werte = _reihe(start, 61, 2000, 8, rauschen=(0, 6, -4, 3))
    punkte = evaluation.build_points(werte, start, date(2026, 3, 1), None)
    b = evaluation.evaluate(punkte, 5, 50)
    gesamt = b.wert("jahre", "2026", "verbrauch")
    # 1.1. bis 1.3. = 59 Tage x 8 l = 472 l echter Verbrauch;
    # Rauschen verschiebt nur den Zeitpunkt, es verdoppelt nichts
    assert abs(gesamt - 472) <= 8


def test_tankung_wird_erkannt_und_nicht_als_verbrauch_gezaehlt():
    start = date(2026, 11, 1)
    werte = _reihe(start, 10, 1170, 9)
    for i in range(5, 10):  # Tankung zwischen 5.11. und 6.11. (Mitternacht 6.11.)
        werte[(start + timedelta(days=i)).isoformat()] += 1030
    punkte = evaluation.build_points(werte, start, date(2026, 11, 10), None)
    b = evaluation.evaluate(punkte, 5, 50)
    assert b.wert("monate", "2026-11", "getankt") == 1030 - 9
    assert b.wert("monate", "2026-11", "verbrauch") == 9 * 9 - 9


def test_laufender_tag_mit_aktuellem_stand():
    start = date(2026, 11, 1)
    werte = {"2026-11-01": 1170.0, "2026-11-07": 1100.0}
    punkte = evaluation.build_points(werte, start, date(2026, 11, 7), 1090.0)
    b = evaluation.evaluate(punkte, 5, 50)
    assert b.wert("tage", "2026-11-07", "verbrauch") == 10
    assert b.wert("monate", "2026-11", "verbrauch") == 80


def test_monatsgrenze():
    werte = {"2026-10-31": 1200.0, "2026-11-01": 1190.0, "2026-11-02": 1180.0}
    punkte = evaluation.build_points(werte, date(2026, 10, 1), date(2026, 11, 2), None)
    b = evaluation.evaluate(punkte, 5, 50)
    # Mitternacht 1.11. schließt den 31.10. ab
    assert b.wert("monate", "2026-10", "verbrauch") == 10
    assert b.wert("monate", "2026-11", "verbrauch") == 10
