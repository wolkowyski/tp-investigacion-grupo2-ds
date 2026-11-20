"""
Comprobación con hilos reales, pero POR HTTP: muchos clientes le pegan a la API
al mismo tiempo, como muchas apps a la vez.

Postman manda los pedidos de a uno (también el Collection Runner), así que sirve
para ver reintentos y códigos de estado, pero no para mostrar concurrencia.
Para eso está este script.

Ejecutar (con la API corriendo en otra terminal: python api.py):
    python prueba_http.py
    python prueba_http.py http://127.0.0.1:6000
Si no encuentra la API, levanta una propia en segundo plano.
"""
import sys
import urllib.error

from cliente_http import en_paralelo, pedir
from consola import bien, color, mal, nota, seccion, titulo


def conectar_api():
    url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:5050"
    try:
        pedir(url, "GET", "/")
        print(color(f"  Usando la API que está corriendo en {url}", "gris"))
        return url
    except (urllib.error.URLError, ConnectionError, OSError):
        from api import arrancar_en_segundo_plano
        _, url = arrancar_en_segundo_plano()
        print(color(f"  No había una API corriendo: levanté una en {url}", "gris"))
        return url


def contar_reservas(url):
    return len(pedir(url, "GET", "/reservas")[1])


def saldo_carlos(url):
    return pedir(url, "GET", "/conductores/1")[1]["saldo"]


def main():
    titulo("Comprobación con hilos reales por HTTP", "cian")
    url = conectar_api()
    ana = {"pasajero": "Ana", "conductor_id": 1}
    pago = {"id_mensaje": "msg-V17", "conductor_id": 1, "monto": 1500}

    seccion("Caso 1 · 30 reintentos de Ana a la vez (misma intención)", "azul")
    pedir(url, "POST", "/reset")
    en_paralelo(url, [("POST", "/reservas/sin-idempotencia", ana, None)] * 30)
    mal(f"POST /reservas/sin-idempotencia: {contar_reservas(url)} reservas.")
    pedir(url, "POST", "/reset")
    respuestas = en_paralelo(url, [("POST", "/reservas", ana, "ana-viaje-1")] * 30)
    repetidas = sum(h.get("Idempotent-Replayed") == "true" for _, _, h in respuestas)
    bien(f"POST /reservas con Idempotency-Key: {contar_reservas(url)} reserva; "
         f"1 respuesta original y {repetidas} repetidas (header Idempotent-Replayed).")

    seccion("Caso 4/5 · 20 pasajeros piden a Carlos a la vez (intenciones distintas)", "naranja")
    pedidos = [("POST", "/reservas", {"pasajero": f"P{i}", "conductor_id": 1}, f"p{i}-viaje") for i in range(20)]
    pedir(url, "POST", "/reset")
    en_paralelo(url, [("POST", "/reservas/sin-idempotencia", p[2], None) for p in pedidos])
    mal(f"Sin control: Carlos quedó con {contar_reservas(url)} reservas.")
    pedir(url, "POST", "/reset")
    codigos = [c for c, _, _ in en_paralelo(url, pedidos)]
    bien(f"Con bloqueo optimista: {codigos.count(201)} × 201 Created y {codigos.count(409)} × 409 Conflict; "
         f"{contar_reservas(url)} reserva.")

    seccion("Caso 2 · el mismo mensaje msg-V17 entregado 10 veces a la vez", "azul")
    pedir(url, "POST", "/reset")
    en_paralelo(url, [("POST", "/pagos/sin-deduplicacion", pago, None)] * 10)
    mal(f"POST /pagos/sin-deduplicacion: saldo ${saldo_carlos(url)} (se pagó {(saldo_carlos(url) - 10000) // 1500} veces).")
    pedir(url, "POST", "/reset")
    en_paralelo(url, [("POST", "/pagos", pago, None)] * 10)
    bien(f"POST /pagos con deduplicación: saldo ${saldo_carlos(url)} (se pagó 1 vez).")

    pedir(url, "POST", "/reset")
    print()
    nota("Son pedidos HTTP de verdad, todos a la vez y sin controlar el orden: el resultado es el mismo "
         "que en la terminal, porque los endpoints llaman a las mismas funciones de los casos.")


if __name__ == "__main__":
    main()
