"""
Cliente HTTP mínimo (biblioteca estándar) para pegarle a la API desde Python:
lo usan la comprobación con hilos por HTTP (prueba_http.py) y las pruebas.

Hace lo mismo que Postman: arma el pedido (método, ruta, headers, body JSON)
y devuelve (código de estado, body, headers).
"""
import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def pedir(url, metodo, ruta, body=None, clave=None):
    datos = json.dumps(body).encode("utf-8") if body is not None else None
    pedido = urllib.request.Request(url + ruta, data=datos, method=metodo)
    pedido.add_header("Content-Type", "application/json")
    if clave:
        pedido.add_header("Idempotency-Key", clave)
    try:
        with urllib.request.urlopen(pedido, timeout=30) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:   # 4xx y 5xx llegan como excepción en urllib
        return e.code, json.loads(e.read()), dict(e.headers)


def en_paralelo(url, pedidos):
    """pedidos: lista de (metodo, ruta, body, clave). Todos arrancan juntos, cada uno en su hilo."""
    barrera = threading.Barrier(len(pedidos))

    def mandar(p):
        barrera.wait()
        return pedir(url, *p)

    with ThreadPoolExecutor(len(pedidos)) as hilos:
        return list(hilos.map(mandar, pedidos))
