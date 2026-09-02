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

/* Dónde vive el agente. En local apunta al servidor de desarrollo y en
   producción a lo que diga `YACHAQ_API` en index.html.
 *
 * Se decide aquí y no a mano porque durante el desarrollo hubo que ir cambiando
 * esa constante en cada prueba, y una de las veces se quedó vacía: el widget
 * dejó de pintarse y parecía que había desaparecido. Que el código lo deduzca
 * quita ese paso. */
const LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);
const YACHAQ = window.YACHAQ_API || (LOCAL ? "http://127.0.0.1:8000" : "");

/* La mascota va en línea y no como <img>: así el CSS puede animar la cabeza, el
   ala y las patas por separado.

   Un piquero patiazul, que es la especie de la que más habla el proyecto. Está
   dibujado para leerse a 40 píxeles, que es el tamaño real en el botón: formas
   grandes, pocas piezas y las patas bien azules, que es lo que lo hace
   reconocible de un vistazo. La primera versión tenía el detalle de un dibujo a
   tamaño completo y a 40px era una mancha gris. */
const PIQUERO = `
  <svg class="yq-pajaro" viewBox="0 0 64 64" aria-hidden="true">
    <g class="yq-patas" stroke="#3d9be0" stroke-width="4.5" stroke-linecap="round" fill="none">
      <path d="M25 46 L22 56"/><path d="M22 56 L16 58"/><path d="M22 56 L26 59"/>
      <path d="M36 46 L39 56"/><path d="M39 56 L34 59"/><path d="M39 56 L45 58"/>
    </g>

    <ellipse cx="30" cy="35" rx="16" ry="12.5" fill="#f2f3ee"/>
    <path class="yq-ala" d="M24 27 Q13 25 20 38 Q28 42 32 33 Z" fill="#7d8a92"/>

    <g class="yq-cabeza">
      <circle cx="43" cy="19" r="11" fill="#f2f3ee"/>
      <path d="M34 12 Q43 6 52 13 Q43 10 34 12 Z" fill="#b8a878"/>
      <path d="M53 16 L64 21 L53 25 Z" fill="#6b757c"/>
      <g class="yq-ojo">
        <circle cx="45" cy="17" r="4" fill="#14181b"/>
        <circle cx="46.4" cy="15.6" r="1.4" fill="#ffffff"/>
      </g>
    </g>
  </svg>`;

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
  document.querySelector(".yq")?.classList.add("yq-ocupado");

  // Un servidor gratuito puede estar dormido y tardar un minuto en despertar.
  // Sin avisar, eso se lee como que el chat está roto, así que a los seis
  // segundos se dice lo que pasa en vez de dejar los puntitos girando.
  const aviso = setTimeout(() => {
    pensando.classList.add("yq-lento");
    pensando.setAttribute("data-nota", "despertando el servidor…");
  }, 6000);

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
    clearTimeout(aviso);
    chat.esperando = false;
    document.querySelector(".yq")?.classList.remove("yq-ocupado");
  }
}

function montar() {
  if (!YACHAQ) return;      // sin servidor configurado, no se pinta nada

  const raiz = nodo("div", "yq");
  raiz.innerHTML = `
    <button class="yq-boton" aria-label="Preguntar a Yachaq" aria-expanded="false">
      ${PIQUERO}
      <span class="yq-globo">¿te ayudo?</span>
    </button>
    <section class="yq-panel" hidden aria-label="Chat con Yachaq">
      <header class="yq-cab">
        <span class="yq-avatar">${PIQUERO}</span>
        <div class="yq-titulo">
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

  // Saluda una vez, a los cuatro segundos, y no vuelve a insistir: un globo que
  // reaparece cada poco es de las cosas que hacen cerrar una página.
  if (!sessionStorage.getItem("yq-saludo")) {
    setTimeout(() => {
      if (!chat.abierto) {
        raiz.classList.add("yq-saluda");
        setTimeout(() => raiz.classList.remove("yq-saluda"), 5200);
      }
      sessionStorage.setItem("yq-saludo", "1");
    }, 4000);
  }

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
