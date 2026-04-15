#!/usr/bin/with-contenv bashio
set -e

export MQTT_HOST="$(bashio::services mqtt host)"
export MQTT_PORT="$(bashio::services mqtt port)"
export MQTT_USERNAME="$(bashio::services mqtt username)"
export MQTT_PASSWORD="$(bashio::services mqtt password)"

bashio::log.info "Waiting for MQTT broker to become available..."
bashio::net.wait_for "${MQTT_PORT}" "${MQTT_HOST}" 90
bashio::log.info "MQTT is up. Starting Spritter..."

exec python /app/server.py