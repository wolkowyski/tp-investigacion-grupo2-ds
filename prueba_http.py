"""
Comprobación con hilos reales, pero POR HTTP: muchos clientes le pegan a la API
al mismo tiempo, como muchas apps a la vez.

Postman manda los pedidos de a uno (también el Collection Runner), así que sirve
para ver reintentos y códigos de estado, pero no para mostrar concurrencia.
Para eso está este script.

Ejecutar (con la API corriendo en otra terminal: py api.py):
    py prueba_http.py           los 5 casos
    py prueba_http.py 3         solo el caso 3
    py prueba_http.py 3 http://127.0.0.1:6000     contra la API en otro puerto
Si no encuentra la API, levanta una propia en segundo plano.
"""
import sys
import urllib.error

from cliente_http import en_paralelo, pedir
from consola import bien, color, mal, nota, seccion, titulo

ANA = {"pasajero": "Ana", "conductor_id": 1}
PAGO = {"id_mensaje": "msg-V17", "conductor_id": 1, "monto": 1500}


def conectar_api(url):
    try:
        pedir(url, "GET", "/estado")   # /estado no se registra en la API
        print(color(f"  Usando la API que está corriendo en {url}", "gris"))
        return url
    except (urllib.error.URLError, ConnectionError, OSError):
        from api import arrancar_en_segundo_plano
        _, url = arrancar_en_segundo_plano()
        print(color(f"  No había una API corriendo: levanté una en {url}", "gris"))
        return url


def reiniciar(url):
    pedir(url, "POST", "/reset", carga=True)


def reservas(url):
    return len(pedir(url, "GET", "/reservas", carga=True)[1])


def saldo(url):
    return pedir(url, "GET", "/conductores/1", carga=True)[1]["saldo"]


def pasajeros(n):
    return [{"pasajero": f"P{i}", "conductor_id": 1} for i in range(n)]


# ==========================================================================
# Un bloque por caso: primero SIN el concepto y después CON el concepto
# ==========================================================================

def caso1(url):
    seccion("Caso 1 · Idempotencia: 30 reintentos de Ana a la vez", "azul")
    reiniciar(url)
    en_paralelo(url, [("POST", "/reservas/sin-idempotencia", ANA, None)] * 30)
    mal(f"A) POST /reservas/sin-idempotencia: {reservas(url)} reservas.")
    reiniciar(url)
    respuestas = en_paralelo(url, [("POST", "/reservas", ANA, "ana-viaje-1")] * 30)
    repetidas = sum(h.get("Idempotent-Replayed") == "true" for _, _, h in respuestas)
    bien(f"B) POST /reservas con Idempotency-Key: {reservas(url)} reserva; "
         f"1 respuesta original y {repetidas} repetidas (header Idempotent-Replayed).")


def caso2(url):
    seccion("Caso 2 · Deduplicación: el mismo mensaje msg-V17 entregado 10 veces a la vez", "azul")
    reiniciar(url)
    en_paralelo(url, [("POST", "/pagos/sin-deduplicacion", PAGO, None)] * 10)
    s = saldo(url)
    mal(f"A) POST /pagos/sin-deduplicacion: saldo ${s} (se pagó {(s - 10000) // 1500} veces).")
    reiniciar(url)
    en_paralelo(url, [("POST", "/pagos", PAGO, None)] * 10)
    bien(f"B) POST /pagos: saldo ${saldo(url)} (se pagó 1 vez).")


def caso3(url):
    seccion("Caso 3 · Condición de carrera: 50 acreditaciones de $100 a la vez (esperado $15000)", "naranja")
    for corrida in (1, 2):
        reiniciar(url)
        en_paralelo(url, [("POST", "/conductores/1/acreditar/sin-control", {"monto": 100}, None)] * 50)
        s = saldo(url)
        mal(f"A) leer → calcular → escribir, corrida {corrida}: saldo ${s} (se perdieron ${15000 - s}).")
    reiniciar(url)
    en_paralelo(url, [("POST", "/conductores/1/acreditar", {"monto": 100}, None)] * 50)
    bien(f"B) operación atómica (saldo = saldo + ?): saldo ${saldo(url)}.")
    nota("Cada corrida sin control da distinto: la carrera no es determinista.")


def caso4(url):
    seccion("Caso 4 · Control de concurrencia: 20 pasajeros piden a Carlos a la vez", "naranja")
    reiniciar(url)
    codigos = [c for c, _, _ in en_paralelo(url, [("POST", "/asignaciones/sin-control", p, None) for p in pasajeros(20)])]
    mal(f"A) POST /asignaciones/sin-control: {codigos.count(201)} × 201, Carlos quedó con {reservas(url)} reservas.")
    reiniciar(url)
    codigos = [c for c, _, _ in en_paralelo(url, [("POST", "/asignaciones", p, None) for p in pasajeros(20)])]
    bien(f"B) POST /asignaciones (bloqueo optimista): {codigos.count(201)} × 201 Created y "
         f"{codigos.count(409)} × 409 Conflict; {reservas(url)} reserva.")


def caso5(url):
    seccion("Caso 5 · Todo junto: 5 pasajeros × 3 reintentos, todos a la vez", "verde")
    pedidos = [("POST", "/reservas", p, f"p{i}-viaje") for i, p in enumerate(pasajeros(5)) for _ in range(3)]
    reiniciar(url)
    en_paralelo(url, [("POST", "/reservas/sin-idempotencia", p, None) for _, _, p, _ in pedidos])
    mal(f"A) sin ningún mecanismo: Carlos quedó con {reservas(url)} reservas.")
    reiniciar(url)
    respuestas = en_paralelo(url, pedidos)
    por_pasajero = {}
    for (_, _, _, clave), (codigo, _, _) in zip(pedidos, respuestas):
        por_pasajero.setdefault(clave, set()).add(codigo)
    coherentes = sum(len(c) == 1 for c in por_pasajero.values())
    bien(f"B) idempotencia + bloqueo optimista: {reservas(url)} reserva, y {coherentes} de 5 pasajeros "
         "recibieron siempre la misma respuesta en sus 3 intentos.")


CASOS = {"1": caso1, "2": caso2, "3": caso3, "4": caso4, "5": caso5}


def main():
    argumentos = sys.argv[1:]
    url = next((a.rstrip("/") for a in argumentos if a.startswith("http")), "http://127.0.0.1:5050")
    elegidos = [a for a in argumentos if a in CASOS] or list(CASOS)

    titulo("Comprobación con hilos reales por HTTP", "cian")
    url = conectar_api(url)
    for c in elegidos:
        CASOS[c](url)
    reiniciar(url)
    print()
    nota("Son pedidos HTTP de verdad, todos a la vez y sin controlar el orden: el resultado es el mismo "
         "que en la terminal, porque los endpoints llaman a las mismas funciones de los casos.")


if __name__ == "__main__":
    main()
