"""
TP de Investigación · Desarrollo de Software · UTN FRRe 2026 · Grupo 2
  Tema 9:  Idempotencia y deduplicación
  Tema 10: Condiciones de carrera y control de concurrencia

Demo por terminal: 4 casos, cada uno SIN y CON el concepto, y un caso 5 con todo junto.
Se avanza paso a paso con Enter.

Ejecutar:
    python main.py            menú
    python main.py 3          directo al caso 3
    python main.py todos      los 5 casos seguidos
    python main.py --auto     sin pausas (para ensayar)

Al arrancar, si no hay una API corriendo, la abre en su propia ventana (en Windows),
y al final de cada caso sigue con la parte HTTP: Postman y los mismos pedidos por
HTTP, muchos a la vez (prueba_http.py).
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

import caso1_idempotencia
import caso2_deduplicacion
import caso3_condicion_carrera
import caso4_control_concurrencia
import caso5_todo_junto
import prueba_http
from consola import AUTO, color, limpiar, pausa, tabla, titulo

CARPETA = os.path.dirname(os.path.abspath(__file__))
API = f"http://127.0.0.1:{os.environ.get('PORT', '5050')}"
PANEL = API + "/panel"

CASOS = {
    "1": ("Idempotencia", "Tema 9", "azul", caso1_idempotencia.demo),
    "2": ("Deduplicación", "Tema 9", "azul", caso2_deduplicacion.demo),
    "3": ("Condición de carrera", "Tema 10", "naranja", caso3_condicion_carrera.demo),
    "4": ("Control de concurrencia", "Tema 10", "naranja", caso4_control_concurrencia.demo),
    "5": ("Todo junto", "Tema 9 + 10", "verde", caso5_todo_junto.demo),
}


def resumen():
    titulo("RESUMEN · los 5 casos", "verde")
    tabla("qué vimos", [
        {"caso": "1 Idempotencia", "A)": "sin clave: 2 reintentos → 2 reservas",
         "B)": "con Idempotency-Key: 1 reserva", "clave del mecanismo": "PRIMARY KEY sobre la clave"},
        {"caso": "2 Deduplicación", "A)": "sin dedup: se paga 2 veces",
         "B)": "con dedup: se paga 1 vez", "clave del mecanismo": "PRIMARY KEY sobre el id del mensaje"},
        {"caso": "3 Condición de carrera", "A)": "en serie: $13500 ✔",
         "B)": "a la vez: $12000 ✘", "clave del mecanismo": "leer y escribir separados"},
        {"caso": "4 Control de concurrencia", "A)": "sin control: doble asignación",
         "B)": "con versión: 1 éxito y 1 conflicto", "clave del mecanismo": "UPDATE … WHERE version = ?"},
        {"caso": "5 Todo junto", "A)": "sin nada: 4 reservas",
         "B)": "con los dos: 1 reserva, respuestas coherentes", "clave del mecanismo": "clave idempotente + version"},
    ], ["caso", "A)", "B)", "clave del mecanismo"])
    print(color("  La idempotencia hace que la MISMA intención tenga un solo efecto.", "azul", "negrita"))
    print(color("  El control de concurrencia hace que intenciones DISTINTAS no se pisen.", "naranja", "negrita"))
    print()


# ==========================================================================
# La API HTTP: se levanta sola y cada caso termina con su parte HTTP
# ==========================================================================

def api_activa():
    try:
        with urllib.request.urlopen(API + "/estado", timeout=0.6):   # /estado no se registra en la API
            return True
    except urllib.error.HTTPError:
        return True    # respondió (aunque sea con un error): hay un servidor en ese puerto
    except OSError:
        return False


def levantar_api():
    """Si no hay una API corriendo, la abre en su propia ventana (solo en Windows).
    Devuelve "ya estaba", "levantada" o None si no hay API."""
    if api_activa():
        return "ya estaba"
    if os.name != "nt" or AUTO:
        return None
    entorno = {k: v for k, v in os.environ.items() if k != "DB_PATH"}   # la API usa su propia base: api.db
    subprocess.Popen([sys.executable, "api.py"], cwd=CARPETA, env=entorno,
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
    for _ in range(40):
        time.sleep(0.15)
        if api_activa():
            return "levantada"
    return None


def linea_api(estado):
    if estado:
        detalle = "la abrí en otra ventana" if estado == "levantada" else "ya estaba corriendo"
        print(color(f"   API HTTP en {API} ({detalle}) · base en vivo: {PANEL}", "gris"))
    else:
        print(color("   API HTTP: no está corriendo. Abrila en otra terminal con  py api.py  "
                    "(o  docker compose up api).", "amarillo"))


def parte_http(clave):
    """Al final de cada caso: Postman y después los mismos pedidos por HTTP, muchos a la vez."""
    nombre = CASOS[clave][0]
    print()
    print(color(f"  ➜  Ahora como API real: en Postman, carpeta «Caso {clave} · {nombre}» (A y después B).", "cian", "negrita"))
    if AUTO:
        print(color(f"     Con pedidos HTTP a la vez:  py prueba_http.py {clave}", "gris"))
        return
    print(color("     Mientras mandás los pedidos, mirá la ventana de la API y el panel de la base.", "gris"))
    pausa("Enter cuando termines con Postman → los mismos pedidos por HTTP, muchos a la vez")
    print()
    prueba_http.CASOS[clave](prueba_http.conectar_api(API))


def correr(clave):
    if clave == "todos":
        for c in CASOS:
            limpiar()
            CASOS[c][3]()
            parte_http(c)
            pausa("Enter para el siguiente caso")
        limpiar()
        resumen()
    elif clave in CASOS:
        limpiar()
        CASOS[clave][3]()
        parte_http(clave)
    elif clave in ("6", "resumen"):
        limpiar()
        resumen()
    elif clave == "p":
        webbrowser.open(PANEL)


def menu(estado_api):
    while True:
        limpiar()
        titulo("Demo · Grupo 2 · Idempotencia y concurrencia", "cian")
        linea_api(estado_api)
        print()
        for clave, (nombre, tema, col, _) in CASOS.items():
            print(f"   {color(clave, col, 'negrita')})  {nombre}  {color('· ' + tema, 'gris')}")
        print(f"   {color('6', 'gris', 'negrita')})  Resumen")
        print(f"   {color('t', 'cian', 'negrita')})  Todos seguidos")
        print(f"   {color('p', 'cian', 'negrita')})  Abrir el panel de la base en el navegador")
        print(f"   {color('0', 'gris', 'negrita')})  Salir")
        print()
        opcion = input(color("   Elegí una opción: ", "negrita")).strip().lower()
        if opcion in ("0", "q", "salir"):
            break
        if opcion == "p":
            if not api_activa():
                estado_api = levantar_api()
            correr("p")
            continue
        correr("todos" if opcion == "t" else opcion)
        print()
        pausa("Enter para volver al menú")


if __name__ == "__main__":
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    estado_api = levantar_api()
    if estado_api == "levantada":
        webbrowser.open(PANEL)   # la primera vez abre también el panel de la base
    try:
        if argumentos:
            correr(argumentos[0])
        elif AUTO:
            correr("todos")
        else:
            menu(estado_api)
    except (KeyboardInterrupt, EOFError):
        print(color("\n  Demo terminada.", "gris"))
