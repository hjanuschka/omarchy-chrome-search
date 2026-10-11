const hostName = "com.hjanuschka.omarchy_chrome_search";
let port;
let retryTimer;
chrome.alarms.create("reconnect", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "reconnect") connect();
});

async function handle(request) {
  switch (request.action) {
    case "list": {
      const tabs = await chrome.tabs.query({});
      return tabs.filter(tab => tab.id !== undefined && tab.windowId !== undefined)
        .map(tab => ({
          id: tab.id,
          windowId: tab.windowId,
          title: tab.title || "",
          url: tab.url || "",
          active: !!tab.active,
          lastAccessed: tab.lastAccessed || 0
        }));
    }
    case "activate": {
      const tab = await chrome.tabs.get(request.tabId);
      await chrome.tabs.update(tab.id, { active: true });
      await chrome.windows.update(tab.windowId, { focused: true });
      return { id: tab.id, windowId: tab.windowId };
    }
    case "search":
      await chrome.search.query({ text: request.text, disposition: "NEW_TAB" });
      return true;
    default:
      throw new Error("Unknown action");
  }
}

function connect() {
  if (port) return;
  try {
    const connectedPort = chrome.runtime.connectNative(hostName);
    port = connectedPort;
    connectedPort.onMessage.addListener(async request => {
      let response;
      try {
        response = { id: request.id, result: await handle(request) };
      } catch (error) {
        response = { id: request.id, error: String(error) };
      }
      if (port === connectedPort) connectedPort.postMessage(response);
    });
    connectedPort.onDisconnect.addListener(() => {
      if (chrome.runtime.lastError) console.error("Native host:", chrome.runtime.lastError.message);
      if (port === connectedPort) port = undefined;
      clearTimeout(retryTimer);
      retryTimer = setTimeout(connect, 3000);
    });
  } catch (error) {
    retryTimer = setTimeout(connect, 3000);
  }
}

connect();
