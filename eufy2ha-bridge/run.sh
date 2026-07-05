#!/usr/bin/with-contenv bashio

# Build /app/config.json from add-on options + MQTT service credentials.
CONFIG=/app/config.json

WS_HOST="$(bashio::config 'ws_host')"
WS_PORT="$(bashio::config 'ws_port')"
HB="$(bashio::config 'homebase_sn')"
POLL="$(bashio::config 'poll_interval')"
RESET="$(bashio::config 'motion_reset_seconds')"

# MQTT from the Supervisor mqtt service (fallback to add-on-less defaults)
if bashio::services.available "mqtt"; then
    MQTT_HOST="$(bashio::services 'mqtt' 'host')"
    MQTT_PORT="$(bashio::services 'mqtt' 'port')"
    MQTT_USER="$(bashio::services 'mqtt' 'username')"
    MQTT_PASS="$(bashio::services 'mqtt' 'password')"
else
    bashio::log.warning "No MQTT service; falling back to localhost:1883 anonymous"
    MQTT_HOST="127.0.0.1"; MQTT_PORT="1883"; MQTT_USER=""; MQTT_PASS=""
fi

# cameras[] -> {serial: {key,name}}
CAMS_JSON="$(bashio::config 'cameras | reduce .[] as $c ({}; . + {($c.serial): {key: $c.key, name: $c.name}})')"

jq -n \
  --arg ws_host "$WS_HOST" --argjson ws_port "$WS_PORT" \
  --arg hb "$HB" --argjson poll "$POLL" --argjson reset "$RESET" \
  --arg mqtt_host "$MQTT_HOST" --argjson mqtt_port "$MQTT_PORT" \
  --arg mqtt_user "$MQTT_USER" --arg mqtt_pass "$MQTT_PASS" \
  --argjson cams "$CAMS_JSON" \
  '{ws_host:$ws_host, ws_port:$ws_port, homebase_sn:$hb, poll_interval:$poll,
    motion_reset_seconds:$reset, mqtt_host:$mqtt_host, mqtt_port:$mqtt_port,
    mqtt_user:$mqtt_user, mqtt_pass:$mqtt_pass, cameras:$cams}' > "$CONFIG"

bashio::log.info "eufy2ha bridge starting (ws ${WS_HOST}:${WS_PORT}, mqtt ${MQTT_HOST}:${MQTT_PORT})"
exec python3 -m eufy2ha.bridge
