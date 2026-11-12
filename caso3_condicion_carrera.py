"""
CASO 3 · CONDICIÓN DE CARRERA (Tema 10)

Pregunta guía (1ra parte): ¿cómo se producen las condiciones de carrera al
modificar un recurso compartido?

Escenario: Carlos tiene $10000 y termina dos viajes casi al mismo tiempo:
uno de $1500 y otro de $2000. Cada acreditación hace LEER → CALCULAR → ESCRIBIR.
El saldo correcto al final es $13500.
"""
from consola import bien, codigo, mal, nota, parrafo, pausa, seccion, tabla, titulo
from db import conectar, filas, reiniciar, saldo_de, valor
from planificador import con_hilos, paso_a_paso


# ==========================================================================
# LA LÓGICA (lo que se explica en la exposición)
# ==========================================================================

def acreditar_ganancia(conductor_id, monto):
    con = conectar()

    saldo = saldo_de(con, conductor_id)
    yield f"LEE el saldo de Carlos: ${saldo}"

    nuevo = saldo + monto
    yield f"CALCULA ${saldo} + ${monto} = ${nuevo}"

    con.execute("UPDATE conductores SET saldo = ? WHERE id = ?",
                (nuevo, conductor_id))
    yield f"ESCRIBE saldo = ${nuevo}"

    return nuevo


def acreditar_ganancia_atomica(conductor_id, monto):
    """Versión corregida: la base lee y escribe en UNA sola operación."""
    con = conectar()
    con.execute("UPDATE conductores SET saldo = saldo + ? "
                "WHERE id = ?", (monto, conductor_id))
    yield f"UPDATE saldo = saldo + {monto} (en un solo paso)"
    return saldo_de(con, conductor_id)


# ==========================================================================
# LA DEMO (solo presentación)
# ==========================================================================

V1, V2 = "Viaje 1 · +$1500", "Viaje 2 · +$2000"
COLORES = ["naranja", "amarillo"]


def _saldo():
    return valor("SELECT saldo FROM conductores WHERE id = 1")


def demo():
    reiniciar()
    titulo("CASO 3 · CONDICIÓN DE CARRERA  ·  Tema 10", "naranja")
    parrafo("Pregunta guía: ¿cómo se producen las condiciones de carrera al modificar un recurso compartido?", col="naranja")
    parrafo("Hay condición de carrera cuando el resultado depende del ORDEN en que se intercalan "
            "dos operaciones sobre un dato compartido. Hacen falta tres cosas a la vez: "
            "un dato compartido, acceso concurrente y al menos una escritura.")
    parrafo("Escenario: Carlos tiene $10000 y termina dos viajes casi al mismo tiempo, uno de $1500 "
            "y otro de $2000. Cada acreditación hace LEER → CALCULAR → ESCRIBIR. "
            "El saldo correcto al final es $13500.")
    pausa("Enter para ver el caso SIN condición de carrera")

    # ---------------------------------------------------------------- A
    seccion("A)  SIN condición de carrera: uno después del otro", "verde")
    parrafo("Si las acreditaciones no se pisan en el tiempo, el segundo lee el saldo que dejó el primero.")
    paso_a_paso({V1: acreditar_ganancia(1, 1500), V2: acreditar_ganancia(1, 2000)}, COLORES,
                orden=[V1, V1, V1, V1, V2, V2, V2, V2], formato=lambda s: f"terminó (saldo ${s})")
    print()
    tabla("tabla conductores", filas("SELECT nombre, saldo FROM conductores WHERE id = 1"), ["nombre", "saldo"])
    bien(f"Saldo final ${_saldo()}: correcto.")
    print()
    pausa("Enter para ver el caso CON condición de carrera")

    # ---------------------------------------------------------------- B
    reiniciar()
    seccion("B)  CON condición de carrera: los dos al mismo tiempo", "rojo")
    parrafo("Ahora las dos acreditaciones se intercalan: las dos LEEN antes de que la otra ESCRIBA.")
    paso_a_paso({V1: acreditar_ganancia(1, 1500), V2: acreditar_ganancia(1, 2000)}, COLORES,
                orden=[V1, V2, V1, V2, V1, V2, V1, V2], formato=lambda s: f"terminó (saldo ${s})")
    print()
    tabla("tabla conductores", filas("SELECT nombre, saldo FROM conductores WHERE id = 1"), ["nombre", "saldo"])
    mal(f"Saldo final ${_saldo()} en vez de $13500: se perdieron ${13500 - _saldo()}.")
    nota("Es una ACTUALIZACIÓN PERDIDA: el viaje 2 calculó con un saldo viejo y su escritura pisó la del viaje 1. "
         "El código es el mismo que en A; lo único que cambió es el orden.")
    print()
    pausa("Enter: comprobación con hilos reales (sin pausas)")

    # ---------------------------------------------------------------- comprobación
    seccion("Comprobación con hilos reales: 50 viajes de $100 terminan a la vez", "cian")
    for intento in (1, 2):
        reiniciar()
        con_hilos([acreditar_ganancia(1, 100) for _ in range(50)], latencia=0.01, escalonado=0.15)
        mal(f"Corrida {intento}: saldo ${_saldo()} (esperado $15000, se perdieron ${15000 - _saldo()}).")
    nota("El resultado depende de cómo se intercalaron los hilos, así que puede cambiar de una corrida a otra: "
         "las condiciones de carrera no son deterministas. Por eso casi nunca aparecen en una prueba simple y sí bajo carga.")
    print()
    pausa("Enter: ¿cómo se evita?")

    seccion("¿Cómo se evita?", "verde")
    parrafo("Haciendo que leer y escribir no se puedan separar: con control de concurrencia (caso 4). "
            "En este caso alcanza con que la base haga la suma en una sola operación atómica:")
    codigo(["UPDATE conductores SET saldo = saldo + ? WHERE id = ?"])
    reiniciar()
    con_hilos([acreditar_ganancia_atomica(1, 100) for _ in range(50)])
    bien(f"Con la operación atómica y 50 hilos: saldo ${_saldo()}.")
