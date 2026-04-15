# Spritter Home Assistant Add-On

This repository provides a Home Assistant add-on that periodically fetches fuel prices and publishes updates directly to MQTT.

## Installation

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
2. Open the menu (top-right) and select **Repositories**.
3. Add this repository URL: `https://github.com/spritter-org/spritter-ha`
4. Open **Spritter Add-On** from the store and install it.
5. Create `/addon_configs/<slug>/spritter_config.json` and start the add-on.

## Configuration

The add-on reads `/data/spritter_config.json`.

```json
{
  "refresh_interval_seconds": 300,
  "max_parallelism": 6,
  "mqtt": {
    "host": "core-mosquitto",
    "port": 1883,
    "username": "mqtt-user",
    "password": "mqtt-password",
    "topic_prefix": "spritter/stations",
    "client_id": "spritter-addon",
    "qos": 0,
    "retain": false
  },
  "stations": [
    {
      "provider": "jet",
      "station_id": "2640f98f48",
      "name": "JET Example"
    }
  ]
}
```

## Published Topics

- Per station: `<topic_prefix>/<provider>/<station_id>`
- Cycle summary: `<topic_prefix>/_summary`

Each station topic payload contains `generated_at`, `refresh_interval_seconds`, and `station` (provider, station_id, name, prices).

## Notes

- The old `custom_components` integration has been removed.
- Station fetches run asynchronously with a default max parallelism of 6.
- A failed station fetch does not block other station updates.
