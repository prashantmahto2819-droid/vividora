// Vividora service worker: the app shell works offline; API calls always go to the network.
const SHELL = "vividora-shell-v8";
const FILES = ["/", "/assets/app.css", "/assets/app.js", "/assets/editor.css", "/assets/theme.css", "/assets/fonts/Mukta-Regular.woff", "/assets/fonts/Mukta-Medium.woff", "/assets/fonts/Mukta-SemiBold.woff", "/assets/fonts/Mukta-Bold.woff", "/assets/fonts/TiroDevanagariHindi-Regular.woff", "/assets/editor.js", "/assets/record.js", "/assets/thumbs.js", "/assets/voice.js", "/assets/textfx.js", "/assets/cutout.js", "/manifest.webmanifest", "/icon.svg"];

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
  e.respondWith(
    fetch(e.request).then((r) => {
      if (r.ok && FILES.includes(url.pathname)) caches.open(SHELL).then((c) => c.put(e.request, r.clone()));
      return r;
    }).catch(() => caches.match(e.request).then((r) => r || caches.match("/")))
  );
});
