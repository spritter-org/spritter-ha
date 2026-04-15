# Spritter Home Assistant Add-On

This repository provides a Home Assistant Add-On.

## Install As Add-On Repository

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
2. Open the menu (top-right) and select **Repositories**.
3. Add this repository URL: `https://github.com/spritter-org/spritter-ha`
4. Open **Spritter Add-On** from the store and install it.
5. Start the add-on.

## Internal API

Base URL inside the add-on container: `http://127.0.0.1:8099`

Endpoints:
- `GET /prices/?provider={provider}&id={id}`

Example response for `GET /prices/?provider=jet&id=2640f98f48`:

```json
{
  "generated_at": "2026-04-15T12:00:00+00:00",
  "refresh_interval_seconds": 300,
  "station": {
    "provider": "jet",
    "station_id": "2640f98f48",
    "name": "JET 2640f98f48",
    "prices": {
      "diesel": 1.539,
      "super": 1.589
    }
  }
}
```

## Notes

- The previous `custom_components` integration has been removed.
- The `spritter_config.json` file is the single source of configuration.