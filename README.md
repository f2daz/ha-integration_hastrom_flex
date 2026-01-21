# Stadtwerk Haßfurt haStrom Flex Integration für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/v/release/f2daz/ha-integration_hastrom_flex)](https://github.com/f2daz/ha-integration_hastrom_flex/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Diese Home Assistant Integration ermöglicht die Einbindung der dynamischen Stromtarife **haStrom Flex** und **haStrom Flex Pro** der Stadtwerk Haßfurt GmbH.

## Features

- 🔌 Unterstützung für alle Tarife:
  - **haStrom Flex** (mit Preisober- und -untergrenze)
  - **haStrom Flex Pro** (ohne Preisobergrenze)
  - **EPEX Spot Raw** (reine Börsenpreise)
- ⚡ Stündliche Strompreise basierend auf EPEX Spot
- 📊 Statistische Daten (Min, Max, Durchschnitt, Median)
- 📅 Preise für heute und morgen
- 🕐 Automatische Updates alle 15 Minuten
- 🔄 Automatischer Abruf der morgigen Preise um 13 Uhr
- 💰 Optional: Zusätzliche Kosten via Jinja2-Template

## Installation

### Via HACS (empfohlen)

1. Öffnen Sie HACS in Home Assistant
2. Gehen Sie zu "Integrationen"
3. Klicken Sie auf die drei Punkte oben rechts und wählen Sie "Benutzerdefinierte Repositories"
4. Fügen Sie die Repository-URL hinzu: `https://github.com/f2daz/ha-integration_hastrom_flex`
5. Wählen Sie Kategorie "Integration"
6. Suchen Sie nach "Stadtwerk Haßfurt haStrom Flex" und installieren Sie es
7. Starten Sie Home Assistant neu

### Manuelle Installation

1. Laden Sie die neueste Version herunter
2. Kopieren Sie den Ordner `custom_components/hastrom_flex` in Ihr `config/custom_components/` Verzeichnis
3. Starten Sie Home Assistant neu

## Konfiguration

### Über die UI (empfohlen)

1. Gehen Sie zu **Einstellungen** → **Geräte & Dienste**
2. Klicken Sie auf **+ Integration hinzufügen**
3. Suchen Sie nach "Stadtwerk Haßfurt haStrom Flex"
4. Wählen Sie Ihren Tarif:
   - **haStrom Flex** - Mit Preisgrenzen (Min: 16.78 ct/kWh, Max: 25.82 ct/kWh)
   - **haStrom Flex Pro** - Ohne Preisobergrenze (Min: 3.45 ct/kWh)
   - **EPEX Spot (Raw)** - Reine Börsenpreise ohne Aufschläge
5. Optional: Geben Sie ein Template für zusätzliche Kosten ein (siehe unten)
6. Klicken Sie auf **Absenden**

### Zusätzliche Kosten (Optional)

Sie können zusätzliche Kosten über ein Jinja2-Template hinzufügen, z.B. für:
- Grundgebühr
- Messstellenbetrieb
- Weitere individuelle Kosten

**Beispiele:**

```jinja2
{{0.0|float}}
```
Keine zusätzlichen Kosten (Standard)

```jinja2
{{0.5|float}}
```
Feste zusätzliche Kosten von 0,5 ct/kWh

```jinja2
{{(current_price * 0.1)|float}}
```
10% Aufschlag auf den aktuellen Preis

```jinja2
{{(210.06 / 365 / 24)|round(2)|float}}
```
Umrechnung der Jahresgrundgebühr (210,06 €) auf ct/kWh

Die Variable `current_price` enthält den aktuellen Strompreis in ct/kWh.

## Sensoren

Die Integration erstellt folgende Sensoren pro Tarif:

| Sensor | Beschreibung |
|--------|--------------|
| `sensor.hastrom_flex_{tariff}_current_price` | Aktueller Strompreis (ct/kWh) |
| `sensor.hastrom_flex_{tariff}_average` | Durchschnittspreis heute |
| `sensor.hastrom_flex_{tariff}_min` | Minimaler Preis heute |
| `sensor.hastrom_flex_{tariff}_max` | Maximaler Preis heute |
| `sensor.hastrom_flex_{tariff}_median` | Median-Preis heute |
| `sensor.hastrom_flex_{tariff}_prices_today` | Alle Preise für heute |
| `sensor.hastrom_flex_{tariff}_prices_tomorrow` | Alle Preise für morgen |

## Verwendung in Automationen

### Beispiel: Waschmaschine bei günstigem Strompreis starten

```yaml
automation:
  - alias: "Waschmaschine bei günstigem Preis"
    trigger:
      - platform: numeric_state
        entity_id: sensor.hastrom_flex_flex_current_price
        below: 20
    condition:
      - condition: time
        after: "06:00:00"
        before: "22:00:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.waschmaschine
```

## Apex Charts Lovelace-Karte

Visualisieren Sie die Strompreise mit einer schönen Grafik:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: haStrom Flex Preise
  show_states: true
graph_span: 48h
now:
  show: true
  label: Jetzt
span:
  start: day
series:
  - entity: sensor.hastrom_flex_flex_prices_today
    name: Strompreis
    type: column
    data_generator: |
      const today = entity.attributes.raw_data || [];
      const tomorrow_entity = hass.states['sensor.hastrom_flex_flex_prices_tomorrow'];
      const tomorrow = tomorrow_entity?.attributes?.raw_data || [];
      const data = [];
      today.forEach(item => {
        data.push([new Date(item.start).getTime(), item.value]);
      });
      tomorrow.forEach(item => {
        data.push([new Date(item.start).getTime(), item.value]);
      });
      return data;
    color: "#03a9f4"
```

## API-Details

Die Integration nutzt die öffentliche API des Stadtwerk Haßfurt:

- **Base URL:** `http://eex.stwhas.de/api`
- **Endpunkte:**
  - `/spotprices` - haStrom Flex
  - `/spotprices/flexpro` - haStrom Flex Pro
  - `/spotprices/raw` - EPEX Spot Raw

**Hinweis:** Die API ist nur über HTTP (nicht HTTPS) erreichbar.

## Preisstruktur

### haStrom Flex
- Minimalpreis: 16,78 ct/kWh
- Maximalpreis: 25,82 ct/kWh
- Grundgebühr: 210,06 €/Jahr
- MwSt: 19%

### haStrom Flex Pro
- Minimalpreis: 3,45 ct/kWh
- Maximalpreis: Keine Obergrenze
- Grundgebühr: 210,06 €/Jahr
- MwSt: 19%

## Troubleshooting

### Sensor zeigt keine Daten

1. Überprüfen Sie die Home Assistant Logs: `Einstellungen` → `System` → `Protokolle`
2. Stellen Sie sicher, dass Ihre Home Assistant Instanz `http://eex.stwhas.de` erreichen kann
3. Warten Sie bis zur nächsten vollen Stunde (Daten werden alle 15 Minuten aktualisiert)

### Morgige Preise nicht verfügbar

Die Preise für den nächsten Tag werden normalerweise gegen 13-14 Uhr veröffentlicht. Das ist normal für Day-Ahead-Marktpreise.

## Support

Bei Problemen oder Fragen:
- [GitHub Issues](https://github.com/f2daz/ha-integration_hastrom_flex/issues)
- [Home Assistant Community Forum](https://community.home-assistant.io/)

## Lizenz

MIT License - siehe [LICENSE](LICENSE) Datei

## Credits

Entwickelt für die Integration der Stadtwerk Haßfurt haStrom Flex Tarife in Home Assistant.

Basierend auf der [Nordpool Integration](https://github.com/custom-components/nordpool).
