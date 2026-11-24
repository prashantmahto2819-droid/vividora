// Vividora service worker: the app shell works offline; API calls always go to the network.
// VERSION is the one number to raise with every release (index.html carries the same ?v= — tests/test_webshell.py checks it).
// Every request for our own code (/assets/*.js, *.css) is sent with ?v=VERSION and past the HTTP cache, so an old copy kept
// by the phone's browser or by the CDN in front of the server can never be shown after an update.
const VERSION = 74;
const SHELL = "vividora-shell-v" + VERSION;
const FILES = ["/", "/assets/app.css", "/assets/app.js", "/assets/learn.js", "/assets/editor.css", "/assets/theme.css", "/assets/fonts/Mukta-Regular.woff", "/assets/fonts/Mukta-Medium.woff", "/assets/fonts/Mukta-SemiBold.woff", "/assets/fonts/Mukta-Bold.woff", "/assets/fonts/TiroDevanagariHindi-Regular.woff", "/assets/editor.js", "/assets/pro.js", "/assets/mix.js", "/assets/lut.js", "/assets/record.js", "/assets/thumbs.js", "/assets/voice.js", "/assets/chars.js", "/assets/scenes.js", "/assets/tools.js", "/assets/models3d.js", "/assets/chars3d.js", "/assets/chars3d-ui.js", "/assets/scenes3d.js", "/assets/three.module.min.js", "/assets/textfx.js", "/assets/cutout.js", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  const code = url.origin === self.location.origin && url.pathname.startsWith("/assets/") && /\.(js|css)$/.test(url.pathname);
  let req = e.request;
  if (code) { const u = new URL(url); u.searchParams.set("v", VERSION); req = new Request(u, { cache: "no-store", credentials: "same-origin" }); }
  e.respondWith(
    fetch(req).then((r) => {
      if (r.ok && !r.redirected && FILES.includes(url.pathname)) caches.open(SHELL).then((c) => c.put(e.request, r.clone()));
      return r;
    }).catch(() => caches.match(e.request).then((r) => r || caches.match("/")))
  );
});
