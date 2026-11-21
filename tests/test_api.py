"""
Pruebas de la API HTTP (api.py).  Ejecutar:  python -m pytest -v

Levantan la API en un hilo, en un puerto libre, y le mandan pedidos HTTP de
verdad, igual que Postman. Las de concurrencia mandan los pedidos desde muchos
hilos a la vez.
"""
import os
import sys
import tempfile

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "pruebas.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from api import arrancar_en_segundo_plano  # noqa: E402
from cliente_http import en_paralelo, pedir  # noqa: E402
from db import reiniciar, valor  # noqa: E402


@pytest.fixture(scope="module")
def url():
    servidor, url = arrancar_en_segundo_plano()
    yield url
    servidor.shutdown()


@pytest.fixture(autouse=True)
def base_limpia():
    reiniciar()


def reservas():
    return valor("SELECT COUNT(*) FROM reservas")


def saldo():
    return valor("SELECT saldo FROM conductores WHERE id = 1")


ANA = {"pasajero": "Ana", "conductor_id": 1}
PAGO = {"id_mensaje": "msg-V17", "conductor_id": 1, "monto": 1500}


# ---------------- GET y errores ----------------
def test_get_conductor_existente_y_404(url):
    codigo, body, _ = pedir(url, "GET", "/conductores/1")
    assert codigo == 200 and body["nombre"] == "Carlos" and body["version"] == 0
    codigo, _, _ = pedir(url, "GET", "/conductores/99")
    assert codigo == 404


def test_ruta_inexistente_y_metodo_equivocado(url):
    assert pedir(url, "GET", "/no-existe")[0] == 404
    assert pedir(url, "GET", "/reset")[0] == 405


def test_body_invalido_400(url):
    assert pedir(url, "POST", "/reservas", {"pasajero": "Ana"}, clave="k1")[0] == 400


# ---------------- Reservas: idempotencia + bloqueo optimista ----------------
def test_sin_idempotency_key_400(url):
    codigo, body, _ = pedir(url, "POST", "/reservas", ANA)
    assert codigo == 400 and "Idempotency-Key" in body["error"]
    assert reservas() == 0


def test_reintento_con_la_misma_clave_devuelve_la_misma_respuesta(url):
    c1, b1, h1 = pedir(url, "POST", "/reservas", ANA, clave="k-ana")
    c2, b2, h2 = pedir(url, "POST", "/reservas", ANA, clave="k-ana")
    assert (c1, c2) == (201, 201)
    assert b1["reserva_id"] == b2["reserva_id"]
    assert "Idempotent-Replayed" not in h1 and h2["Idempotent-Replayed"] == "true"
    assert reservas() == 1


def test_misma_clave_con_otros_datos_422(url):
    pedir(url, "POST", "/reservas", ANA, clave="k-ana")
    codigo, _, _ = pedir(url, "POST", "/reservas", {"pasajero": "Ana", "conductor_id": 2}, clave="k-ana")
    assert codigo == 422
    assert reservas() == 1


def test_otro_pasajero_por_el_mismo_conductor_409(url):
    pedir(url, "POST", "/reservas", ANA, clave="k-ana")
    codigo, _, _ = pedir(url, "POST", "/reservas", {"pasajero": "Beto", "conductor_id": 1}, clave="k-beto")
    assert codigo == 409
    assert pedir(url, "GET", "/conductores/1")[1]["version"] == 1


def test_sin_idempotencia_cada_reintento_crea_otra_reserva(url):
    pedir(url, "POST", "/reservas/sin-idempotencia", ANA)
    pedir(url, "POST", "/reservas/sin-idempotencia", ANA)
    assert reservas() == 2


# ---------------- Pagos: deduplicación ----------------
def test_pagos_con_deduplicacion(url):
    _, b1, _ = pedir(url, "POST", "/pagos", PAGO)
    _, b2, _ = pedir(url, "POST", "/pagos", PAGO)
    assert b1["duplicado"] is False and b2["duplicado"] is True
    assert saldo() == 11500


def test_pagos_sin_deduplicacion(url):
    pedir(url, "POST", "/pagos/sin-deduplicacion", PAGO)
    pedir(url, "POST", "/pagos/sin-deduplicacion", PAGO)
    assert saldo() == 13000


# ---------------- Caso 3: acreditar ----------------
def test_acreditar_de_a_uno_da_bien_con_y_sin_control(url):
    pedir(url, "POST", "/conductores/1/acreditar/sin-control", {"monto": 1500})
    codigo, body, _ = pedir(url, "POST", "/conductores/1/acreditar", {"monto": 2000})
    assert codigo == 200 and body["saldo"] == 13500
    assert pedir(url, "POST", "/conductores/99/acreditar", {"monto": 100})[0] == 404
    assert pedir(url, "POST", "/conductores/1/acreditar", {"monto": -5})[0] == 400


# ---------------- Caso 4: asignaciones ----------------
def test_asignaciones_un_exito_y_un_409(url):
    assert pedir(url, "POST", "/asignaciones", ANA)[0] == 201
    assert pedir(url, "POST", "/asignaciones", {"pasajero": "Beto", "conductor_id": 1})[0] == 409
    assert pedir(url, "GET", "/conductores/1")[1]["version"] == 1


# ---------------- Concurrencia por HTTP ----------------
def test_http_50_acreditaciones_atomicas_a_la_vez(url):
    en_paralelo(url, [("POST", "/conductores/1/acreditar", {"monto": 100}, None)] * 50)
    assert saldo() == 15000


def test_http_50_acreditaciones_sin_control_pierden_plata(url):
    en_paralelo(url, [("POST", "/conductores/1/acreditar/sin-control", {"monto": 100}, None)] * 50)
    assert saldo() < 15000


def test_http_20_asignaciones_con_bloqueo_optimista(url):
    pedidos = [("POST", "/asignaciones", {"pasajero": f"P{i}", "conductor_id": 1}, None) for i in range(20)]
    codigos = sorted(c for c, _, _ in en_paralelo(url, pedidos))
    assert codigos == [201] + [409] * 19
    assert reservas() == 1


def test_http_30_reintentos_a_la_vez_una_reserva(url):
    respuestas = en_paralelo(url, [("POST", "/reservas", ANA, "k-ana")] * 30)
    assert reservas() == 1
    assert {b["reserva_id"] for _, b, _ in respuestas} == {1}


def test_http_20_pasajeros_a_la_vez_un_exito_y_19_conflictos(url):
    pedidos = [("POST", "/reservas", {"pasajero": f"P{i}", "conductor_id": 1}, f"k{i}") for i in range(20)]
    codigos = sorted(c for c, _, _ in en_paralelo(url, pedidos))
    assert codigos == [201] + [409] * 19
    assert reservas() == 1


def test_http_10_entregas_a_la_vez_se_paga_una(url):
    en_paralelo(url, [("POST", "/pagos", PAGO, None)] * 10)
    assert saldo() == 11500
