/* Riksi en el navegador: cámara -> EfficientNet-Lite0 int8 -> una determinación.
 *
 * Todo pasa aquí dentro. No hay servidor al que mandar la foto ni al que
 * preguntarle nada: el modelo son 3,8 MB que se descargan una vez.
 */

// Por debajo de esto no se afirma nada: la ficha sale con «cf.», que es lo que
// escribe un taxónomo cuando la determinación es probable pero no firme. En el
// campo, una identificación equivocada dicha con seguridad hace más daño que
// un "no lo sé".
// ponytail: umbral fijo elegido a ojo; medir la curva de confianza sobre el
// conjunto de validación y ajustarlo cuando haya datos de uso real.
const UMBRAL = 0.40;

const $ = (s) => document.querySelector(s);
const video = $("#camara"), foto = $("#foto"), mira = $("#mira"), aviso = $("#aviso");
const meta = $("#meta"), ficha = $("#ficha");
const boton = $("#identificar"), volver = $("#volver");

const lienzo = document.createElement("canvas");
const cx = lienzo.getContext("2d", { willReadFrequently: true });
// Dos auxiliares que se alternan: al reducir por pasos nunca se puede leer y
// escribir el mismo canvas (asignarle width lo borra).
const bufer = [document.createElement("canvas"), document.createElement("canvas")];

let sesion, clases, comunes = {}, pre;

/** Estado en la barra. Con punto verde solo cuando de verdad puede trabajar. */
function estado(texto, listo = true) {
  meta.innerHTML = (listo ? '<i class="punto"></i>' : "") + texto;
}

async function arrancar() {
  // Un solo hilo a propósito: los hilos de WASM piden aislamiento de origen
  // (COOP/COEP) que GitHub Pages no da, y sin él ORT los desactiva igual.
  ort.env.wasm.numThreads = 1;
  // URL absoluta, no "vendor/": ORT carga el .mjs con import() dinámico y un
  // specifier relativo sin "./" no es válido como módulo — falla con
  // "Failed to resolve module specifier".
  ort.env.wasm.wasmPaths = new URL("vendor/", location.href).href;

  pre = await (await fetch("modelo/preprocesado.json")).json();
  clases = await (await fetch("modelo/clases.json")).json();
  comunes = await fetch("modelo/comunes.json").then((r) => r.ok ? r.json() : {}).catch(() => ({}));
  // El peso sale de la última medición, no escrito a mano en el HTML: al
  // reentrenar cambia solo.
  fetch("modelo/metricas.json").then((r) => r.ok ? r.json() : null).then((m) => {
    if (m) $("#peso").textContent = m.int8.mb.toFixed(1).replace(".", ",") + " MB";
  }).catch(() => {});
  lienzo.width = lienzo.height = pre.tam;

  sesion = await ort.InferenceSession.create("modelo/riksi-int8.onnx", {
    executionProviders: ["wasm"],
  });

  aviso.hidden = true;
  boton.disabled = false;
  $("#n-especies").textContent = clases.length;
  estado("listo, funciona sin conexión");
  // La guía se enseña hasta la primera determinación: quien llega desde la
  // portada no tiene por qué adivinar que hay que encuadrar dentro del marco.
  if (!localStorage.getItem("riksi-guia-vista")) $("#guia").hidden = false;
  abrirCamara();
  if (new URLSearchParams(location.search).has("test")) autocomprobar();
}

async function abrirCamara() {
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } }, audio: false,
    });
    video.hidden = false; foto.hidden = true; mira.hidden = false; aviso.hidden = true;
    volver.textContent = "Cámara";
  } catch (err) {
    // Sin cámara (PC, permiso denegado, http sin TLS) queda la vía de subir foto.
    video.hidden = true; mira.hidden = true; aviso.hidden = false;
    aviso.textContent = "Aquí no hay cámara. Sube una foto y funciona igual.";
  }
}

/** Réplica de lo que hizo torchvision al entrenar.
 *
 * Resize(256) + CenterCrop(224) equivale a quedarse con el 87,5% central del
 * lado corto y escalarlo a 224. Si esto no coincide con el entrenamiento el
 * modelo no falla: acierta menos, y se le echa la culpa al modelo.
 */
function aTensor(fuente, ancho, alto) {
  const tam = pre.tam;
  let sw = Math.min(ancho, alto) * (tam / pre.resize);
  let sh = sw, sx = (ancho - sw) / 2, sy = (alto - sh) / 2, origen = fuente;

  // Por mitades hasta acercarse al tamaño final: el canvas no promedia bien
  // cuando la reducción es grande de golpe, y el bilineal de PIL sí (su
  // soporte se adapta a la escala). Sin esto la misma foto da varios puntos
  // de confianza menos que en Python.
  for (let i = 0; sw > tam * 2; i++) {
    const m = Math.max(tam, Math.round(sw / 2));
    const c = bufer[i % 2];
    c.width = c.height = m;
    const g = c.getContext("2d");
    g.imageSmoothingQuality = "high";
    g.drawImage(origen, sx, sy, sw, sh, 0, 0, m, m);
    origen = c; sx = sy = 0; sw = sh = m;
  }

  cx.imageSmoothingQuality = "high";
  cx.drawImage(origen, sx, sy, sw, sh, 0, 0, tam, tam);

  const px = cx.getImageData(0, 0, tam, tam).data;
  const plano = tam * tam;
  const datos = new Float32Array(3 * plano);
  for (let i = 0, p = 0; p < plano; i += 4, p++) {
    datos[p]             = (px[i]     / 255 - pre.media[0]) / pre.desv[0];
    datos[plano + p]     = (px[i + 1] / 255 - pre.media[1]) / pre.desv[1];
    datos[2 * plano + p] = (px[i + 2] / 255 - pre.media[2]) / pre.desv[2];
  }
  return new ort.Tensor("float32", datos, [1, 3, tam, tam]);
}

/** Deja quieta la imagen que se acaba de analizar.
 *
 * Con el vídeo en marcha, la ficha habla de un instante que ya pasó: el ave se
 * fue y en pantalla hay una rama, así que parece que el modelo se equivocó.
 * Una cámara de verdad tampoco te devuelve el visor, te devuelve la foto.
 */
function congelar(ancho, alto) {
  const c = bufer[0];
  c.width = ancho; c.height = alto;
  c.getContext("2d").drawImage(video, 0, 0);
  foto.src = c.toDataURL("image/jpeg", 0.9);
  foto.hidden = false; video.hidden = true;
  volver.textContent = "Volver a la cámara";
}

function probabilidades(logits) {
  const max = Math.max(...logits);
  const exp = logits.map((v) => Math.exp(v - max));   // -max: si no, desborda
  const suma = exp.reduce((a, b) => a + b, 0);
  return exp.map((v) => v / suma);
}

async function identificar() {
  const fuente = video.hidden ? foto : video;
  const ancho = fuente.videoWidth || fuente.naturalWidth;
  const alto = fuente.videoHeight || fuente.naturalHeight;
  if (!ancho) { estado("todavía no hay imagen", false); return; }

  boton.disabled = true;
  estado("mirando la imagen", false);
  const t0 = performance.now();
  const tensor = aTensor(fuente, ancho, alto);
  if (fuente === video) congelar(ancho, alto);
  const salida = await sesion.run({ [sesion.inputNames[0]]: tensor });
  const probs = probabilidades(Array.from(salida[sesion.outputNames[0]].data));
  const ms = Math.round(performance.now() - t0);
  boton.disabled = false;

  const top = probs.map((p, i) => [p, i]).sort((a, b) => b[0] - a[0]).slice(0, 3);
  pintar(top, ms);
  return top;
}

const cientifico = (i) => clases[i].replace(/_/g, " ");
const comun = (i) => comunes[clases[i]] || "";

/** Barra de certeza con la línea del umbral encima: se ve dónde cae cada
 *  candidata respecto al corte a partir del cual sí se afirma. */
const escala = (p) => `<div class="escala" role="img" aria-label="${(p * 100).toFixed(1)} por ciento">
  <i style="width:${(p * 100).toFixed(1)}%"></i><u style="left:${UMBRAL * 100}%"></u></div>`;

function pintar(top, ms) {
  const [p, i] = top[0];
  const dudoso = p < UMBRAL;
  const hora = new Date().toLocaleTimeString("es-EC", { hour: "2-digit", minute: "2-digit" });

  ficha.innerHTML = `
    <div class="encabezado"><span>Determinación</span><span>${hora}</span></div>

    <div class="principal">
      <div class="comun">${dudoso ? '<span class="cf">cf.</span>' : ""}${
        comun(i) || `<span class="cientifico">${cientifico(i)}</span>`}</div>
      ${comun(i) ? `<span class="cientifico">${cientifico(i)}</span>` : ""}
      ${escala(p)}
      <div class="fila" style="padding-top:6px">
        <span class="nombre" style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--tinta-2)">
          confianza</span>
        <span class="pct">${(p * 100).toFixed(1)}%</span>
      </div>
      ${dudoso ? `<p class="nota"><b>cf.</b> es «parecido a». La confianza no llega
        al ${(UMBRAL * 100).toFixed(0)}% y solo conozco ${clases.length} especies:
        puede no ser ninguna de estas.</p>` : ""}
    </div>

    <div class="alternativas">
      <p>Otras candidatas</p>
      ${top.slice(1).map(([q, j]) => `
        <div class="fila">
          <div class="nombre">
            ${comun(j) ? `<span>${comun(j)}</span>` : ""}
            <span class="cientifico">${cientifico(j)}</span>
            ${escala(q)}
          </div>
          <span class="pct">${(q * 100).toFixed(1)}%</span>
        </div>`).join("")}
    </div>`;

  ficha.classList.remove("nuevo");
  void ficha.offsetWidth;              // reinicia la animación en cada disparo
  ficha.classList.add("nuevo");
  cerrarGuia();
  $("#ms").textContent = ms + " ms";
  estado("listo, funciona sin conexión");
}

$("#archivo").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (!f) return;
  foto.src = URL.createObjectURL(f);
  foto.hidden = false; video.hidden = true; mira.hidden = false; aviso.hidden = true;
  if (video.srcObject) video.srcObject.getTracks().forEach((t) => t.stop());
  foto.onload = () => identificar();
});

boton.addEventListener("click", () => identificar());
volver.addEventListener("click", abrirCamara);

function cerrarGuia() {
  $("#guia").hidden = true;
  localStorage.setItem("riksi-guia-vista", "1");
}
$("#cerrar-guia").addEventListener("click", cerrarGuia);

/** Comprobación de que el preprocesado del navegador coincide con el de Python.
 *
 * Es el único fallo del proyecto que no da error: si el resize o la
 * normalización difieren, el modelo responde igual pero peor. `comprobar.py`
 * deja la imagen y el resultado esperado.
 */
async function autocomprobar() {
  const esperado = await fetch("prueba/esperado.json").then((r) => r.json());
  foto.src = "prueba/" + esperado.archivo;
  foto.hidden = false; video.hidden = true; mira.hidden = false; aviso.hidden = true;
  await new Promise((ok) => (foto.onload = ok));
  const top = await identificar();
  const igual = clases[top[0][1]] === esperado.clase;
  const desvio = Math.abs(top[0][0] - esperado.prob);
  meta.textContent = igual && desvio < (esperado.tolerancia ?? 0.05)
    ? `autocomprobación ok · desvío ${(desvio * 100).toFixed(1)} pts`
    : `autocomprobación falla · ${clases[top[0][1]]} ${top[0][0].toFixed(3)} vs python ${esperado.prob.toFixed(3)}`;
}

// El punto del proyecto es funcionar sin señal: cachear todo en la primera visita.
if ("serviceWorker" in navigator && location.protocol !== "file:") {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

arrancar().catch((err) => {
  aviso.hidden = false;
  aviso.textContent = "No se pudo cargar el modelo: " + err.message;
});
