// Pekno Cookie Sync - Background Service Worker
// Handles scheduled and lazy cookie synchronization.

const ALARM_PREFIX = "pekno-sync-";
const STORAGE_KEYS = {
  apiUrl: "pekno_api_url",
  pat: "pekno_pat",
  platforms: "pekno_platforms",
};

// ---------------------------------------------------------------------------
// Cookie sync logic
// ---------------------------------------------------------------------------

async function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      [STORAGE_KEYS.apiUrl, STORAGE_KEYS.pat, STORAGE_KEYS.platforms],
      (result) => resolve(result)
    );
  });
}

async function getCookiesForDomains(domainPatterns) {
  const allCookies = [];
  for (const domain of domainPatterns) {
    const cookies = await chrome.cookies.getAll({ domain });
    allCookies.push(...cookies);
  }
  // Deduplicate by name+domain
  const seen = new Set();
  const unique = [];
  for (const c of allCookies) {
    const key = `${c.domain}|${c.name}`;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(c);
    }
  }
  return unique;
}

function buildCookieString(cookies) {
  return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
}

async function syncPlatform(platform, domainPatterns) {
  const config = await getConfig();
  const apiUrl = config[STORAGE_KEYS.apiUrl];
  const pat = config[STORAGE_KEYS.pat];

  if (!apiUrl || !pat) {
    console.warn("[Pekno] Missing API URL or PAT, skipping sync.");
    return { ok: false, error: "not_configured" };
  }

  const cookies = await getCookiesForDomains(domainPatterns);
  if (cookies.length === 0) {
    console.warn(`[Pekno] No cookies found for ${platform}.`);
    return { ok: false, error: "no_cookies" };
  }

  const cookieString = buildCookieString(cookies);
  const baseUrl = apiUrl.replace(/\/+$/, "");

  try {
    const resp = await fetch(`${baseUrl}/api/user/credentials/cookie`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${pat}`,
      },
      body: JSON.stringify({
        platform: platform,
        cookie_value: cookieString,
      }),
    });

    if (!resp.ok) {
      const text = await resp.text();
      console.error(`[Pekno] Sync failed for ${platform}: ${resp.status} ${text}`);
      return { ok: false, error: `http_${resp.status}` };
    }

    const now = new Date().toISOString();
    await updateLastSync(platform, now);
    console.log(`[Pekno] Synced ${platform} at ${now} (${cookies.length} cookies)`);
    return { ok: true, count: cookies.length, timestamp: now };
  } catch (err) {
    console.error(`[Pekno] Network error syncing ${platform}:`, err);
    return { ok: false, error: "network" };
  }
}

async function updateLastSync(platform, timestamp) {
  return new Promise((resolve) => {
    chrome.storage.local.get("lastSync", (data) => {
      const lastSync = data.lastSync || {};
      lastSync[platform] = timestamp;
      chrome.storage.local.set({ lastSync }, resolve);
    });
  });
}

// ---------------------------------------------------------------------------
// Platform config fetching
// ---------------------------------------------------------------------------

async function fetchPlatforms() {
  const config = await getConfig();
  const apiUrl = config[STORAGE_KEYS.apiUrl];
  if (!apiUrl) return [];

  const baseUrl = apiUrl.replace(/\/+$/, "");
  try {
    const resp = await fetch(`${baseUrl}/api/user/credentials/cookie-platforms`);
    if (!resp.ok) return [];
    const platforms = await resp.json();
    chrome.storage.sync.set({ [STORAGE_KEYS.platforms]: platforms });
    return platforms;
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Alarm management (scheduled mode)
// ---------------------------------------------------------------------------

function getAlarmName(platform) {
  return `${ALARM_PREFIX}${platform}`;
}

async function setupAlarms() {
  // Clear existing alarms
  const existing = await chrome.alarms.getAll();
  for (const alarm of existing) {
    if (alarm.name.startsWith(ALARM_PREFIX)) {
      await chrome.alarms.clear(alarm.name);
    }
  }

  const config = await getConfig();
  const platformConfigs = config[STORAGE_KEYS.platforms] || [];
  const syncModes = await getSyncModes();

  for (const p of platformConfigs) {
    const mode = syncModes[p.platform];
    if (mode && mode.type === "scheduled") {
      const interval = mode.intervalMinutes || 60;
      chrome.alarms.create(getAlarmName(p.platform), {
        periodInMinutes: interval,
      });
      console.log(`[Pekno] Alarm set for ${p.platform} every ${interval} min`);
    }
  }
}

async function getSyncModes() {
  return new Promise((resolve) => {
    chrome.storage.sync.get("syncModes", (data) => resolve(data.syncModes || {}));
  });
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

// Alarm fires → sync that platform
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (!alarm.name.startsWith(ALARM_PREFIX)) return;
  const platform = alarm.name.slice(ALARM_PREFIX.length);
  const config = await getConfig();
  const platformConfigs = config[STORAGE_KEYS.platforms] || [];
  const target = platformConfigs.find((p) => p.platform === platform);
  if (target) {
    await syncPlatform(platform, target.domain_patterns);
  }
});

// Page navigation → lazy sync
chrome.webNavigation.onCompleted.addListener(async (details) => {
  // Only top-level frames
  if (details.frameId !== 0) return;

  const config = await getConfig();
  const platformConfigs = config[STORAGE_KEYS.platforms] || [];
  const syncModes = await getSyncModes();
  const url = new URL(details.url);

  for (const p of platformConfigs) {
    const mode = syncModes[p.platform];
    if (!mode || mode.type !== "lazy") continue;

    const matches = p.domain_patterns.some((pattern) => {
      const domain = pattern.startsWith(".") ? pattern : `.${pattern}`;
      return url.hostname === domain.slice(1) || url.hostname.endsWith(domain);
    });

    if (matches) {
      console.log(`[Pekno] Lazy sync triggered for ${p.platform} on ${url.hostname}`);
      await syncPlatform(p.platform, p.domain_patterns);
    }
  }
});

// Message handler from popup
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "syncNow") {
    const { platform, domainPatterns } = msg;
    syncPlatform(platform, domainPatterns).then(sendResponse);
    return true; // Keep channel open for async response
  }
  if (msg.type === "fetchPlatforms") {
    fetchPlatforms().then(sendResponse);
    return true;
  }
  if (msg.type === "refreshAlarms") {
    setupAlarms().then(() => sendResponse({ ok: true }));
    return true;
  }
});

// On install, fetch platforms
chrome.runtime.onInstalled.addListener(async () => {
  await fetchPlatforms();
});
