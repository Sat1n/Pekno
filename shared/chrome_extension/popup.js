// Pekno Cookie Sync - Popup Script

const STORAGE_KEYS = {
  apiUrl: "pekno_api_url",
  pat: "pekno_pat",
  platforms: "pekno_platforms",
};

// Interval options in minutes
const INTERVAL_OPTIONS = [
  { value: 15, label: "15 min" },
  { value: 30, label: "30 min" },
  { value: 60, label: "1 hour" },
  { value: 240, label: "4 hours" },
  { value: 720, label: "12 hours" },
];

// ---------------------------------------------------------------------------
// i18n
// ---------------------------------------------------------------------------

async function loadLocale() {
  const lang = chrome.i18n.getUILanguage();
  const locale = lang.startsWith("zh") ? "zh_CN" : "en";
  try {
    const resp = await fetch(`_locales/${locale}/messages.json`);
    return await resp.json();
  } catch {
    return {};
  }
}

function applyI18n(messages) {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (messages[key]) {
      el.textContent = messages[key].message;
    }
  });
}

// ---------------------------------------------------------------------------
// Storage helpers
// ---------------------------------------------------------------------------

function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      [STORAGE_KEYS.apiUrl, STORAGE_KEYS.pat, STORAGE_KEYS.platforms, "syncModes"],
      resolve
    );
  });
}

function saveConfig(apiUrl, pat) {
  return new Promise((resolve) => {
    chrome.storage.sync.set(
      { [STORAGE_KEYS.apiUrl]: apiUrl, [STORAGE_KEYS.pat]: pat },
      resolve
    );
  });
}

function getSyncModes() {
  return new Promise((resolve) => {
    chrome.storage.sync.get("syncModes", (data) => resolve(data.syncModes || {}));
  });
}

function saveSyncModes(modes) {
  return new Promise((resolve) => {
    chrome.storage.sync.set({ syncModes: modes }, resolve);
  });
}

function getLastSync() {
  return new Promise((resolve) => {
    chrome.storage.local.get("lastSync", (data) => resolve(data.lastSync || {}));
  });
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------

function setStatus(elementId, text, type) {
  const el = document.getElementById(elementId);
  if (el) {
    el.textContent = text;
    el.className = `status-text ${type || ""}`;
  }
}

function setConnectionDot(status) {
  const dot = document.getElementById("connectionDot");
  dot.className = `dot dot-${status}`;
}

function addLog(message, type = "info") {
  const logSection = document.getElementById("logSection");
  const logEl = document.getElementById("syncLog");
  logSection.classList.remove("hidden");

  const entry = document.createElement("div");
  entry.className = `log-entry ${type}`;
  const time = new Date().toLocaleTimeString();
  entry.textContent = `[${time}] ${message}`;
  logEl.appendChild(entry);
  logEl.scrollTop = logEl.scrollHeight;
}

function formatTimestamp(isoString) {
  if (!isoString) return "—";
  const d = new Date(isoString);
  return d.toLocaleString();
}

// ---------------------------------------------------------------------------
// Platform rendering
// ---------------------------------------------------------------------------

async function renderPlatforms() {
  const config = await getConfig();
  const platforms = config[STORAGE_KEYS.platforms] || [];
  const syncModes = await getSyncModes();
  const lastSync = await getLastSync();

  const container = document.getElementById("platformList");
  const section = document.getElementById("platformSection");

  if (platforms.length === 0) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");
  container.innerHTML = "";

  for (const p of platforms) {
    const mode = syncModes[p.platform] || { type: "off", intervalMinutes: 60 };
    const lastSyncTime = lastSync[p.platform];

    const card = document.createElement("div");
    card.className = "platform-card";
    card.innerHTML = `
      <div class="platform-header">
        <span class="platform-label">${escapeHtml(p.label)}</span>
      </div>
      <div class="platform-domains">${escapeHtml(p.domain_patterns.join(", "))}</div>
      <div class="platform-controls">
        <select class="sync-mode" data-platform="${escapeHtml(p.platform)}">
          <option value="off" ${mode.type === "off" ? "selected" : ""}>Off</option>
          <option value="lazy" ${mode.type === "lazy" ? "selected" : ""}>Lazy (on visit)</option>
          <option value="scheduled" ${mode.type === "scheduled" ? "selected" : ""}>Scheduled</option>
        </select>
        <select class="sync-interval" data-platform="${escapeHtml(p.platform)}" ${mode.type !== "scheduled" ? "disabled" : ""}>
          ${INTERVAL_OPTIONS.map(
            (opt) =>
              `<option value="${opt.value}" ${mode.intervalMinutes === opt.value ? "selected" : ""}>${opt.label}</option>`
          ).join("")}
        </select>
        <button class="btn btn-sm btn-secondary sync-now" data-platform="${escapeHtml(p.platform)}" data-patterns='${escapeHtml(JSON.stringify(p.domain_patterns))}'>
          Sync Now
        </button>
      </div>
      <div class="platform-status">
        <span class="last-sync-label">Last sync: ${formatTimestamp(lastSyncTime)}</span>
      </div>
    `;

    container.appendChild(card);
  }

  // Bind events
  container.querySelectorAll(".sync-mode").forEach((select) => {
    select.addEventListener("change", async (e) => {
      const platform = e.target.dataset.platform;
      const intervalSelect = container.querySelector(
        `.sync-interval[data-platform="${platform}"]`
      );
      intervalSelect.disabled = e.target.value !== "scheduled";

      const modes = await getSyncModes();
      modes[platform] = {
        type: e.target.value,
        intervalMinutes: parseInt(intervalSelect.value) || 60,
      };
      await saveSyncModes(modes);
      chrome.runtime.sendMessage({ type: "refreshAlarms" });
    });
  });

  container.querySelectorAll(".sync-interval").forEach((select) => {
    select.addEventListener("change", async (e) => {
      const platform = e.target.dataset.platform;
      const modeSelect = container.querySelector(
        `.sync-mode[data-platform="${platform}"]`
      );
      const modes = await getSyncModes();
      modes[platform] = {
        type: modeSelect.value,
        intervalMinutes: parseInt(e.target.value) || 60,
      };
      await saveSyncModes(modes);
      chrome.runtime.sendMessage({ type: "refreshAlarms" });
    });
  });

  container.querySelectorAll(".sync-now").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const platform = e.target.dataset.platform;
      const patterns = JSON.parse(e.target.dataset.patterns);
      btn.disabled = true;
      btn.textContent = "...";

      addLog(`Syncing ${platform}...`, "info");
      chrome.runtime.sendMessage(
        { type: "syncNow", platform, domainPatterns: patterns },
        async (result) => {
          btn.disabled = false;
          btn.textContent = "Sync Now";

          if (result && result.ok) {
            addLog(`Synced ${platform}: ${result.count} cookies`, "success");
          } else {
            const err = result ? result.error : "no_response";
            addLog(`Failed to sync ${platform}: ${err}`, "error");
          }
          // Refresh last sync display
          await renderPlatforms();
        }
      );
    });
  });
}

// ---------------------------------------------------------------------------
// Config save & test
// ---------------------------------------------------------------------------

document.getElementById("saveConfig").addEventListener("click", async () => {
  const apiUrl = document.getElementById("apiUrl").value.trim();
  const pat = document.getElementById("pat").value.trim();

  if (!apiUrl) {
    setStatus("configStatus", "API URL is required.", "error");
    return;
  }
  if (!pat) {
    setStatus("configStatus", "PAT token is required.", "error");
    return;
  }

  await saveConfig(apiUrl, pat);
  setStatus("configStatus", "Configuration saved.", "ok");

  // Fetch platforms
  setStatus("configStatus", "Fetching platforms...", "info");
  chrome.runtime.sendMessage({ type: "fetchPlatforms" }, async (platforms) => {
    if (platforms && platforms.length > 0) {
      setStatus("configStatus", `Saved. Found ${platforms.length} platform(s).`, "ok");
      await renderPlatforms();
    } else {
      setStatus("configStatus", "Saved. No cookie platforms found.", "error");
    }
  });
});

document.getElementById("testConnection").addEventListener("click", async () => {
  const apiUrl = document.getElementById("apiUrl").value.trim();
  const pat = document.getElementById("pat").value.trim();

  if (!apiUrl || !pat) {
    setStatus("configStatus", "Enter API URL and PAT first.", "error");
    setConnectionDot("red");
    return;
  }

  setStatus("configStatus", "Testing connection...", "info");
  setConnectionDot("yellow");

  const baseUrl = apiUrl.replace(/\/+$/, "");
  try {
    const resp = await fetch(`${baseUrl}/api/user/credentials/cookie-platforms`, {
      headers: { Authorization: `Bearer ${pat}` },
    });

    if (resp.ok) {
      const platforms = await resp.json();
      setStatus("configStatus", `Connected! ${platforms.length} platform(s) available.`, "ok");
      setConnectionDot("green");
    } else if (resp.status === 401 || resp.status === 403) {
      setStatus("configStatus", "Authentication failed. Check your PAT.", "error");
      setConnectionDot("red");
    } else {
      setStatus("configStatus", `Server returned ${resp.status}.`, "error");
      setConnectionDot("red");
    }
  } catch (err) {
    setStatus("configStatus", "Cannot reach server. Check URL.", "error");
    setConnectionDot("red");
  }
});

// Toggle PAT visibility
document.getElementById("togglePat").addEventListener("click", () => {
  const input = document.getElementById("pat");
  input.type = input.type === "password" ? "text" : "password";
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  // Apply i18n
  const messages = await loadLocale();
  applyI18n(messages);

  // Load saved config
  const config = await getConfig();
  if (config[STORAGE_KEYS.apiUrl]) {
    document.getElementById("apiUrl").value = config[STORAGE_KEYS.apiUrl];
  }
  if (config[STORAGE_KEYS.pat]) {
    document.getElementById("pat").value = config[STORAGE_KEYS.pat];
  }

  // If config exists, render platforms
  if (config[STORAGE_KEYS.apiUrl] && config[STORAGE_KEYS.pat]) {
    await renderPlatforms();
  }
}

init();
