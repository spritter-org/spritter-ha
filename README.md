# Spritter Home Assistant Add-On

This repository provides a Home Assistant add-on that periodically fetches fuel prices and publishes updates directly to MQTT.

## Installation

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
2. Open the menu (top-right) and select **Repositories**.
3. Add this repository URL: `https://github.com/spritter-org/spritter-ha`
4. Open **Spritter Add-On** from the store and install it.
5. Open the add-on's **Configuration** tab, set your refresh interval and stations, then start the add-on.


## Published Topics

- Per station: `<topic_prefix>/<provider>/<station_id>`
- Cycle summary: `<topic_prefix>/_summary`

Each station topic payload contains `generated_at`, `refresh_interval_minutes`, and `station` (provider, station_id, name, prices).

## Notes

- The old `custom_components` integration has been removed.
- Station fetches run asynchronously with a default max parallelism of 6.
- A failed station fetch does not block other station updates.
