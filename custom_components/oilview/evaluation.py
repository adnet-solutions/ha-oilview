"""Auswertung der Tankstände – ohne Abhängigkeit von Home Assistant (testbar)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class Bilanz:
    """Verbrauch und Tankungen, aufgeschlüsselt nach Tag, Monat und Jahr."""

    tage: dict[str, dict[str, float]] = field(default_factory=dict)
    monate: dict[str, dict[str, int]] = field(default_factory=dict)
    jahre: dict[str, dict[str, int]] = field(default_factory=dict)

    def wert(self, ebene: str, key: str, art: str) -> int:
        """Gerundeten Wert holen, z. B. wert("monate", "2026-11", "verbrauch")."""
        tabelle = getattr(self, ebene)
        return round(tabelle.get(key, {}).get(art, 0))


def build_points(
    midnight_levels: dict[str, float],
    start: date,
    today: date,
    current: float | None,
) -> list[tuple[date, float]]:
    """Messpunkte bauen.

    Der Stand um 00:00 Uhr am Tag D schließt den Tag D-1 ab. Der erste
    Mitternachtswert ist nur Ausgangspunkt. Der aktuelle Stand schließt den
    laufenden Tag (bis jetzt) ab.
    """
    werte = sorted(
        (date.fromisoformat(k), v)
        for k, v in midnight_levels.items()
        if start <= date.fromisoformat(k) <= today
    )
    punkte: list[tuple[date, float]] = []
    if werte:
        punkte.append(werte[0])
        punkte.extend((d - timedelta(days=1), v) for d, v in werte[1:])
    if current is not None:
        punkte.append((today, current))
    return punkte


def evaluate(
    punkte: list[tuple[date, float]],
    consumption_threshold: float,
    refill_threshold: float,
) -> Bilanz:
    """Verbrauch und Tankungen mit Hysterese berechnen.

    Ein Referenzstand wird gehalten, bis der Stand mindestens
    ``consumption_threshold`` darunter liegt (dann zählt der volle Unterschied
    als Verbrauch) oder mindestens ``refill_threshold`` darüber (dann zählt er
    als Tankung). Kleinere Bewegungen sind Messrauschen. Dadurch geht kein
    Liter verloren, er wird höchstens etwas später gezählt.
    """
    bilanz = Bilanz()
    if not punkte:
        return bilanz

    ref = punkte[0][1]
    for tag, stand in punkte[1:]:
        eintrag = bilanz.tage.setdefault(
            tag.isoformat(), {"verbrauch": 0.0, "getankt": 0.0}
        )
        diff = stand - ref
        if diff <= -consumption_threshold:
            eintrag["verbrauch"] += -diff
            ref = stand
        elif diff >= refill_threshold:
            eintrag["getankt"] += diff
            ref = stand

    bilanz.monate = _summe(bilanz.tage, 7)
    bilanz.jahre = _summe(bilanz.tage, 4)
    return bilanz


def _summe(tage: dict[str, dict[str, float]], laenge: int) -> dict[str, dict[str, int]]:
    summe: dict[str, dict[str, float]] = {}
    for key, werte in tage.items():
        s = summe.setdefault(key[:laenge], {"verbrauch": 0.0, "getankt": 0.0})
        s["verbrauch"] += werte["verbrauch"]
        s["getankt"] += werte["getankt"]
    return {
        k: {art: round(wert) for art, wert in v.items()}
        for k, v in sorted(summe.items())
    }
