"""
Pruebas automáticas de los 4 casos.  Ejecutar desde la carpeta del proyecto:  python -m pytest -v

Cada caso se prueba de dos formas:
  - con el MISMO orden intercalado que se muestra en la demo (determinista)
  - con hilos reales, sin pausas
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "pruebas.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from caso1_idempotencia import crear_reserva_con_idempotencia, crear_reserva_sin_idempotencia  # noqa: E402
from caso2_deduplicacion import MENSAJE, procesar_con_deduplicacion, procesar_sin_deduplicacion  # noqa: E402
from caso3_condicion_carrera import acreditar_ganancia, acreditar_ganancia_atomica  # noqa: E402
from caso4_control_concurrencia import asignar_con_bloqueo_optimista, asignar_sin_control  # noqa: E402
from db import reiniciar, valor  # noqa: E402
from planificador import con_hilos, intercalar  # noqa: E402


@pytest.fixture(autouse=True)
def base_limpia():
    reiniciar()


def reservas():
    return valor("SELECT COUNT(*) FROM reservas")


def saldo():
    return valor("SELECT saldo FROM conductores WHERE id = 1")


# ---------------- Caso 1 · Idempotencia ----------------
def test_sin_idempotencia_cada_reintento_crea_una_reserva():
    intercalar({i: crear_reserva_sin_idempotencia("Ana", 1) for i in range(3)})
    assert reservas() == 3


def test_con_idempotencia_los_reintentos_reciben_la_misma_respuesta():
    r = intercalar({i: crear_reserva_con_idempotencia("k1", "Ana", 1) for i in range(3)})
    assert reservas() == 1
    assert {x["reserva_id"] for x in r.values()} == {1}
    assert sum(bool(x.get("repetida")) for x in r.values()) == 2


def test_misma_clave_con_otros_datos_se_rechaza():
    intercalar({"a": crear_reserva_con_idempotencia("k1", "Ana", 1)})
    r = intercalar({"b": crear_reserva_con_idempotencia("k1", "Ana", 2)})
    assert r["b"]["codigo"] == 422
    assert reservas() == 1


def test_idempotencia_con_hilos_reales():
    con_hilos([crear_reserva_con_idempotencia("k1", "Ana", 1) for _ in range(30)])
    assert reservas() == 1


# ---------------- Caso 2 · Deduplicación ----------------
def test_sin_deduplicacion_se_paga_dos_veces():
    intercalar({1: procesar_sin_deduplicacion(MENSAJE)})
    intercalar({2: procesar_sin_deduplicacion(MENSAJE)})
    assert saldo() == 13000


def test_con_deduplicacion_se_paga_una_vez():
    intercalar({1: procesar_con_deduplicacion(MENSAJE)})
    r = intercalar({2: procesar_con_deduplicacion(MENSAJE)})
    assert saldo() == 11500
    assert "descartado" in r[2]


def test_deduplicacion_con_hilos_reales():
    con_hilos([procesar_con_deduplicacion(MENSAJE) for _ in range(10)])
    assert saldo() == 11500


# ---------------- Caso 3 · Condición de carrera ----------------
def test_en_serie_no_hay_carrera():
    intercalar({1: acreditar_ganancia(1, 1500), 2: acreditar_ganancia(1, 2000)}, orden=[1] * 4 + [2] * 4)
    assert saldo() == 13500


def test_intercalado_pierde_una_actualizacion():
    intercalar({1: acreditar_ganancia(1, 1500), 2: acreditar_ganancia(1, 2000)}, orden=[1, 2] * 4)
    assert saldo() == 12000


def test_operacion_atomica_con_hilos_reales():
    con_hilos([acreditar_ganancia_atomica(1, 100) for _ in range(50)])
    assert saldo() == 15000


# ---------------- Caso 4 · Control de concurrencia ----------------
def test_sin_control_hay_doble_asignacion():
    intercalar({"a": asignar_sin_control("Ana", 1), "b": asignar_sin_control("Beto", 1)}, orden=["a", "b"] * 4)
    assert reservas() == 2


def test_bloqueo_optimista_un_exito_y_un_conflicto():
    r = intercalar({"a": asignar_con_bloqueo_optimista("Ana", 1), "b": asignar_con_bloqueo_optimista("Beto", 1)},
                   orden=["a", "b"] * 4)
    assert sorted(x["codigo"] for x in r.values()) == [201, 409]
    assert reservas() == 1


def test_bloqueo_optimista_con_hilos_reales():
    r = con_hilos([asignar_con_bloqueo_optimista(f"P{i}", 1) for i in range(20)])
    assert reservas() == 1
    assert sum(x["codigo"] == 409 for x in r) == 19


# ---------------- Caso 5 · Todo junto ----------------
def test_todo_junto_una_reserva_y_respuestas_coherentes():
    from caso5_todo_junto import reservar
    r = intercalar({
        "a1": reservar("k-ana", "Ana", 1), "a2": reservar("k-ana", "Ana", 1),
        "b1": reservar("k-beto", "Beto", 1), "b2": reservar("k-beto", "Beto", 1),
    })
    assert reservas() == 1
    assert r["a1"]["codigo"] == r["a2"]["codigo"]
    assert r["b1"]["codigo"] == r["b2"]["codigo"]
    assert sorted([r["a1"]["codigo"], r["b1"]["codigo"]]) == [201, 409]


def test_todo_junto_con_hilos_reales():
    from caso5_todo_junto import reservar
    pedidos = [(i, reservar(f"k{i}", f"P{i}", 1)) for i in range(5) for _ in range(3)]
    respuestas = con_hilos([g for _, g in pedidos])
    assert reservas() == 1
    por_pasajero = {}
    for (i, _), x in zip(pedidos, respuestas):
        por_pasajero.setdefault(i, set()).add(x["codigo"])
    assert all(len(c) == 1 for c in por_pasajero.values())
