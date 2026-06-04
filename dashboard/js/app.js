let dashboardOptions = {
    default_greenhouse_id: "GH1",
    greenhouses: [],
    sensor_types: [],
    actuator_types: [],
    sensors: [],
    actuators: [],
    device_labels: {},
    actions: []
};

let selectedGreenhouse = "GH1";
let loadedGreenhouse = "GH1";

const PLANT_PLACEHOLDERS = ["basil", "pepper", "cucumber", "strawberry", "spinach", "mint"];

function deviceLabel(device) {
    const type = device.actuator_type || device;
    const rawLabel = dashboardOptions.device_labels[type] || type;
    return displayName(rawLabel);
}

function displayName(name) {
    return String(name)
        .replace(/_/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase());
}

function actuatorOptionList(select, values) {
    select.innerHTML = "";
    values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value.device_id;
        option.textContent = `${value.device_id} (${deviceLabel(value)})`;
        select.appendChild(option);
    });
}

function typeOptionList(select, values) {
    select.innerHTML = "";
    values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = displayName(value);
        select.appendChild(option);
    });
}

function actionOptionList(select, values) {
    select.innerHTML = "";
    values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
    });
}

function greenhouseOptionList(select, greenhouses) {
    select.innerHTML = "";
    greenhouses.forEach((greenhouse) => {
        const option = document.createElement("option");
        option.value = greenhouse.greenhouse_id;
        option.textContent = `${greenhouse.greenhouse_id} (${displayName(greenhouse.plant_type)})`;
        select.appendChild(option);
    });
}

function nextGreenhouseId(greenhouses) {
    let maxNumber = 0;
    greenhouses.forEach((greenhouse) => {
        const match = String(greenhouse.greenhouse_id).match(/^GH(\d+)$/i);
        if (match) {
            maxNumber = Math.max(maxNumber, Number(match[1]));
        }
    });
    return `GH${maxNumber + 1}`;
}

function updateGreenhousePlaceholders() {
    const nextId = nextGreenhouseId(dashboardOptions.greenhouses);
    const plantIndex = dashboardOptions.greenhouses.length % PLANT_PLACEHOLDERS.length;
    document.getElementById("newGreenhouseId").placeholder = nextId;
    document.getElementById("newPlantType").placeholder = PLANT_PLACEHOLDERS[plantIndex];
    document.getElementById("newThingSpeakKey").placeholder = "optional";
}

function updateSelectedGreenhouseLabels() {
    document.getElementById("workspaceTitle").textContent = `${loadedGreenhouse} Current State`;
    document.getElementById("deviceTargetGreenhouse").textContent = loadedGreenhouse;
    const hint = document.getElementById("refreshHint");
    if (selectedGreenhouse === loadedGreenhouse) {
        hint.textContent = `Showing latest loaded state for ${loadedGreenhouse}.`;
    } else {
        hint.textContent = "Please click 'Refresh State' to switch.";
    }
}

function sensorCards(latest) {
    const container = document.getElementById("sensorCards");
    container.innerHTML = "";

    const entries = Object.entries(latest || {}).sort((left, right) => {
        const leftType = left[1].sensor_type || "";
        const rightType = right[1].sensor_type || "";
        const sensorOrder = dashboardOptions.sensor_types || [];
        return sensorOrder.indexOf(leftType) - sensorOrder.indexOf(rightType)
            || left[0].localeCompare(right[0]);
    });
    if (!entries.length) {
        container.innerHTML = `<div class="card"><div class="label">No sensor data</div><div class="value">Waiting</div></div>`;
        return;
    }

    entries.forEach(([deviceId, payload]) => {
        const event = payload.e && payload.e[0] ? payload.e[0] : {};
        const card = document.createElement("div");
        card.className = "card";
        const unit = event.u ? ` (${event.u})` : "";
        card.innerHTML = `
            <div class="label">${displayName(deviceId)}${unit}</div>
            <div class="value">${event.v ?? "-"}</div>
        `;
        container.appendChild(card);
    });
}

function actuatorCards(states) {
    const container = document.getElementById("actuatorCards");
    container.innerHTML = "";

    const order = dashboardOptions.actuators.map((device) => device.device_id);
    const entries = Object.entries(states || {}).sort((left, right) => {
        return order.indexOf(left[0]) - order.indexOf(right[0])
            || left[0].localeCompare(right[0]);
    });
    if (!entries.length) {
        container.innerHTML = `<div class="card"><div class="label">No actuator data</div><div class="value">Waiting</div></div>`;
        return;
    }

    entries.forEach(([deviceId, state]) => {
        const isOn = state.state === "ON";
        const card = document.createElement("div");
        card.className = `card ${isOn ? "on" : ""}`;
        card.innerHTML = `
            <div class="label">${displayName(deviceId)}</div>
            <div class="value">${state.state || "-"}</div>
        `;
        container.appendChild(card);
    });
}

async function loadOptions() {
    const response = await fetch(`/api/options?greenhouse_id=${encodeURIComponent(selectedGreenhouse)}`);
    dashboardOptions = await response.json();
    if (!dashboardOptions.greenhouses.some((greenhouse) => greenhouse.greenhouse_id === selectedGreenhouse)) {
        selectedGreenhouse = dashboardOptions.default_greenhouse_id;
        loadedGreenhouse = selectedGreenhouse;
    }
    greenhouseOptionList(document.getElementById("greenhouse"), dashboardOptions.greenhouses);
    document.getElementById("greenhouse").value = selectedGreenhouse;
    updateSelectedGreenhouseLabels();
    updateGreenhousePlaceholders();
    actuatorOptionList(document.getElementById("device"), dashboardOptions.actuators);
    actionOptionList(document.getElementById("action"), dashboardOptions.actions);
    changeDeviceKind();
}

async function loadSelectedGreenhouse() {
    await loadOptions();
    loadedGreenhouse = selectedGreenhouse;
    await refreshLoadedState();
}

async function refreshLoadedState() {
    const response = await fetch(`/api/state?greenhouse_id=${encodeURIComponent(loadedGreenhouse)}`);
    const data = await response.json();
    document.getElementById("state").textContent = JSON.stringify(data, null, 2);
    sensorCards(data.sensors && data.sensors.latest);
    actuatorCards(data.actuators && data.actuators.states);
    updateSelectedGreenhouseLabels();
}

function changeGreenhouse() {
    selectedGreenhouse = document.getElementById("greenhouse").value;
    updateSelectedGreenhouseLabels();
    document.getElementById("overrideResult").textContent = "No command sent yet.";
    document.getElementById("deviceResult").textContent = `No device added to ${loadedGreenhouse} yet.`;
}

async function sendOverride() {
    const device_id = document.getElementById("device").value;
    const action = document.getElementById("action").value;
    const duration = Number(document.getElementById("duration").value || 5);

    const response = await fetch("/api/override", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            greenhouse_id: selectedGreenhouse,
            device_id,
            action,
            duration
        })
    });
    const data = await response.json();
    if (typeof data.response === "string") {
        try {
            data.response = JSON.parse(data.response);
        } catch (error) {
            // Keep the original string if the response is not JSON.
        }
    }
    document.getElementById("overrideResult").textContent = JSON.stringify(data, null, 2);
    setTimeout(refreshLoadedState, 600);
}

function changeDeviceKind() {
    const kind = document.getElementById("newDeviceKind").value;
    const values = kind === "sensor" ? dashboardOptions.sensor_types : dashboardOptions.actuator_types;
    typeOptionList(document.getElementById("newDeviceType"), values);
}

async function addGreenhouse() {
    const greenhouseInput = document.getElementById("newGreenhouseId");
    const plantInput = document.getElementById("newPlantType");
    const apiKeyInput = document.getElementById("newThingSpeakKey");
    const greenhouseId = greenhouseInput.value.trim() || greenhouseInput.placeholder;
    const plantType = plantInput.value.trim() || plantInput.placeholder || "unknown";
    const apiKey = apiKeyInput.value.trim();
    const body = {
        greenhouse_id: greenhouseId,
        plant_type: plantType
    };
    if (apiKey) {
        body.thingspeak_api_key = apiKey;
    }
    const response = await fetch("/api/greenhouses", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
    });
    const data = await response.json();
    document.getElementById("greenhouseResult").textContent = JSON.stringify(data, null, 2);
    if (greenhouseId) {
        selectedGreenhouse = greenhouseId;
    }
    await loadSelectedGreenhouse();
}

async function addDevice() {
    const kind = document.getElementById("newDeviceKind").value;
    const deviceType = document.getElementById("newDeviceType").value;
    const body = {
        greenhouse_id: loadedGreenhouse,
        type: kind
    };
    if (kind === "sensor") {
        body.sensor_type = deviceType;
    } else {
        body.actuator_type = deviceType;
    }
    const response = await fetch("/api/devices", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
    });
    const data = await response.json();
    document.getElementById("deviceResult").textContent = JSON.stringify(data, null, 2);
    await loadSelectedGreenhouse();
}

async function init() {
    await loadSelectedGreenhouse();
    setInterval(refreshLoadedState, 5000);
}

init();
