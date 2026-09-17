# Stadtwerk Haßfurt haStrom Flex — Entitäten-Referenz

Installation, Konfiguration und Tarifübersicht stehen in der
[README im Repository-Wurzelverzeichnis](../../README.md). Diese Datei
beschreibt nur, welche Entitäten die Integration anlegt und welche Attribute
daran hängen.

## Angelegte Sensoren

Pro eingerichtetem Tarif entsteht ein Gerät mit **sieben** Sensoren:

| Anzeigename | Zustand | Zweck |
|---|---|---|
| `<Tarif> Aktueller Preis` | Preis in ct/kWh | Preis der laufenden Stunde, inkl. zusätzlicher Kosten |
| `<Tarif> Durchschnitt` | Preis in ct/kWh | Mittelwert heute |
| `<Tarif> Minimum` | Preis in ct/kWh | Niedrigster Preis heute |
| `<Tarif> Maximum` | Preis in ct/kWh | Höchster Preis heute |
| `<Tarif> Median` | Preis in ct/kWh | Median heute |
| `<Tarif> Preise Heute` | z. B. `24 Stunden` | Sammelsensor, Preise im Attribut |
| `<Tarif> Preise Morgen` | z. B. `Noch nicht verfügbar` | Sammelsensor, ab ca. 13 Uhr gefüllt |

`<Tarif>` ist „haStrom Flex", „haStrom Flex Pro" oder „EPEX Spot (Raw)".

> **Zur entity_id:** Home Assistant bildet sie beim ersten Anlegen aus dem
> Anzeigenamen und macht sie danach nicht mehr von selbst rückgängig. Sie kann
> also je nach Instanz abweichen, etwa wenn Entitäten umbenannt wurden oder aus
> einer älteren Version stammen. Die tatsächlichen IDs stehen unter
> **Entwicklerwerkzeuge → Zustände**, Filter `hastrom_flex`. In den Beispielen
> unten steht `sensor.DEIN_PREIS_SENSOR` als Platzhalter für den
> „Aktueller Preis"-Sensor.

Die fünf Preis-Sensoren tragen `state_class: measurement` und landen damit in der
Langzeitstatistik. Bewusst **ohne** `device_class`: `monetary` verlangt eine reine
Währungseinheit, hier ist die Einheit ct/kWh.

## Attribute am Sensor „Aktueller Preis"

| Attribut | Beschreibung |
|---|---|
| `today` | Liste aller Preise für heute |
| `tomorrow` | Liste aller Preise für morgen |
| `tomorrow_valid` | `true`, sobald mindestens 23 Werte für morgen vorliegen |
| `raw_today` | Liste aus `start`, `end`, `value` für heute |
| `raw_tomorrow` | dito für morgen |
| `average`, `min`, `max`, `median` | Statistik für heute |
| `tariff` | Anzeigename des Tarifs |
| `tariff_type` | `flex`, `flex_pro` oder `raw` |
| `unit` | `ct/kWh` |
| `additional_costs_current_hour` | Angewandter Aufschlag der laufenden Stunde |

## Attribute an „Preise Heute" / „Preise Morgen"

| Attribut | Beschreibung |
|---|---|
| `prices` | Liste der Preise |
| `raw_data` | Liste aus `start`, `end`, `value` |
| `tariff` | Anzeigename des Tarifs |
| `unit` | `ct/kWh` |
| `valid` | nur bei „Preise Morgen": `true` ab 23 Werten |

## Beispiele

### Waschmaschine bei günstigem Preis starten

```yaml
automation:
  - alias: "Waschmaschine bei günstigem Preis"
    trigger:
      - platform: numeric_state
        entity_id: sensor.DEIN_PREIS_SENSOR
        below: 20
    condition:
      - condition: time
        after: "06:00:00"
        before: "22:00:00"
    action:
      - action: switch.turn_on
        target:
          entity_id: switch.waschmaschine
```

### Benachrichtigung, sobald die Preise für morgen da sind

```yaml
automation:
  - alias: "Strompreise morgen"
    trigger:
      - platform: state
        entity_id: sensor.DEIN_PREIS_SENSOR
        attribute: tomorrow_valid
        to: true
    action:
      - action: notify.mobile_app
        data:
          title: "Strompreise morgen"
          message: >
            Minimum: {{ state_attr('sensor.DEIN_PREIS_SENSOR', 'min') }} ct/kWh,
            Durchschnitt: {{ state_attr('sensor.DEIN_PREIS_SENSOR', 'average') }} ct/kWh
```

### Anzahl günstiger Stunden heute

```yaml
template:
  - sensor:
      - name: "Günstige Stunden heute"
        unit_of_measurement: "h"
        state: >
          {% set prices = state_attr('sensor.DEIN_PREIS_SENSOR', 'today') or [] %}
          {% set min_price = state_attr('sensor.DEIN_PREIS_SENSOR', 'min') %}
          {% if prices and min_price is not none %}
            {{ prices | select('le', min_price * 1.1) | list | count }}
          {% else %}
            0
          {% endif %}
```

### Apex-Charts-Karte über 48 Stunden

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
  - entity: sensor.DEIN_PREIS_SENSOR
    name: Strompreis
    type: column
    data_generator: |
      const today = entity.attributes.raw_today || [];
      const tomorrow = entity.attributes.raw_tomorrow || [];
      return [...today, ...tomorrow].map(item => [
        new Date(item.start).getTime(),
        item.value,
      ]);
    color: "#931041"
```
