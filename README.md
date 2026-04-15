# Spritter Home Assistant Add-On

This repository now provides a Home Assistant Add-On (not a HACS custom component).

The add-on:
- fetches fuel prices using the `spritter` core library,
- exposes an internal REST endpoint for price maps,
- includes a basic web UI to manage stations and base settings.

## Install As Add-On Repository

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
2. Open the menu (top-right) and select **Repositories**.
3. Add this repository URL: `https://github.com/spritter-org/spritter-ha`
4. Open **Spritter Add-On** from the store and install it.
5. Start the add-on.

## Add-On UI

Open the add-on via sidebar/ingress. The UI lets you:
- set `refresh_interval_seconds`,
- add/remove stations (`provider`, `station_id`, optional `name`, optional `keys`),
- save the config,
- preview the aggregated price map.

## Internal API

Base URL inside the add-on container: `http://127.0.0.1:8099`

Endpoints:
- `GET /api/v1/config`
- `PUT /api/v1/config`
- `GET /api/v1/price-map`

Example response for `GET /api/v1/price-map`:

```json
{
  "generated_at": "2026-04-15T12:00:00+00:00",
  "refresh_interval_seconds": 300,
  "stations": [
    {
      "provider": "jet",
      "station_id": "2640f98f48",
      "name": "JET 2640f98f48",
      "prices": {
        "diesel": 1.539,
        "super": 1.589
      }
    }
  ]
}
```

## Notes

- The previous `custom_components` integration has been removed.
- This add-on is the single source of configuration and data retrieval.