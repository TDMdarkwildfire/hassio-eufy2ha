# eufy2ha Bridge

Push-freie Bewegungserkennung + Event-Thumbnails für Eufy-Kameras.

Der Eufy-Push ist seit der eufy_mega-Cloud-Umstellung (Juni 2026) upstream
kaputt (client #933: Registrierung ok, aber keine Zustellung). Diese Bridge
umgeht das: sie **pollt** `station.database_query_latest_info` über
eufy-security-ws, erkennt neue Aufnahmen am steigenden `event_count`, lädt das
Event-Thumbnail (`download_image`) und veröffentlicht Bewegung + Bild + Zeitpunkt
per MQTT-Discovery nach Home Assistant.

## Voraussetzungen
- Add-on **eufy-security-ws (patched)** (oder Original) läuft auf Port 3000.
- MQTT-Broker (Mosquitto-Add-on) — wird automatisch über den Supervisor bezogen.

## Konfiguration
- `homebase_sn`: Seriennummer der HomeBase (z. B. `T8010…`).
- `cameras`: Liste `{serial, key, name}` je Kamera. `key` = kurzer Slug für
  Entity-IDs (`image.<key>_eufy2ha_letztes_event`), `name` = Anzeigename.
- `poll_interval` (Sek.), `motion_reset_seconds` (Bewegungsmelder-Auto-Aus).

## Entities je Kamera
- `image.<key>_eufy2ha_letztes_event` — letztes Event-Thumbnail
- `binary_sensor.<key>_eufy2ha_bewegung` — Bewegung (Puls)
- `sensor.<key>_eufy2ha_letztes_event` — Zeitstempel (+ count/delta)
