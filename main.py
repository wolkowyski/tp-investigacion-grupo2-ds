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
"""
import sys

import caso1_idempotencia
import caso2_deduplicacion
import caso3_condicion_carrera
import caso4_control_concurrencia
import caso5_todo_junto
from consola import AUTO, color, limpiar, pausa, tabla, titulo

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


def correr(clave):
    if clave == "todos":
        for c in CASOS:
            limpiar()
            CASOS[c][3]()
            pausa("Enter para el siguiente caso")
        limpiar()
        resumen()
    elif clave in CASOS:
        limpiar()
        CASOS[clave][3]()
    elif clave in ("6", "resumen"):
        limpiar()
        resumen()


def menu():
    while True:
        limpiar()
        titulo("Demo · Grupo 2 · Idempotencia y concurrencia", "cian")
        print()
        for clave, (nombre, tema, col, _) in CASOS.items():
            print(f"   {color(clave, col, 'negrita')})  {nombre}  {color('· ' + tema, 'gris')}")
        print(f"   {color('6', 'gris', 'negrita')})  Resumen")
        print(f"   {color('t', 'cian', 'negrita')})  Todos seguidos")
        print(f"   {color('0', 'gris', 'negrita')})  Salir")
        print()
        opcion = input(color("   Elegí una opción: ", "negrita")).strip().lower()
        if opcion in ("0", "q", "salir"):
            break
        correr("todos" if opcion == "t" else opcion)
        print()
        pausa("Enter para volver al menú")


if __name__ == "__main__":
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    try:
        if argumentos:
            correr(argumentos[0])
        elif AUTO:
            correr("todos")
        else:
            menu()
    except (KeyboardInterrupt, EOFError):
        print(color("\n  Demo terminada.", "gris"))
