# Spritter Home Assistant Integration

Minimal Home Assistant integration for fuel prices, powered by the `spritter` core library.

## Installation

### HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=spritter-org&repository=spritter-ha&category=integration)

1. Open HACS > Integrations > Menu > **Custom repositories**.
2. Add `https://github.com/spritter-org/spritter-ha` and choose type **Integration**
3. Install **Spritter** from HACS
4. Restart Home Assistant

### Manual Installation

1. Clone this repository.
2. Copy the `custom_components/spritter` folder into your `homeassistant/custom_components/` directory.
3. Restart Home Assistant

## Development

Install development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Configuration

### UI setup (recommended)

1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for **Spritter**.
3. Enter the base scan interval and at least one `provider` / `station_id` pair.
4. After setup, make sure to **Configure** the integration in the UI.

### YAML setup (legacy)

Add the platform in `configuration.yaml`:

```yaml
sensor:
  - platform: spritter
    scan_interval:
      minutes: 5
    sources:
      - provider: jet
        station_id: "2640f98f48"
        name: "JET Example"
      - provider: omv
        station_id: "AT123456"
        name: "OMV Example"
        keys:
          - diesel
          - super
```

### Source options

- `provider` (required): provider id, e.g. `jet`, `omv`, `avanti`
- `station_id` (required): station identifier for the provider
- `name` (optional): Home Assistant entity name
- `user_agent` (optional): custom user agent sent to provider
- `keys` (optional): filter returned fuel types

## Entities

Creates one device per configured source (petrol station).

- Device: station (`provider` + `station_id`)
- Entities: one numeric sensor per fuel type (for example `diesel`, `super`)
- Sensor state: current fuel price as number (unit `€/L`)
- Sensor attributes:
  - `provider`
  - `station_id`
  - `fuel_type`
  - `keys` (if configured)

Because fuel prices are exposed as numeric sensor states, they can be used in Home Assistant long-term statistics and statistical history views.
