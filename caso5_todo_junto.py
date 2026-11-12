"""
CASO 5 · TODO JUNTO (Tema 9 + Tema 10)

Escenario: Ana y Beto piden a Carlos al mismo tiempo, y la app de cada uno
reintenta (2 pedidos por pasajero, 4 en total).

  - La IDEMPOTENCIA (caso 1) agrupa los reintentos de cada pasajero: misma clave.
  - El BLOQUEO OPTIMISTA (caso 4) decide quién se queda con Carlos.

Y muestra por qué se necesitan los dos: la idempotencia sola, con pedidos en
paralelo, también necesita control de concurrencia (la PRIMARY KEY de la clave).
"""
import json
import random
import sqlite3
import string
import time

from caso4_control_concurrencia import asignar_con_bloqueo_optimista, asignar_sin_control
from consola import LineaDeTiempo, bien, codigo, mal, nota, parrafo, pausa, seccion, tabla, titulo
from db import conectar, filas, reiniciar, valor
from planificador import con_hilos, intercalar, paso_a_paso


# ==========================================================================
# LA LÓGICA (lo que se explica en la exposición)
# ==========================================================================

def reservar(clave, pasajero, conductor_id):
    """Los dos mecanismos juntos."""
    con = conectar()
    datos = json.dumps({"pasajero": pasajero,
                        "conductor_id": conductor_id})
    yield f"recibe POST /reservas con clave {clave}"

    # TEMA 9: ¿es un reintento? (la clave es PRIMARY KEY)
    try:
        con.execute("INSERT INTO idempotencia (clave, datos) "
                    "VALUES (?, ?)", (clave, datos))
        es_reintento = False
    except sqlite3.IntegrityError:
        es_reintento = True

    if es_reintento:
        yield "la clave YA EXISTE: es un reintento"
        while True:
            fila = con.execute(
                "SELECT respuesta FROM idempotencia "
                "WHERE clave = ?", (clave,)).fetchone()
            if fila["respuesta"]:
                yield "devuelve la MISMA respuesta del primero"
                respuesta = json.loads(fila["respuesta"])
                return {**respuesta, "repetida": True}
            yield "el primero todavía no terminó: espera"
            time.sleep(0.01)

    yield "clave nueva: este pedido la procesa"

    # TEMA 10: asignar con bloqueo optimista (la función del caso 4)
    respuesta = yield from asignar_con_bloqueo_optimista(
        pasajero, conductor_id)

    # TEMA 9: guardar la respuesta (201 o 409) para los reintentos
    con.execute("UPDATE idempotencia SET respuesta = ? "
                "WHERE clave = ?", (json.dumps(respuesta), clave))
    yield f"guarda la respuesta ({respuesta['codigo']}) para reintentos"

    return respuesta


# ==========================================================================
# LA DEMO (solo presentación)
# ==========================================================================

A1, A2, B1, B2 = "Ana · intento 1", "Ana · intento 2", "Beto · intento 1", "Beto · intento 2"
COLORES = ["cian", "azul", "amarillo", "naranja"]


def _formato(r):
    texto = f"responde {r['codigo']} · " + (f"reserva #{r['reserva_id']}" if r["codigo"] == 201 else r["error"])
    return texto + ("  (repetida)" if r.get("repetida") else "")


def _clave(nombre):
    return nombre + "-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=4))


def demo():
    reiniciar()
    titulo("CASO 5 · TODO JUNTO  ·  Tema 9 + Tema 10", "verde")
    parrafo("Ana y Beto piden a Carlos al mismo tiempo, y la app de cada uno REINTENTA: "
            "llegan 4 pedidos (2 de Ana y 2 de Beto) casi a la vez.")
    parrafo("Hay dos problemas mezclados: reintentos de la MISMA intención (tema 9) "
            "e intenciones DISTINTAS que compiten por Carlos (tema 10).")
    pausa("Enter para ver qué pasa SIN ningún mecanismo")

    # ---------------------------------------------------------------- A
    seccion("A)  SIN ningún mecanismo", "rojo")
    parrafo("Se ejecuta de una vez (sin pausas), intercalando los 4 pedidos:")
    pedidos = {n: asignar_sin_control(n.split(" ")[0], 1) for n in (A1, A2, B1, B2)}
    linea = LineaDeTiempo(list(pedidos), COLORES)
    linea.encabezado()
    intercalar(pedidos, despues=lambda num, nombre, texto, final:
               linea.paso(num, nombre, f"→ {_formato(texto)}" if final else texto, final))
    print()
    tabla("tabla reservas", filas("SELECT id, pasajero, conductor_id FROM reservas"), ["id", "pasajero", "conductor_id"])
    mal(f"Carlos quedó con {valor('SELECT COUNT(*) FROM reservas')} reservas: duplicados Y doble asignación.")
    print()
    pausa("Enter para ver el caso CON los dos mecanismos")

    # ---------------------------------------------------------------- B
    reiniciar()
    clave_ana, clave_beto = _clave("ana"), _clave("beto")
    seccion("B)  CON idempotencia + bloqueo optimista", "verde")
    parrafo(f"Primero compiten los pedidos originales de Ana y Beto; después llegan los reintentos. "
            f"Ana usa la clave {clave_ana} en sus 2 intentos y Beto, {clave_beto}. "
            "La función reservar() primero resuelve la idempotencia y después llama a la "
            "asignación con bloqueo optimista del caso 4:")
    codigo(["respuesta = yield from asignar_con_bloqueo_optimista(",
            "    pasajero, conductor_id)"])
    pedidos = {
        A1: reservar(clave_ana, "Ana", 1), A2: reservar(clave_ana, "Ana", 1),
        B1: reservar(clave_beto, "Beto", 1), B2: reservar(clave_beto, "Beto", 1),
    }
    # Primero compiten los pedidos originales; los reintentos llegan después
    # (la app reintenta porque la respuesta no le llegó a tiempo).
    orden = [A1, B1] * 7 + [A2, B2] * 4
    respuestas = paso_a_paso(pedidos, COLORES, orden=orden, formato=_formato)
    print()
    tabla("tabla reservas", filas("SELECT id, pasajero, conductor_id FROM reservas"), ["id", "pasajero", "conductor_id"])
    tabla("tabla idempotencia", filas("SELECT clave, respuesta FROM idempotencia"), ["clave", "respuesta"])
    ganador = next(n.split(" ")[0] for n, r in respuestas.items() if r["codigo"] == 201)
    perdedor = "Beto" if ganador == "Ana" else "Ana"
    bien(f"1 sola reserva. {ganador} recibió 201 en sus 2 intentos; {perdedor}, 409 en sus 2 intentos.")
    nota("La idempotencia agrupó los reintentos de cada uno (misma respuesta) y el bloqueo optimista "
         "decidió quién se queda con Carlos. Fijate que el 409 también se guarda: el reintento de quien "
         "perdió recibe el mismo 409, no un resultado distinto.")
    print()
    pausa("Enter: comprobación con hilos reales (sin pausas)")

    # ---------------------------------------------------------------- comprobación
    seccion("Comprobación con hilos reales: 5 pasajeros × 3 reintentos, todos a la vez", "cian")
    reiniciar()
    con_hilos([asignar_sin_control(f"P{i}", 1) for i in range(5) for _ in range(3)])
    sin = valor("SELECT COUNT(*) FROM reservas")
    reiniciar()
    claves = {i: _clave(f"p{i}") for i in range(5)}
    pedidos_hilos = [(i, reservar(claves[i], f"P{i}", 1)) for i in range(5) for _ in range(3)]
    respuestas = con_hilos([g for _, g in pedidos_hilos])
    con = valor("SELECT COUNT(*) FROM reservas")
    por_pasajero = {}
    for (i, _), r in zip(pedidos_hilos, respuestas):
        por_pasajero.setdefault(i, set()).add(r["codigo"])
    coherentes = sum(len(c) == 1 for c in por_pasajero.values())
    mal(f"Sin mecanismos: Carlos quedó con {sin} reservas.")
    bien(f"Con los dos: {con} reserva, y {coherentes} de 5 pasajeros recibieron siempre la misma respuesta en sus 3 intentos.")
    print()
    nota("Idempotencia: la misma intención, un solo efecto. Control de concurrencia: intenciones distintas, sin pisarse.")
