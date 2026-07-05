#!/usr/bin/with-contenv bashio

# Build /app/config.json from add-on options + MQTT service credentials.
CONFIG=/app/config.json

WS_HOST="$(bashio::config 'ws_host')"
WS_PORT="$(bashio::config 'ws_port')"
HB="$(bashio::config 'homebase_sn')"
POLL="$(bashio::config 'poll_interval')"
RESET="$(bashio::config 'motion_reset_seconds')"
GO2RTC="$(bashio::config 'go2rtc_url')"
CC_ON="$(bashio::config 'concierge_enabled')"
CC_GRACE="$(bashio::config 'concierge_grace_seconds')"
CC_INT="$(bashio::config 'concierge_interval')"
NOTIFY="$(bashio::config 'notify_service')"

# Home Assistant API for the concierge (stop_p2p_livestream). homeassistant_api:
# true provides SUPERVISOR_TOKEN; the bridge reads it from the env.
export HA_URL="http://supervisor/core/api"

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

# cameras[] -> {serial: {key,name,entity}}
CAMS_JSON="$(bashio::config 'cameras | reduce .[] as $c ({}; . + {($c.serial): {key: $c.key, name: $c.name, entity: ($c.entity // "")}})')"

jq -n \
  --arg ws_host "$WS_HOST" --argjson ws_port "$WS_PORT" \
  --arg hb "$HB" --argjson poll "$POLL" --argjson reset "$RESET" \
  --arg mqtt_host "$MQTT_HOST" --argjson mqtt_port "$MQTT_PORT" \
  --arg mqtt_user "$MQTT_USER" --arg mqtt_pass "$MQTT_PASS" \
  --arg go2rtc "$GO2RTC" --arg ha_url "$HA_URL" --arg notify "$NOTIFY" \
  --argjson cc_on "$CC_ON" --argjson cc_grace "$CC_GRACE" --argjson cc_int "$CC_INT" \
  --argjson cams "$CAMS_JSON" \
  '{ws_host:$ws_host, ws_port:$ws_port, homebase_sn:$hb, poll_interval:$poll,
    motion_reset_seconds:$reset, mqtt_host:$mqtt_host, mqtt_port:$mqtt_port,
    mqtt_user:$mqtt_user, mqtt_pass:$mqtt_pass, go2rtc_url:$go2rtc, ha_url:$ha_url,
    notify_service:$notify, concierge_enabled:$cc_on, concierge_grace_seconds:$cc_grace,
    concierge_interval:$cc_int, cameras:$cams}' > "$CONFIG"

bashio::log.info "eufy2ha bridge starting (ws ${WS_HOST}:${WS_PORT}, mqtt ${MQTT_HOST}:${MQTT_PORT}, concierge ${CC_ON})"
exec python3 -m eufy2ha.bridge
