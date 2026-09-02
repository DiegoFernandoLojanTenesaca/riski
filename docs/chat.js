/* El chat de Yachaq, como burbuja flotante.
 *
 * **Esto es lo contrario del resto de la página, y hay que decirlo.** Riksi
 * identifica dentro del navegador y funciona sin señal; el chat habla con un
 * servidor y sin red no hay chat. Por eso el widget se apaga solo cuando no hay
 * conexión en vez de dejar un botón que no responde: prometer sin conexión y
 * fallar al pulsar es peor que no ofrecerlo.
 *
 * La respuesta enseña qué herramientas usó el agente. No es depuración: es la
 * diferencia entre algo que consultó los registros de GBIF y algo que se lo
 * inventó, y quien lee tiene derecho a distinguirlas.
 */

const YACHAQ = window.YACHAQ_API || "";   // lo fija index.html; vacío = apagado

const chat = {
  abierto: false,
  conversacion: null,
  esperando: false,
};

const nodo = (etiqueta, clase, texto) => {
  const n = document.createElement(etiqueta);
  if (clase) n.className = clase;
  if (texto) n.textContent = texto;
  return n;
};

/* Marcado mínimo: negrita, cursiva y saltos. El agente responde con markdown y
 * pintarlo crudo se lee mal, pero traerse una librería entera para tres reglas
 * sería pagar 40 KB por esto. `textContent` primero, así que nada de lo que
 * devuelva el servidor se interpreta como HTML. */
function conFormato(texto) {
  const p = nodo("div", "yq-texto");
  p.textContent = texto || "";
  p.innerHTML = p.innerHTML
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\n/g, "<br>");
  return p;
}

function burbuja(quien, texto, herramientas) {
  const caja = nodo("div", `yq-msj yq-${quien}`);
  caja.appendChild(conFormato(texto));

  if (herramientas && herramientas.length) {
    const vistas = [...new Set(herramientas.map((h) => h.herramienta))];
    const pie = nodo("div", "yq-usos");
    pie.appendChild(nodo("span", "yq-usos-t", "consultó"));
    vistas.forEach((h) => pie.appendChild(nodo("code", "yq-uso", h)));
    caja.appendChild(pie);
  }
  return caja;
}

function pintar(nodoMsj) {
  const hilo = document.getElementById("yq-hilo");
  hilo.appendChild(nodoMsj);
  hilo.scrollTop = hilo.scrollHeight;
}

async function enviar(texto) {
  if (!texto.trim() || chat.esperando) return;
  chat.esperando = true;
  pintar(burbuja("yo", texto));

  const pensando = nodo("div", "yq-msj yq-el yq-pensando");
  pensando.innerHTML = "<span></span><span></span><span></span>";
  pintar(pensando);

  try {
    const r = await fetch(`${YACHAQ}/preguntar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: texto, conversacion: chat.conversacion }),
    });
    if (!r.ok) throw new Error(`el servidor respondió ${r.status}`);
    const d = await r.json();
    chat.conversacion = d.conversacion || chat.conversacion;
    pensando.remove();
    pintar(burbuja("el", d.respuesta, d.herramientas));
  } catch (e) {
    pensando.remove();
    // El motivo, no un «algo salió mal»: si el servidor está dormido o sin
    // cuota, quien lee merece saber que no es culpa suya ni de su conexión.
    pintar(burbuja("el", navigator.onLine
      ? `No pude preguntar: ${e.message}. El identificador de la cámara sigue funcionando, que ese va dentro del navegador.`
      : "Sin conexión. El chat necesita red; el identificador de la cámara no."));
  } finally {
    chat.esperando = false;
  }
}

function montar() {
  if (!YACHAQ) return;      // sin servidor configurado, no se pinta nada

  const raiz = nodo("div", "yq");
  raiz.innerHTML = `
    <button class="yq-boton" aria-label="Preguntar a Yachaq" aria-expanded="false">
      <svg viewBox="0 0 64 64" width="26" height="26" aria-hidden="true">
        <path d="M6 32C17 14 47 14 58 32 47 50 17 50 6 32Z" fill="none"
              stroke="currentColor" stroke-width="3.5" stroke-linejoin="round"/>
        <circle cx="32" cy="32" r="7.5" fill="currentColor"/>
      </svg>
    </button>
    <section class="yq-panel" hidden aria-label="Chat con Yachaq">
      <header class="yq-cab">
        <div>
          <strong>Yachaq</strong>
          <span class="yq-sub">pregunta sobre las 100 especies</span>
        </div>
        <button class="yq-cerrar" aria-label="Cerrar">&times;</button>
      </header>
      <div id="yq-hilo" class="yq-hilo"></div>
      <div class="yq-sugerencias">
        <button>¿por qué el piquero tiene los pies azules?</button>
        <button>¿dónde puedo ver colibríes cerca de Quito?</button>
        <button>¿qué come el hoatzin?</button>
      </div>
      <form class="yq-pie">
        <input type="text" placeholder="Escribe tu pregunta…" autocomplete="off"
               aria-label="Tu pregunta">
        <button type="submit" aria-label="Enviar">→</button>
      </form>
    </section>`;
  document.body.appendChild(raiz);

  const boton = raiz.querySelector(".yq-boton");
  const panel = raiz.querySelector(".yq-panel");
  const campo = raiz.querySelector(".yq-pie input");

  const alternar = (abrir) => {
    chat.abierto = abrir;
    panel.hidden = !abrir;
    boton.setAttribute("aria-expanded", String(abrir));
    raiz.classList.toggle("yq-activo", abrir);
    if (abrir) {
      campo.focus();
      if (!document.getElementById("yq-hilo").children.length) {
        pintar(burbuja("el", "Pregúntame por cualquiera de las 100 especies: qué come, "
          + "dónde vive, por qué es de ese color. Consulto los registros de GBIF y las "
          + "fichas, y si no tengo el dato te lo digo."));
      }
    }
  };

  boton.addEventListener("click", () => alternar(!chat.abierto));
  raiz.querySelector(".yq-cerrar").addEventListener("click", () => alternar(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && chat.abierto) alternar(false);
  });

  raiz.querySelector(".yq-pie").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = campo.value;
    campo.value = "";
    enviar(t);
  });

  raiz.querySelectorAll(".yq-sugerencias button").forEach((b) => {
    b.addEventListener("click", () => {
      raiz.querySelector(".yq-sugerencias").remove();
      enviar(b.textContent);
    });
  });

  // El chat necesita red y el resto de la página no. Se apaga y se enciende
  // solo, en vez de dejar un botón que falla al pulsarlo.
  const segunRed = () => raiz.classList.toggle("yq-sinred", !navigator.onLine);
  addEventListener("online", segunRed);
  addEventListener("offline", segunRed);
  segunRed();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", montar);
} else {
  montar();
}
