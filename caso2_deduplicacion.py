"""
CASO 2 · DEDUPLICACIÓN (Tema 9)

Pregunta guía: ¿cómo evitar efectos duplicados cuando un MENSAJE se entrega más de una vez?

Escenario: al terminar un viaje, el módulo de Viajes publica el mensaje
"ViajeFinalizado" (id msg-V17). El módulo de Pagos lo consume y le acredita
$1500 a Carlos. La cola garantiza entrega "al menos una vez": si Pagos procesa
el mensaje pero la confirmación (ACK) se pierde, la cola lo vuelve a entregar.
"""
import sqlite3

from consola import bien, codigo, mal, nota, parrafo, pausa, seccion, tabla, titulo
from db import conectar, filas, reiniciar, saldo_de, valor
from planificador import con_hilos, paso_a_paso

MENSAJE = {"id": "msg-V17", "conductor_id": 1, "monto": 1500}


# ==========================================================================
# LA LÓGICA (lo que se explica en la exposición)
# ==========================================================================

def procesar_sin_deduplicacion(mensaje):
    con = conectar()
    id_msg, monto, cid = mensaje["id"], mensaje["monto"], mensaje["conductor_id"]
    yield f"recibe {id_msg}: acreditar ${monto} a Carlos"

    con.execute("BEGIN IMMEDIATE")
    con.execute("UPDATE conductores SET saldo = saldo + ? "
                "WHERE id = ?", (monto, cid))
    con.execute("INSERT INTO pagos (mensaje_id, conductor_id, monto) "
                "VALUES (?, ?, ?)", (id_msg, cid, monto))
    con.execute("COMMIT")
    yield f"acredita ${monto} → saldo de Carlos: ${saldo_de(con, cid)}"

    return "envía ACK"


def procesar_con_deduplicacion(mensaje):
    con = conectar()
    id_msg, monto, cid = mensaje["id"], mensaje["monto"], mensaje["conductor_id"]
    yield f"recibe {id_msg}: acreditar ${monto} a Carlos"

    con.execute("BEGIN IMMEDIATE")
    # 1) Registrar el id. Es PRIMARY KEY: si ya se procesó, falla
    try:
        con.execute("INSERT INTO mensajes_procesados (id_mensaje) "
                    "VALUES (?)", (id_msg,))
    except sqlite3.IntegrityError:
        con.execute("ROLLBACK")
        yield f"{id_msg} YA FUE PROCESADO: se descarta, no se paga"
        return "envía ACK (duplicado descartado)"

    # 2) Recién ahí se paga, en la MISMA transacción
    con.execute("UPDATE conductores SET saldo = saldo + ? "
                "WHERE id = ?", (monto, cid))
    con.execute("INSERT INTO pagos (mensaje_id, conductor_id, monto) "
                "VALUES (?, ?, ?)", (id_msg, cid, monto))
    con.execute("COMMIT")
    yield f"registra {id_msg} y acredita ${monto} → saldo: ${saldo_de(con, cid)}"

    return "envía ACK"


# ==========================================================================
# LA DEMO (solo presentación)
# ==========================================================================

def cola_que_reentrega(id_mensaje):
    """La cola de mensajes (no es parte de nuestra solución: así se comporta la infraestructura)."""
    yield f"entrega {id_mensaje} a Pagos y espera la confirmación (ACK)"
    yield "✘ el ACK nunca llega: se perdió en la red"
    yield f"no sabe si se procesó → VUELVE a entregar {id_mensaje}"
    return "✔ ahora sí recibe el ACK"


ORDEN = ["Cola de mensajes", "Pagos · entrega 1", "Pagos · entrega 1", "Pagos · entrega 1",
         "Cola de mensajes", "Cola de mensajes",
         "Pagos · entrega 2", "Pagos · entrega 2", "Pagos · entrega 2", "Cola de mensajes"]
COLORES = ["gris", "azul", "violeta"]


def _ver_tablas(con_procesados=False):
    tabla("tabla conductores", filas("SELECT nombre, saldo FROM conductores WHERE id = 1"), ["nombre", "saldo"])
    tabla("tabla pagos", filas("SELECT id, mensaje_id, monto FROM pagos"), ["id", "mensaje_id", "monto"])
    if con_procesados:
        tabla("tabla mensajes_procesados", filas("SELECT id_mensaje FROM mensajes_procesados"), ["id_mensaje"])


def demo():
    reiniciar()
    titulo("CASO 2 · DEDUPLICACIÓN  ·  Tema 9", "azul")
    parrafo("Pregunta guía: ¿cómo evitar efectos de negocio duplicados cuando un MENSAJE se entrega más de una vez?", col="azul")
    parrafo("Entre módulos se usan colas de mensajes, que garantizan entrega “al menos una vez”: "
            "un mensaje puede llegar repetido. Deduplicar es reconocer que un mensaje ya se procesó "
            "(por su id) y descartarlo.")
    parrafo("Escenario: termina un viaje y el módulo de Viajes publica ViajeFinalizado (id msg-V17). "
            "El módulo de Pagos lo consume y le acredita $1500 a Carlos, que tiene $10000.")
    pausa("Enter para ver el caso SIN deduplicación")

    # ---------------------------------------------------------------- A
    seccion("A)  SIN deduplicación", "rojo")
    pedidos = {
        "Cola de mensajes": cola_que_reentrega(MENSAJE["id"]),
        "Pagos · entrega 1": procesar_sin_deduplicacion(MENSAJE),
        "Pagos · entrega 2": procesar_sin_deduplicacion(MENSAJE),
    }
    paso_a_paso(pedidos, COLORES, orden=ORDEN)
    print()
    _ver_tablas()
    mal(f"Carlos cobró DOS veces: saldo ${valor('SELECT saldo FROM conductores WHERE id = 1')} en vez de $11500.")
    print()
    pausa("Enter para ver el caso CON deduplicación")

    # ---------------------------------------------------------------- B
    reiniciar()
    seccion("B)  CON deduplicación (id de mensaje procesado)", "verde")
    parrafo("Pagos guarda el id de cada mensaje que procesa en una tabla donde es PRIMARY KEY, "
            "en la MISMA transacción que el pago. Si el mensaje vuelve, el INSERT falla y se descarta.")
    codigo(["BEGIN",
            "INSERT INTO mensajes_procesados (id_mensaje) VALUES ('msg-V17')   -- PRIMARY KEY",
            "UPDATE conductores SET saldo = saldo + 1500 WHERE id = 1",
            "COMMIT"])
    pedidos = {
        "Cola de mensajes": cola_que_reentrega(MENSAJE["id"]),
        "Pagos · entrega 1": procesar_con_deduplicacion(MENSAJE),
        "Pagos · entrega 2": procesar_con_deduplicacion(MENSAJE),
    }
    paso_a_paso(pedidos, COLORES, orden=ORDEN)
    print()
    _ver_tablas(con_procesados=True)
    bien("Carlos cobró UNA vez ($11500). La segunda entrega se reconoció y se descartó.")
    nota("¿Por qué en la misma transacción? Si se pagara y se cayera antes de registrar el id, "
         "la reentrega volvería a pagar. Juntos, o se hacen los dos o ninguno.")
    print()
    pausa("Enter: comprobación con hilos reales (sin pausas)")

    # ---------------------------------------------------------------- comprobación
    seccion("Comprobación con hilos reales: el mismo mensaje entregado 10 veces a la vez", "cian")
    reiniciar()
    con_hilos([procesar_sin_deduplicacion(MENSAJE) for _ in range(10)])
    sin = valor("SELECT saldo FROM conductores WHERE id = 1")
    reiniciar()
    con_hilos([procesar_con_deduplicacion(MENSAJE) for _ in range(10)])
    con = valor("SELECT saldo FROM conductores WHERE id = 1")
    mal(f"Sin deduplicación: saldo ${sin} (se pagó {(sin - 10000) // 1500} veces).")
    bien(f"Con deduplicación: saldo ${con} (se pagó 1 vez).")
    print()
    nota("Diferencia con el caso 1: la idempotencia la pide el CLIENTE con una clave en la API; "
         "la deduplicación la hace el CONSUMIDOR de mensajes con el id de cada mensaje. "
         "Las dos usan la misma idea: una PRIMARY KEY que solo deja pasar al primero.")
