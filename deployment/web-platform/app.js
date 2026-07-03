const result = document.getElementById("result");
const resultHint = document.getElementById("resultHint");
const input = document.getElementById("commandInput");
const button = document.getElementById("runButton");
const apiState = document.getElementById("apiState");
const authState = document.getElementById("authState");
const promptChips = Array.from(document.querySelectorAll(".prompt-chip"));

const API_BASE = window.AIOS_API_BASE || localStorage.getItem("AIOS_API_BASE") || "";

function setResult(text, hint) {
  result.textContent = text;
  if (hint) resultHint.textContent = hint;
}

function formatPayload(data) {
  if (typeof data === "string") return data;
  return JSON.stringify(data, null, 2);
}

async function health() {
  if (!API_BASE) {
    apiState.textContent = "Backend not configured";
    authState.textContent = "Private Beta";
    setResult(
      "Private beta shell ready.\n\nSet AIOS_API_BASE after the hosted backend is deployed.",
      "Offline shell"
    );
    return;
  }

  apiState.textContent = "Checking backend";
  resultHint.textContent = "Runtime probe";

  try {
    const res = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    apiState.textContent = data.status ? `Backend ${data.status}` : "Backend connected";
    authState.textContent = "Connected Runtime";
    setResult(formatPayload(data), "Health response");
  } catch (error) {
    apiState.textContent = "Backend unreachable";
    authState.textContent = "Private Beta";
    setResult(`Backend not reachable: ${error.message}`, "Connection failed");
  }
}

async function runCommand() {
  const request = input.value.trim();
  if (!request) return;

  button.disabled = true;
  button.textContent = "Running";
  setResult("AIOS is processing the request...", "Command running");

  if (!API_BASE) {
    setResult(
      `Command captured for private beta:\n${request}\n\nBackend URL is not configured yet.`,
      "Backend missing"
    );
    button.disabled = false;
    button.textContent = "Run Command";
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request }),
    });

    const data = await res.json();
    setResult(formatPayload(data), res.ok ? "Command complete" : "Command returned error");
  } catch (error) {
    setResult(`Command failed: ${error.message}`, "Request failed");
  } finally {
    button.disabled = false;
    button.textContent = "Run Command";
  }
}

button.addEventListener("click", runCommand);

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter") runCommand();
});

promptChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    input.value = chip.dataset.prompt || "";
    input.focus();
  });
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

health();
