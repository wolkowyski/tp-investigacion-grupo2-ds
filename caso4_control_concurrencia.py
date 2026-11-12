"""
CASO 4 · CONTROL DE CONCURRENCIA (Tema 10)

Pregunta guía (2da parte): ¿qué mecanismos garantizan una actualización consistente?

Escenario: Ana y Beto piden al mismo conductor, Carlos, al mismo tiempo.
Cada pedido hace "verificar y después actuar": lee si Carlos está disponible,
calcula la tarifa y recién después lo asigna.
"""
from consola import bien, codigo, mal, nota, parrafo, pausa, seccion, tabla, titulo
from db import conectar, filas, reiniciar, valor
from planificador import con_hilos, paso_a_paso


# ==========================================================================
# LA LÓGICA (lo que se explica en la exposición)
# ==========================================================================

def asignar_sin_control(pasajero, conductor_id):
    con = conectar()

    c = con.execute("SELECT disponible FROM conductores "
                    "WHERE id = ?", (conductor_id,)).fetchone()
    disp = "sí" if c["disponible"] else "no"
    yield f"LEE a Carlos: disponible = {disp}"      # 1) verificar
    if not c["disponible"]:
        return {"codigo": 409, "error": "no disponible"}

    yield "calcula la tarifa…"  # otro pedido puede leer lo mismo

    con.execute("BEGIN IMMEDIATE")                  # 2) actuar
    con.execute("UPDATE conductores SET disponible = 0 "
                "WHERE id = ?", (conductor_id,))
    cur = con.execute(
        "INSERT INTO reservas (pasajero, conductor_id) "
        "VALUES (?, ?)", (pasajero, conductor_id))
    con.execute("COMMIT")
    yield f"ASIGNA sin volver a verificar → reserva #{cur.lastrowid}"

    return {"codigo": 201, "reserva_id": cur.lastrowid}


def asignar_con_bloqueo_optimista(pasajero, conductor_id):
    con = conectar()

    c = con.execute("SELECT disponible, version FROM conductores "
                    "WHERE id = ?", (conductor_id,)).fetchone()
    disp, v = ("sí" if c["disponible"] else "no"), c["version"]
    yield f"LEE a Carlos: disponible = {disp}, versión = {v}"
    if not c["disponible"]:
        return {"codigo": 409, "error": "no disponible"}

    yield "calcula la tarifa…"

    con.execute("BEGIN IMMEDIATE")
    # Solo actualiza si la versión SIGUE siendo la que leyó
    cur = con.execute(
        "UPDATE conductores "
        "SET disponible = 0, version = version + 1 "
        "WHERE id = ? AND version = ?", (conductor_id, v))
    if cur.rowcount == 0:
        con.execute("ROLLBACK")
        yield f"UPDATE … version = {v}: 0 filas, otro ganó antes"
        return {"codigo": 409, "error": "conflicto"}

    cur = con.execute(
        "INSERT INTO reservas (pasajero, conductor_id) "
        "VALUES (?, ?)", (pasajero, conductor_id))
    con.execute("COMMIT")
    yield f"UPDATE … version = {v}: 1 fila → reserva #{cur.lastrowid}"

    return {"codigo": 201, "reserva_id": cur.lastrowid}


# ==========================================================================
# LA DEMO (solo presentación)
# ==========================================================================

ANA, BETO = "Pedido de Ana", "Pedido de Beto"
COLORES = ["cian", "amarillo"]
ORDEN = [ANA, BETO, ANA, BETO, ANA, BETO, ANA, BETO]


def _formato(r):
    if r["codigo"] == 201:
        return f"responde 201 · reserva #{r['reserva_id']}"
    return f"responde 409 · {r['error']}"


def _ver_tablas():
    tabla("tabla conductores", filas("SELECT id, nombre, disponible, version FROM conductores"),
          ["id", "nombre", "disponible", "version"])
    tabla("tabla reservas", filas("SELECT id, pasajero, conductor_id FROM reservas"),
          ["id", "pasajero", "conductor_id"])


def demo():
    reiniciar()
    titulo("CASO 4 · CONTROL DE CONCURRENCIA  ·  Tema 10", "naranja")
    parrafo("Pregunta guía: ¿qué mecanismos garantizan una actualización consistente de un recurso compartido?", col="naranja")
    parrafo("Mecanismos: transacciones, bloqueo pesimista (SELECT … FOR UPDATE: bloquea antes de leer), "
            "bloqueo optimista (una columna version: solo se escribe si nadie la cambió) y restricciones UNIQUE. "
            "Acá usamos BLOQUEO OPTIMISTA.")
    parrafo("Escenario: Ana y Beto piden a Carlos al mismo tiempo. Cada pedido hace “verificar y después actuar”: "
            "lee si Carlos está disponible, calcula la tarifa y recién después lo asigna.")
    pausa("Enter para ver el caso SIN control de concurrencia")

    # ---------------------------------------------------------------- A
    seccion("A)  SIN control de concurrencia", "rojo")
    parrafo("Los dos verifican antes de que el otro actúe, y al actuar nadie vuelve a verificar.")
    paso_a_paso({ANA: asignar_sin_control("Ana", 1), BETO: asignar_sin_control("Beto", 1)}, COLORES,
                orden=ORDEN, formato=_formato)
    print()
    _ver_tablas()
    mal(f"DOBLE ASIGNACIÓN: Carlos quedó con {valor('SELECT COUNT(*) FROM reservas')} reservas.")
    print()
    pausa("Enter para ver el caso CON control de concurrencia")

    # ---------------------------------------------------------------- B
    reiniciar()
    seccion("B)  CON control de concurrencia: bloqueo optimista", "verde")
    parrafo("La tabla conductores tiene una columna version. Al escribir se pide: “actualizá solo si la versión "
            "sigue siendo la que leí”, y se incrementa. El que escribe segundo ya no la encuentra.")
    codigo(["UPDATE conductores SET disponible = 0, version = version + 1",
            "WHERE id = ? AND version = ?        -- la versión que se leyó"])
    paso_a_paso({ANA: asignar_con_bloqueo_optimista("Ana", 1), BETO: asignar_con_bloqueo_optimista("Beto", 1)},
                COLORES, orden=ORDEN, formato=_formato)
    print()
    _ver_tablas()
    bien("Un éxito y un conflicto controlado: una sola reserva, y Beto sabe que perdió (409).")
    nota("Mismo orden, mismas lecturas que en A. Lo único que cambió es la condición en el UPDATE.")
    print()
    pausa("Enter: comprobación con hilos reales (sin pausas)")

    # ---------------------------------------------------------------- comprobación
    seccion("Comprobación con hilos reales: 20 pasajeros piden a Carlos a la vez", "cian")
    reiniciar()
    con_hilos([asignar_sin_control(f"P{i}", 1) for i in range(20)])
    sin = valor("SELECT COUNT(*) FROM reservas")
    reiniciar()
    respuestas = con_hilos([asignar_con_bloqueo_optimista(f"P{i}", 1) for i in range(20)])
    con = valor("SELECT COUNT(*) FROM reservas")
    conflictos = sum(r["codigo"] == 409 for r in respuestas)
    mal(f"Sin control: Carlos quedó asignado {sin} veces.")
    bien(f"Con bloqueo optimista: {con} reserva y {conflictos} rechazos controlados (409).")
    print()
    nota("Alternativa: bloqueo pesimista (SELECT … FOR UPDATE en PostgreSQL), que hace esperar a los demás. "
         "Conviene cuando hay mucha competencia; el optimista, cuando los conflictos son raros.")
