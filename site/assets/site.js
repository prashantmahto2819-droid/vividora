// Vividora marketing site — tiny helpers, no framework.
const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.12 });
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
const nav = document.querySelector("nav.top"); const burger = document.querySelector(".burger");
if (burger) burger.onclick = () => nav.classList.toggle("open");
const here = location.pathname.split("/").pop() || "index.html";
document.querySelectorAll("nav.top .links a").forEach((a) => { if (a.getAttribute("href") === here) a.classList.add("on"); });
// rotating word in the hero
const w = document.querySelector("[data-rotate]");
if (w) { const words = w.dataset.rotate.split("|"); let i = 0; setInterval(() => { i = (i + 1) % words.length; w.style.opacity = 0; setTimeout(() => { w.textContent = words[i]; w.style.opacity = 1; }, 250); }, 2400); w.style.transition = "opacity .25s"; }
document.querySelectorAll("[data-year]").forEach((e) => (e.textContent = new Date().getFullYear()));
