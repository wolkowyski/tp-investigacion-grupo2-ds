"""
Cómo se ejecutan los pedidos en la demo.

Cada pedido está escrito como una FUNCIÓN GENERADORA: en cada `yield` el pedido
hace una pausa y nos cuenta qué acaba de hacer. Eso nos permite:

  1) paso_a_paso(): elegir el ORDEN en que avanzan los pedidos, de a un paso
     por cada Enter, para ver exactamente cómo se intercalan cuando llegan
     "al mismo tiempo". Las operaciones contra la base de datos son reales;
     lo único que controlamos es el orden, como en un depurador.

  2) con_hilos(): correr los mismos pedidos en hilos de verdad, todos a la vez
     y sin pausas, para comprobar que el problema también aparece solo.

Cada `yield` marca un punto donde, en un sistema real, otro pedido podría
meterse en el medio.
"""
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from consola import LineaDeTiempo, pausa


def intercalar(pedidos, orden=None, antes=None, despues=None):
    """
    pedidos: {nombre: generador}
    orden:   lista de nombres; cada elemento = un paso de ese pedido.
             Si se termina y quedan pedidos sin terminar, siguen por turnos.
    Devuelve {nombre: valor que devolvió el pedido (su "respuesta")}.
    """
    pendientes = dict(pedidos)
    resultados = {}

    def turnos():
        yield from (orden or [])
        while pendientes:
            yield from list(pendientes)

    numero = 0
    for nombre in turnos():
        if nombre not in pendientes:
            continue
        numero += 1
        if antes:
            antes(numero, nombre)
        try:
            texto, final = next(pendientes[nombre]), False
        except StopIteration as fin:
            texto, final = fin.value, True
            resultados[nombre] = fin.value
            del pendientes[nombre]
        if despues:
            despues(numero, nombre, texto, final)
    return resultados


def paso_a_paso(pedidos, colores, orden=None, formato=str):
    """Igual que intercalar(), pero con un Enter antes de cada paso y la línea de tiempo en pantalla."""
    linea = LineaDeTiempo(list(pedidos), colores)
    linea.encabezado()
    return intercalar(
        pedidos,
        orden,
        antes=lambda n, nombre: pausa(f"Enter → paso {n}: avanza «{nombre}»"),
        despues=lambda n, nombre, texto, final: linea.paso(n, nombre, f"→ {formato(texto)}" if final else texto, final),
    )


def con_hilos(generadores, latencia=0.01, escalonado=0.0):
    """Corre cada generador en su propio hilo, todos arrancando a la vez y sin pausas.
    escalonado: demora al azar al arrancar (para que no lleguen todos en el mismo instante)."""
    barrera = threading.Barrier(len(generadores))

    def correr(gen):
        barrera.wait()  # todos esperan acá y arrancan juntos
        time.sleep(random.uniform(0, escalonado))
        while True:
            try:
                next(gen)
                time.sleep(random.uniform(0, latencia))  # latencia de red / procesamiento
            except StopIteration as fin:
                return fin.value

    with ThreadPoolExecutor(len(generadores)) as hilos:
        return list(hilos.map(correr, generadores))
