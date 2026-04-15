const state = {
  refresh_interval_seconds: 300,
  stations: [],
};

const els = {
  refreshInput: document.getElementById("refresh-interval"),
  stationForm: document.getElementById("station-form"),
  stationList: document.getElementById("station-list"),
  saveBtn: document.getElementById("save-btn"),
  refreshBtn: document.getElementById("refresh-btn"),
  preview: document.getElementById("price-preview"),
  provider: document.getElementById("provider"),
  stationId: document.getElementById("station-id"),
  stationName: document.getElementById("station-name"),
  keys: document.getElementById("keys"),
};

function renderStations() {
  els.stationList.innerHTML = "";

  if (!state.stations.length) {
    const li = document.createElement("li");
    li.textContent = "No stations configured yet.";
    els.stationList.appendChild(li);
    return;
  }

  state.stations.forEach((station, index) => {
    const li = document.createElement("li");
    li.className = "station-item";

    const details = document.createElement("div");
    details.textContent = `${station.provider} / ${station.station_id}${station.name ? ` (${station.name})` : ""}`;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => {
      state.stations.splice(index, 1);
      renderStations();
    });

    li.appendChild(details);
    li.appendChild(removeBtn);
    els.stationList.appendChild(li);
  });
}

async function loadConfig() {
  const response = await fetch("/api/v1/config");
  const data = await response.json();
  state.refresh_interval_seconds = data.refresh_interval_seconds || 300;
  state.stations = Array.isArray(data.stations) ? data.stations : [];
  els.refreshInput.value = state.refresh_interval_seconds;
  renderStations();
}

async function saveConfig() {
  state.refresh_interval_seconds = Number(els.refreshInput.value || 300);

  const response = await fetch("/api/v1/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state),
  });

  const data = await response.json();
  state.refresh_interval_seconds = data.refresh_interval_seconds;
  state.stations = data.stations;
  renderStations();
}

async function previewPriceMap() {
  els.preview.textContent = "Loading...";
  const response = await fetch("/api/v1/price-map");
  const data = await response.json();
  els.preview.textContent = JSON.stringify(data, null, 2);
}

els.stationForm.addEventListener("submit", (event) => {
  event.preventDefault();

  const provider = els.provider.value.trim();
  const station_id = els.stationId.value.trim();
  if (!provider || !station_id) {
    return;
  }

  const station = {
    provider,
    station_id,
    name: els.stationName.value.trim() || null,
    keys: els.keys.value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  };

  if (!station.keys.length) {
    delete station.keys;
  }

  state.stations.push(station);
  renderStations();
  els.stationForm.reset();
});

els.saveBtn.addEventListener("click", saveConfig);
els.refreshBtn.addEventListener("click", previewPriceMap);

loadConfig().catch((err) => {
  els.preview.textContent = `Failed to load config: ${err}`;
});
