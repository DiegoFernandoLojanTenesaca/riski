/* Funcionar sin señal es el punto del proyecto, así que todo se cachea. Pero
 * cache-first para TODO tiene un precio que se paga en cada corrección: un
 * `app.js` arreglado no llega nunca y el error que ya resolviste sigue en
 * pantalla.
 *
 * Reparto según el peso: lo grande e inmutable (modelo, wasm, fotos) va
 * cache-first —es lo que de verdad hace falta tener guardado—; el código y los
 * JSON, que son 60 KB, van network-first con la copia local de respaldo. Sin
 * red se comportan igual que antes; con red siempre se ve lo último.
 */
const VERSION = "riksi-v6";
const ARCHIVOS = [
  "./", "index.html", "app.html", "estilo.css", "app.js", "icono.svg",
  "vendor/ort.wasm.min.js", "vendor/ort-wasm-simd-threaded.mjs", "vendor/ort-wasm-simd-threaded.wasm",
  "modelo/riksi-int8.onnx", "modelo/clases.json", "modelo/preprocesado.json", "modelo/metricas.json", "modelo/comunes.json", "muestras/muestras.json",
];
const PESADO = /\.(onnx|wasm|jpg|jpeg|png|svg|woff2?)$/i;

self.addEventListener("install", (e) => {
  // add() individual y no addAll(): addAll falla entero si un archivo no está,
  // y alguno es opcional (comunes.json, las muestras de la portada).
  e.waitUntil(caches.open(VERSION)
    .then((c) => Promise.all(ARCHIVOS.map((a) => c.add(a).catch(() => {}))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function guardar(req, res) {
  if (res.ok) (await caches.open(VERSION)).put(req, res.clone());
  return res;
}

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const pesado = PESADO.test(new URL(e.request.url).pathname);
  e.respondWith(
    pesado
      ? caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => guardar(e.request, r)))
      : fetch(e.request).then((r) => guardar(e.request, r))
          .catch(() => caches.match(e.request).then((hit) => hit || Promise.reject(new Error("sin red y sin copia"))))
  );
});
