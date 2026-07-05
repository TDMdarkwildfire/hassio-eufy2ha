# eufy2ha Add-ons

Home-Assistant-Add-on-Repository für das eufy2ha-Projekt (saubere Eufy-Kamera-
Einbindung, siehe privates Projekt-Repo `eufy2ha`).

## Add-ons

### eufy-security-ws (patched) — `3.1.0-p1`

[bropat/eufy-security-ws](https://github.com/bropat/eufy-security-ws) 3.1.0,
ergänzt um genau ein Feature: das rohe **`push message`**-Event der
eufy-security-client-Bibliothek wird an WebSocket-Clients weitergeleitet
(`{source:"driver", event:"push message", message:{…}}`). Die Payload enthält
u.a. `file_path`/`cipher` fertiger Stations-Aufnahmen — Grundlage für den
Clip-Download nach `/media`.

Quelle des Patches: Fork
[TDMdarkwildfire/eufy-security-ws](https://github.com/TDMdarkwildfire/eufy-security-ws),
Branch `push-message-event` (Build erfolgt lokal beim Add-on-Install).
Drop-in-Ersatz für das Original-Add-on: identische Optionen, identischer Port.

## Installation

Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories →
`https://github.com/TDMdarkwildfire/hassio-eufy2ha`
