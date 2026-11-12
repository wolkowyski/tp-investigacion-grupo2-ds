"""
CASO 1 · IDEMPOTENCIA (Tema 9)

Pregunta guía: ¿cómo evitar efectos duplicados cuando un cliente REINTENTA una operación?

Escenario: la app de Ana manda "crear reserva", la respuesta tarda, la app no sabe
si llegó y reintenta. Al servidor le llegan 2 pedidos iguales casi al mismo tiempo.

Cada función representa el endpoint POST /reservas. Cada `yield` es un paso.
"""
import json
import random
import sqlite3
import string
import time

from consola import bien, mal, nota, parrafo, pausa, seccion, tabla, titulo, codigo
from db import conectar, filas, reiniciar, valor
from planificador import con_hilos, paso_a_paso


# ==========================================================================
# LA LÓGICA (lo que se explica en la exposición)
# ==========================================================================

def crear_reserva_sin_idempotencia(pasajero, conductor_id):
    con = conectar()
    yield f"recibe POST /reservas ({pasajero})"

    cur = con.execute(
        "INSERT INTO reservas (pasajero, conductor_id) "
        "VALUES (?, ?)", (pasajero, conductor_id))
    yield f"INSERT en reservas: crea la reserva #{cur.lastrowid}"

    return {"codigo": 201, "reserva_id": cur.lastrowid}


def crear_reserva_con_idempotencia(clave, pasajero, conductor_id):
    con = conectar()
    datos = json.dumps({"pasajero": pasajero,
                        "conductor_id": conductor_id})
    yield f"recibe POST /reservas con Idempotency-Key: {clave}"

    # 1) Guardar la clave. Es PRIMARY KEY: entra UNO solo,
    #    aunque lleguen varios pedidos a la vez.
    try:
        con.execute("INSERT INTO idempotencia (clave, datos) "
                    "VALUES (?, ?)", (clave, datos))
        es_reintento = False
    except sqlite3.IntegrityError:
        es_reintento = True

    if es_reintento:
        yield "la clave YA EXISTE: es un reintento"
        # 2a) Devolver lo que respondió el primer pedido
        while True:
            fila = con.execute(
                "SELECT datos, respuesta FROM idempotencia "
                "WHERE clave = ?", (clave,)).fetchone()
            if fila["datos"] != datos:
                yield "pero los datos son OTROS: se rechaza"
                return {"codigo": 422, "error": "datos distintos"}
            if fila["respuesta"]:
                yield "devuelve la MISMA respuesta del primero"
                respuesta = json.loads(fila["respuesta"])
                return {**respuesta, "repetida": True}
            yield "el primer pedido todavía no terminó: espera"
            time.sleep(0.01)

    yield "guarda la clave: es la primera vez que la ve"

    # 2b) Es el primero: crear la reserva de verdad
    cur = con.execute(
        "INSERT INTO reservas (pasajero, conductor_id) "
        "VALUES (?, ?)", (pasajero, conductor_id))
    respuesta = {"codigo": 201, "reserva_id": cur.lastrowid}
    yield f"INSERT en reservas: crea la reserva #{cur.lastrowid}"

    # 3) Guardar la respuesta junto a la clave, para los reintentos
    con.execute("UPDATE idempotencia SET respuesta = ? "
                "WHERE clave = ?", (json.dumps(respuesta), clave))
    yield "guarda la respuesta junto a la clave"

    return respuesta


# ==========================================================================
# LA DEMO (solo presentación)
# ==========================================================================

def _formato(r):
    if r["codigo"] != 201:
        return f"responde {r['codigo']} · {r['error']}"
    return f"responde {r['codigo']} · reserva #{r['reserva_id']}" + ("  (repetida)" if r.get("repetida") else "")


def _ver_reservas():
    tabla("tabla reservas", filas("SELECT id, pasajero, conductor_id FROM reservas"), ["id", "pasajero", "conductor_id"])


COLORES = ["azul", "cian", "violeta"]


def demo():
    reiniciar()
    titulo("CASO 1 · IDEMPOTENCIA  ·  Tema 9", "azul")
    parrafo("Pregunta guía: ¿cómo evitar efectos de negocio duplicados cuando un cliente REINTENTA una operación?", col="azul")
    parrafo("Una operación es idempotente si hacerla 1 vez o N veces deja el sistema en el mismo estado. "
            "GET, PUT y DELETE lo son. POST no: cada POST crea algo nuevo.")
    parrafo("Escenario: la app de Ana manda “crear reserva”. La respuesta tarda, la app no sabe si llegó "
            "y REINTENTA. Al servidor le llegan 2 pedidos iguales casi al mismo tiempo.")
    pausa("Enter para ver el caso SIN idempotencia")

    # ---------------------------------------------------------------- A
    seccion("A)  SIN idempotencia", "rojo")
    parrafo("El servidor no tiene forma de saber que los 2 pedidos son el mismo: cada uno crea una reserva.")
    pedidos = {f"Ana · intento {i}": crear_reserva_sin_idempotencia("Ana", 1) for i in (1, 2)}
    paso_a_paso(pedidos, COLORES, formato=_formato)
    print()
    _ver_reservas()
    mal(f"Ana quería UN viaje y quedó con {valor('SELECT COUNT(*) FROM reservas')} reservas.")
    print()
    pausa("Enter para ver el caso CON idempotencia")

    # ---------------------------------------------------------------- B
    reiniciar()
    clave = "ana-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    seccion("B)  CON idempotencia (Idempotency-Key)", "verde")
    parrafo(f"La app genera UNA clave por intención ({clave}) y la manda IGUAL en cada reintento. "
            "El servidor la guarda en la tabla idempotencia, donde la clave es PRIMARY KEY: "
            "solo el primer pedido la puede insertar. Los demás saben que son reintentos.")
    codigo(["INSERT INTO idempotencia (clave, datos) VALUES (?, ?)   -- clave = PRIMARY KEY"])
    pedidos = {f"Ana · intento {i}": crear_reserva_con_idempotencia(clave, "Ana", 1) for i in (1, 2)}
    paso_a_paso(pedidos, COLORES, formato=_formato)
    print()
    _ver_reservas()
    tabla("tabla idempotencia", filas("SELECT clave, respuesta FROM idempotencia"), ["clave", "respuesta"])
    bien("Una sola reserva, y los 2 intentos recibieron la MISMA respuesta.")
    print()
    pausa("Enter: ¿y si alguien reutiliza la clave con OTROS datos?")

    seccion("¿Y si la clave se reutiliza con otros datos?", "amarillo")
    parrafo("Ana manda la misma clave, pero ahora pide a Diana. Si le devolviéramos la reserva vieja, "
            "creería que reservó a Diana cuando en realidad tiene a Carlos.")
    paso_a_paso({"Ana · misma clave, otro conductor": crear_reserva_con_idempotencia(clave, "Ana", 2)},
                ["amarillo"], formato=_formato)
    print()
    bien("Se rechaza: esa clave ya pertenece a otra intención. Para un pedido nuevo, clave nueva.")
    print()
    pausa("Enter: comprobación con hilos reales (sin pausas)")

    # ---------------------------------------------------------------- comprobación
    seccion("Comprobación con hilos reales: 30 reintentos simultáneos", "cian")
    parrafo("Ahora sin pausas ni orden elegido: 30 hilos mandan la misma reserva a la vez.")
    reiniciar()
    con_hilos([crear_reserva_sin_idempotencia("Ana", 1) for _ in range(30)])
    sin = valor("SELECT COUNT(*) FROM reservas")
    reiniciar()
    respuestas = con_hilos([crear_reserva_con_idempotencia("ana-real", "Ana", 1) for _ in range(30)])
    con = valor("SELECT COUNT(*) FROM reservas")
    distintas = len({r["reserva_id"] for r in respuestas})
    mal(f"Sin idempotencia: {sin} reservas.")
    bien(f"Con idempotencia: {con} reserva; las 30 respuestas apuntan a {distintas} sola reserva.")
    print()
    nota("Idempotencia: la misma intención (misma clave) produce un solo efecto, aunque llegue muchas veces.")
