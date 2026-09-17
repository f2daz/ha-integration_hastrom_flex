# Stadtwerk Haßfurt haStrom Flex — Entitäten-Referenz

Installation, Konfiguration und Tarifübersicht stehen in der
[README im Repository-Wurzelverzeichnis](../../README.md). Diese Datei
beschreibt nur, welche Entitäten die Integration anlegt und welche Attribute
daran hängen.

## Angelegte Sensoren

Pro eingerichtetem Tarif entsteht ein Gerät mit **sieben** Sensoren:

| entity_id | Anzeigename | Zweck |
|---|---|---|
| `sensor.hastrom_flex_<tarif>_current_price` | `<Tarif> Aktueller Preis` | Preis der laufenden Stunde, inkl. zusätzlicher Kosten |
| `sensor.hastrom_flex_<tarif>_average` | `<Tarif> Durchschnitt` | Mittelwert heute |
| `sensor.hastrom_flex_<tarif>_min` | `<Tarif> Minimum` | Niedrigster Preis heute |
| `sensor.hastrom_flex_<tarif>_max` | `<Tarif> Maximum` | Höchster Preis heute |
| `sensor.hastrom_flex_<tarif>_median` | `<Tarif> Median` | Median heute |
| `sensor.hastrom_flex_<tarif>_prices_today` | `<Tarif> Preise Heute` | Sammelsensor, Preise im Attribut |
| `sensor.hastrom_flex_<tarif>_prices_tomorrow` | `<Tarif> Preise Morgen` | Sammelsensor, ab ca. 13 Uhr gefüllt |

`<tarif>` ist `flex`, `flex_pro` oder `raw`; `<Tarif>` entsprechend
„haStrom Flex", „haStrom Flex Pro" oder „EPEX Spot (Raw)".

> **entity_id und Anzeigename unterscheiden sich.** Die entity_id ist englisch
> und folgt der internen `unique_id`, der angezeigte Name ist deutsch. Bei
> `flex_pro` entsteht dabei das doppelte `flex_flex`, etwa
> `sensor.hastrom_flex_flex_pro_current_price` — das ist so gewollt. Wer
> Entitäten in Home Assistant umbenannt hat, hat abweichende IDs; nachsehen unter
> **Entwicklerwerkzeuge → Zustände**, Filter `hastrom_flex`.

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
        entity_id: sensor.hastrom_flex_flex_current_price
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
        entity_id: sensor.hastrom_flex_flex_current_price
        attribute: tomorrow_valid
        to: true
    action:
      - action: notify.mobile_app
        data:
          title: "Strompreise morgen"
          message: >
            Minimum: {{ state_attr('sensor.hastrom_flex_flex_current_price', 'min') }} ct/kWh,
            Durchschnitt: {{ state_attr('sensor.hastrom_flex_flex_current_price', 'average') }} ct/kWh
```

### Anzahl günstiger Stunden heute

```yaml
template:
  - sensor:
      - name: "Günstige Stunden heute"
        unit_of_measurement: "h"
        state: >
          {% set prices = state_attr('sensor.hastrom_flex_flex_current_price', 'today') or [] %}
          {% set min_price = state_attr('sensor.hastrom_flex_flex_current_price', 'min') %}
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
  - entity: sensor.hastrom_flex_flex_current_price
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
