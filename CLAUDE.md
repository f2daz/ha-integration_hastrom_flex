# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projekt

HACS-Custom-Integration für Home Assistant, die die dynamischen Stromtarife
**haStrom Flex** der Stadtwerk Haßfurt GmbH als Sensoren einbindet. Domain:
`hastrom_flex`. Gesamter Code liegt in `custom_components/hastrom_flex/`.

Abgeleitet von der [Nordpool-Integration](https://github.com/custom-components/nordpool) —
Aufbau von `events.py`, `aio_price.py` und der Dispatcher-Mechanik stammt von dort.

## Kommandos

Es gibt **keine Test-Suite, kein Lint-Setup, keinen Build und keine CI** in diesem
Repo. Getestet wird gegen eine laufende Home-Assistant-Instanz:

```bash
# Syntax-Check aller Module
python3 -m compileall -q custom_components/hastrom_flex

# JSON-Dateien validieren (manifest, hacs, translations)
for f in custom_components/hastrom_flex/*.json custom_components/hastrom_flex/translations/*.json; do
  python3 -m json.tool "$f" > /dev/null && echo "OK $f"
done

# Deployment in eine lokale HA-Instanz (Pfad anpassen) + Neustart erforderlich
rsync -a --delete custom_components/hastrom_flex/ <ha-config>/custom_components/hastrom_flex/
```

Zum Debuggen in `configuration.yaml` der Testinstanz:

```yaml
logger:
  logs:
    custom_components.hastrom_flex: debug
```

## Architektur

### Datenfluss

```
HaStromFlexApi (aio_price.py)   HTTP GET  http://eex.stwhas.de/api/spotprices[...]
        ↓ _parse_response()     → {"tariff_info": …, "values": [{start, end, data}]}
HaStromFlexData (__init__.py)   Singleton in hass.data[DOMAIN], Cache today/tomorrow je Tarif
        ↓ async_dispatcher_send(EVENT_NEW_HOUR | _DAY | _PRICE)
7 × HaStromFlexBaseSensor (sensor.py)  holen sich die Daten selbst ab, rechnen selbst
```

**Kein DataUpdateCoordinator.** Stattdessen ein Singleton-Datenhalter plus
Dispatcher-Signale. Wichtige Konsequenzen:

- `hass.data[DOMAIN]` wird nur beim **ersten** Config-Entry angelegt und trägt die
  drei globalen Zeit-Listener; alle Entries teilen es sich. `async_unload_entry`
  räumt es deshalb erst ab, wenn kein anderer Entry mehr `LOADED` ist. Diese
  Asymmetrie — Aufbau beim ersten, Abbau beim letzten — muss erhalten bleiben,
  sonst legt das Entladen eines Tarifs die übrigen still.
- Jeder Sensor hält eine eigene Kopie von `_data_today`/`_data_tomorrow` und
  berechnet Preise, Statistik und `raw_*`-Listen für sich. Änderungen an der
  Preislogik gehören deshalb in `HaStromFlexBaseSensor`, nicht in die Unterklassen.
- `SENTINEL` (aus `const.py`) unterscheidet „noch nie geladen" von „leer geladen" —
  nicht durch `None` ersetzen, `handle_new_hour()` hängt daran.

### Zeitsteuerung (`events.py` + `__init__.py`)

Drei Listener, registriert einmalig beim ersten Entry:

| Signal | Auslöser | Zweck |
|---|---|---|
| `EVENT_NEW_HOUR` | alle 15 min (`:00 :15 :30 :45`) | Heute-Daten neu holen, aktuellen Preis + Statistik neu rechnen |
| `EVENT_NEW_DAY` | 00:00 HA-Lokalzeit | Morgen-Daten nach Heute schieben, Morgen leeren |
| `EVENT_NEW_PRICE` | 13:MM:SS **Europe/Berlin** | Day-Ahead-Preise für morgen abrufen |

`events.py` existiert nur, weil HA-Core kein `async_track_time_change` mit expliziter
Zeitzone anbietet — die 13-Uhr-Abholung muss an Berliner Zeit hängen, nicht an der
Zeitzone der HA-Instanz. Minute und Sekunde werden bei Setup zufällig aus
`RANDOM_MINUTE_MIN..MAX` gezogen, um den API-Server nicht zur vollen Minute zu
überrennen.

### Tarif-Abstraktion

Ein Tarif = ein Config-Entry = ein HA-Gerät = 7 Sensoren. Tarifspezifisch sind nur
zwei Stellen in `const.py`:

- `API_ENDPOINT_*` → Mapping auf `HaStromFlexApi._endpoint`
- `PRICE_FIELDS[tariff]["total_price"]` → welches Feld im rohen API-Item den Preis trägt
  (`e_price_has_incl_vat`, `e_price_has_pro_incl_vat`, `epex_spot_price`)

Ein neuer Tarif braucht daher: Konstante + `TARIFF_LIST` + `TARIFF_NAMES` +
`PRICE_FIELDS` + Endpoint, sonst nichts.

### Zusätzliche Kosten

`CONF_ADDITIONAL_COSTS` wird in `_calc_price()` in drei Stufen ausgewertet:
`float()` → `safe_math_eval()` (AST-Whitelist, **kein `eval()`**) → Jinja2-`Template`
mit `current_price` und `now()` im Kontext.

`safe_math_eval` / `_safe_eval_node` / `_SAFE_OPERATORS` sind in `sensor.py` **und**
`config_flow.py` dupliziert (Validierung im Flow, Anwendung im Sensor). Änderungen
immer in beiden Dateien — sonst akzeptiert der Flow Ausdrücke, die der Sensor
ablehnt.

### API-Eigenheiten

- Nur **HTTP**, kein HTTPS (`http://eex.stwhas.de/api`). Nicht „korrigieren".
- **HTTP 500 bedeutet „Daten noch nicht verfügbar"**, nicht Fehler — `_fetch()` gibt
  dafür bewusst `None` zurück statt zu werfen. Betrifft vor allem die Morgen-Preise
  vor ca. 13 Uhr.
- Datumsparameter `start_date` im Format `YYYYMMDD`.
- Preise kommen in ct/kWh inkl. MwSt (außer `raw`), Zeitstempel werden in
  `_parse_response()` nach UTC normalisiert.

## Konventionen

- **Keine `device_class` an den Preis-Sensoren.** `SensorDeviceClass.MONETARY`
  verlangt eine reine Währungseinheit und lässt als `state_class` nur `None` oder
  `TOTAL` zu — die Einheit hier ist aber ct/kWh, und richtig ist `MEASUREMENT`.
  Die Kombination MONETARY + MEASUREMENT erzeugt bei jedem Start eine Warnung je
  Sensor. Nicht „wieder einbauen", auch nicht in `SENSOR_TYPES`.
- **Versionsnummer steht an zwei Stellen**: `manifest.json` → `version` und
  `const.py` → `VERSION`. Immer beide bumpen.
- Docstrings englisch, Inline-Kommentare und Benutzertexte deutsch — so gewachsen,
  beibehalten.
- Entity-Namen/`native_value` von `prices_today`/`prices_tomorrow` sind deutsche
  Strings („3 Stunden", „Noch nicht verfügbar") — Automationen der Nutzer hängen
  daran, nicht beiläufig ändern.
- Übersetzungen in `translations/de.json` und `en.json` parallel pflegen.

## Dokumentation

Zwei READMEs mit unterschiedlicher Aufgabe:

- `README.md` (Wurzel) — Installation, Konfiguration, Tarife, Preisstruktur. Das
  ist die Datei, die HACS rendert.
- `custom_components/hastrom_flex/README.md` — reine Entitäten- und
  Attributreferenz.

Beide waren schon einmal auseinandergelaufen (die innere beschrieb bis 1.1.1 noch
das Ein-Sensor-Layout vor 1.1.0). Wer Sensoren oder Attribute ändert, prüft beide.

**entity_id vs. Anzeigename:** Beide entstehen aus verschiedenen Quellen und
sehen deshalb unterschiedlich aus. Die entity_id folgt der `unique_id`
(`sensor.hastrom_flex_{tariff}_{key}`, englisch), der Anzeigename kommt aus der
`name`-Property (`haStrom Flex Pro Aktueller Preis`, deutsch). An einer laufenden
Instanz gegen die Entity Registry geprüft. Das doppelte `flex_flex` bei
`tariff="flex_pro"` ist kein Fehler, sondern folgt aus dem Präfix in der
`unique_id`. Wer `unique_id` ändert, bricht bestehende Automationen **und** die
Statistik-Historie.
