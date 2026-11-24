// Vividora for Windows: a window onto your Vividora site (the site itself does all the work; login happens there).
// Camera / microphone are allowed for the site only; links to other sites open in the normal browser.
const { app, BrowserWindow, shell, session, Menu } = require("electron");
const path = require("path");
const SITE = (process.env.VIVIDORA_URL || require("./config.json").url).replace(/\/+$/, "");
const HOST = new URL(SITE).host;

function create() {
  const win = new BrowserWindow({ width: 1440, height: 900, minWidth: 380, minHeight: 600, backgroundColor: "#141A24", title: "Vividora",
    icon: path.join(__dirname, "icon.png"), autoHideMenuBar: true, webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true } });
  Menu.setApplicationMenu(null);
  const mine = (u) => { try { return new URL(u).host === HOST; } catch { return false; } };
  session.defaultSession.setPermissionRequestHandler((wc, permission, cb, details) => {
    cb(mine(details.requestingUrl || wc.getURL()) && ["media", "fullscreen", "clipboard-sanitized-write", "notifications"].includes(permission)); });
  win.webContents.setWindowOpenHandler(({ url }) => { if (mine(url)) return { action: "allow" }; shell.openExternal(url); return { action: "deny" }; });
  win.webContents.on("will-navigate", (e, url) => { if (!mine(url)) { e.preventDefault(); shell.openExternal(url); } });
  win.webContents.on("did-fail-load", (e, code, desc, url, isMain) => { if (!isMain) return;
    win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(`<body style="font-family:sans-serif;background:#141A24;color:#eee;padding:3rem"><h2>Vividora से संपर्क नहीं हो पाया</h2><p>${SITE}</p><p>Internet जाँचें, फिर <a style="color:#F2B33D" href="${SITE}">दोबारा कोशिश करें</a>.</p></body>`)); });
  win.loadURL(SITE + "/");
}
const lock = app.requestSingleInstanceLock();
if (!lock) app.quit();
else {
  app.on("second-instance", () => { const w = BrowserWindow.getAllWindows()[0]; if (w) { if (w.isMinimized()) w.restore(); w.focus(); } });
  app.whenReady().then(create);
  app.on("window-all-closed", () => app.quit());
}
