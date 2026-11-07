# OilView (TECSON) für Home Assistant

Inoffizielle Home-Assistant-Integration für das **OilView-Portal von TECSON**
(Tankspion, LX-NET, LX-GSM u. a.). Sie liest den Tankstand über die
[OilView-API](https://api.oilview.de/apidoc/index.html) und berechnet daraus
**Verbrauch und Tankungen pro Tag, Monat und Jahr**, auch rückwirkend.

> Nicht von TECSON. OilView ist eine Marke der TECSON GmbH & Co. KG.

## Sensoren

| Sensor | Beschreibung |
|---|---|
| Tankstand | aktueller Inhalt in Litern (mit Langzeitstatistik) |
| Füllgrad | Prozent laut OilView |
| Verbrauch heute / Monat / Vormonat / Jahr | berechneter Ölverbrauch in Litern |
| Getankt Monat / Jahr | erkannte Tankungen in Litern |
| Gespeicherte Tageswerte | Diagnose: wie viele Tage schon nachgeholt sind |

„Verbrauch heute“ hat die letzten 35 Tage als Attribut `tage`, „Verbrauch
Jahr“ alle Monats- und Jahreswerte als Attribute `monate` und `jahre`.

## So wird gerechnet

Die API liefert über `interpolateAt` den Tankstand zu jedem beliebigen
Zeitpunkt. Die Integration holt dafür einmal pro Tag den Stand um 00:00 Uhr,
ab dem Startdatum rückwirkend, und speichert ihn in Home Assistant. Danach
kommt jede Nacht um 00:15 Uhr der neue Tag dazu.

Füllstandssonden rauschen um einige Liter. Deshalb wird mit einem
**Referenzstand und Hysterese** gerechnet:

- Sinkt der Stand mindestens um die **Verbrauchsschwelle** (Standard 5 l)
  unter den Referenzstand, zählt der **volle** Unterschied als Verbrauch.
  Es geht also kein Liter verloren, er wird höchstens etwas später gezählt.
- Steigt der Stand mindestens um die **Tankungsschwelle** (Standard 50 l),
  zählt das als Tankung, nicht als negativer Verbrauch.
- Kleinere Bewegungen gelten als Messrauschen.

Am Tag einer Tankung wird die getankte Menge um den Verbrauch dieses Tages zu
niedrig angezeigt, weil nur Tageswerte verglichen werden.

## Installation

### HACS
1. HACS → ⋮ → *Benutzerdefinierte Repositories* →
   `https://github.com/adnet-solutions/ha-oilview`, Typ *Integration*.
2. „OilView (TECSON)“ installieren, Home Assistant neu starten.

### Manuell
Ordner `custom_components/oilview` nach `/config/custom_components/` kopieren
und Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → OilView*

1. **API-Token** eingeben (den vergibt TECSON bzw. der OilView-Administrator).
2. **Startdatum** wählen. Ab hier wird rückwirkend gerechnet, Standard ist der
   1. Januar des laufenden Jahres. Das Nachholen läuft im Hintergrund und
   dauert pro Jahr ein paar Minuten.
3. Bei mehreren Tanks den gewünschten auswählen.

Startdatum und Schwellen lassen sich später unter *Konfigurieren* ändern. Ein
früheres Startdatum holt die fehlenden Tage automatisch nach.

Der Token wird nur in Home Assistant gespeichert und ausschließlich an
`www.oilview.de` gesendet.

## Lizenz

[MIT](LICENSE)
