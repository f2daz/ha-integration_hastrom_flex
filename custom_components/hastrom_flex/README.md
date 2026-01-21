# Stadtwerk Haßfurt haStrom Flex Integration für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

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

## Sensor-Attribute

Der Sensor stellt folgende Attribute bereit:

| Attribut | Beschreibung |
|----------|--------------|
| `current_price` | Aktueller Strompreis (ct/kWh) |
| `today` | Liste aller Preise für heute (24 Werte) |
| `tomorrow` | Liste aller Preise für morgen (24 Werte, ab ca. 13 Uhr verfügbar) |
| `tomorrow_valid` | Boolean, ob morgige Preise verfügbar sind |
| `raw_today` | Liste mit Zeitstempeln für heute |
| `raw_tomorrow` | Liste mit Zeitstempeln für morgen |
| `average` | Durchschnittspreis heute |
| `min` | Minimaler Preis heute |
| `max` | Maximaler Preis heute |
| `median` | Median-Preis heute |
| `tariff` | Name des gewählten Tarifs |
| `tariff_type` | Tarif-Typ (flex, flex_pro, raw) |
| `unit` | Einheit (ct/kWh) |
| `additional_costs_current_hour` | Zusätzliche Kosten für aktuelle Stunde |

## Verwendung in Automationen

### Beispiel 1: Waschmaschine bei günstigem Strompreis starten

```yaml
automation:
  - alias: "Waschmaschine bei günstigem Preis"
    trigger:
      - platform: numeric_state
        entity_id: sensor.hastrom_flex_flex
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

### Beispiel 2: Benachrichtigung für morgen günstigste Stunde

```yaml
automation:
  - alias: "Günstigste Stunde morgen"
    trigger:
      - platform: state
        entity_id: sensor.hastrom_flex_flex
        attribute: tomorrow_valid
        to: true
    action:
      - service: notify.mobile_app
        data:
          title: "Strompreise morgen"
          message: >
            Minimaler Preis morgen: {{ state_attr('sensor.hastrom_flex_flex', 'min') }} ct/kWh
            Durchschnitt: {{ state_attr('sensor.hastrom_flex_flex', 'average') }} ct/kWh
```

### Beispiel 3: Template-Sensor für günstigste Stunden heute

```yaml
template:
  - sensor:
      - name: "Günstigste Stunden heute"
        state: >
          {% set prices = state_attr('sensor.hastrom_flex_flex', 'today') %}
          {% set min_price = state_attr('sensor.hastrom_flex_flex', 'min') %}
          {% set threshold = min_price * 1.1 %}
          {{ prices | select('<=', threshold) | list | length }}
        unit_of_measurement: "Stunden"
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
  - entity: sensor.hastrom_flex_flex
    name: Strompreis
    type: column
    data_generator: |
      const today = entity.attributes.raw_today;
      const tomorrow = entity.attributes.raw_tomorrow || [];
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
- Steuern: 5,95 ct/kWh
- Netzkosten: 6,16 ct/kWh
- Marge: 3,45 ct/kWh
- Grundgebühr: 210,06 €/Jahr
- MwSt: 19%

### haStrom Flex Pro
- Minimalpreis: 3,45 ct/kWh
- Maximalpreis: Keine Obergrenze
- Steuern: 5,95 ct/kWh
- Netzkosten: 6,16 ct/kWh
- Marge: 3,45 ct/kWh
- Grundgebühr: 210,06 €/Jahr
- MwSt: 19%

## Troubleshooting

### Sensor zeigt keine Daten

1. Überprüfen Sie die Home Assistant Logs: `Einstellungen` → `System` → `Protokolle`
2. Stellen Sie sicher, dass Ihre Home Assistant Instanz `http://eex.stwhas.de` erreichen kann
3. Warten Sie bis zur nächsten vollen Stunde (Daten werden alle 15 Minuten aktualisiert)

### Morgige Preise nicht verfügbar

Die Preise für den nächsten Tag werden normalerweise gegen 13-14 Uhr veröffentlicht. Das ist normal für Day-Ahead-Marktpreise.

### Template-Fehler

Überprüfen Sie die Syntax Ihres Templates:
- Muss ein gültiges Jinja2-Template sein
- Muss einen Float-Wert zurückgeben
- Die Variable `current_price` ist verfügbar

## Support

Bei Problemen oder Fragen:
- [GitHub Issues](https://github.com/f2daz/ha-integration_hastrom_flex/issues)
- [Home Assistant Community Forum](https://community.home-assistant.io/)

## Lizenz

MIT License

## Credits

Entwickelt für die Integration der Stadtwerk Haßfurt haStrom Flex Tarife in Home Assistant.

Basierend auf der [Nordpool Integration](https://github.com/custom-components/nordpool).
