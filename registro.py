"""
Registro de la API: qué pasó en cada pedido HTTP, de punta a punta.

Por cada pedido arma un bloque con las cuatro etapas del recorrido
cliente-servidor, siguiendo las capas de una aplicación de tres capas:

  ① PEDIDO        cliente → servidor      la línea de pedido, los headers y el body JSON
  ② LÓGICA        capa de aplicación      la función del caso que se ejecutó, sus pasos
                                          (los mismos `yield` que se ven en main.py) y
                                          cada sentencia SQL real que mandó a SQLite
  ③ BASE DE DATOS capa de datos           qué filas cambiaron (INSERT / UPDATE / DELETE)
  ④ RESPUESTA     servidor → cliente      la línea de estado, los headers y el body JSON

El SQL lo informa el propio SQLite (db.observador_sql), con los valores reales.
Los cambios de la base salen de comparar las tablas antes y después del pedido.

También guarda los últimos pedidos para el panel del navegador (/panel).
No tiene lógica de los temas: es solo presentación, como consola.py.
"""
import json
import os
import shutil
import textwrap
import threading
import time
from collections import deque

import db
from consola import color

# --------------------------------------------------------------------------
# Captura de lo que pasa DENTRO de un pedido (cada pedido corre en su hilo)
# --------------------------------------------------------------------------

_hilo = threading.local()


def iniciar_captura():
    _hilo.eventos = []


def terminar_captura():
    eventos = getattr(_hilo, "eventos", None) or []
    _hilo.eventos = None
    return eventos


def _anotar(tipo, *datos):
    eventos = getattr(_hilo, "eventos", None)
    if eventos is not None:
        eventos.append([tipo, *datos])


def anotar_funcion(nombre, archivo):
    _anotar("funcion", nombre, archivo)


def anotar_paso(texto):
    _anotar("paso", str(texto))


def anotar_sql(tipo, texto):
    """tipo: "sql" (la sentencia), "filas" (cuántas tocó) o "error" (por qué falló)."""
    _anotar(tipo, " ".join(texto.split()) if tipo == "sql" else texto)


db.observador_sql = anotar_sql   # SQLite nos avisa cada sentencia que ejecuta y su resultado


# --------------------------------------------------------------------------
# La base antes y después: qué filas cambiaron
# --------------------------------------------------------------------------

def foto():
    """Todas las filas de todas las tablas (son pocas)."""
    con = db.conectar()
    try:
        return {t: [dict(f) for f in con.execute(f"SELECT * FROM {t}")] for t in db.TABLAS}
    finally:
        con.close()


def cambios(antes, despues):
    """Compara dos fotos por clave primaria (la primera columna de cada tabla)."""
    resultado = []
    for tabla in db.TABLAS:
        filas_antes = {next(iter(f.values())): f for f in antes.get(tabla, [])}
        filas_despues = {next(iter(f.values())): f for f in despues.get(tabla, [])}
        columna_pk = next(iter((despues.get(tabla) or antes.get(tabla) or [{"id": 0}])[0]))
        for clave, fila in filas_despues.items():
            if clave not in filas_antes:
                resultado.append({"tabla": tabla, "tipo": "INSERT", "pk": columna_pk, "clave": clave, "fila": fila})
            elif fila != filas_antes[clave]:
                distintas = {c: [filas_antes[clave].get(c), v] for c, v in fila.items() if filas_antes[clave].get(c) != v}
                resultado.append({"tabla": tabla, "tipo": "UPDATE", "pk": columna_pk, "clave": clave,
                                  "columnas": distintas, "fila": fila})
        for clave, fila in filas_antes.items():
            if clave not in filas_despues:
                resultado.append({"tabla": tabla, "tipo": "DELETE", "pk": columna_pk, "clave": clave, "fila": fila})
    return resultado


# --------------------------------------------------------------------------
# Historial (para el panel) y numeración de pedidos
# --------------------------------------------------------------------------

_cerrojo = threading.Lock()
_historial = deque(maxlen=60)
_contador = 0


def nuevo_numero():
    global _contador
    with _cerrojo:
        _contador += 1
        return _contador


def guardar(pedido):
    with _cerrojo:
        _historial.appendleft(pedido)


def historial():
    with _cerrojo:
        return list(_historial), _contador


def estado_de_la_base():
    """Esquema y filas de cada tabla, leídos de la base real con PRAGMA y SELECT."""
    con = db.conectar()
    try:
        tablas = []
        for t in db.TABLAS:
            columnas = [{"nombre": c["name"], "tipo": c["type"] or "", "pk": bool(c["pk"])}
                        for c in con.execute(f"PRAGMA table_info({t})")]
            filas = [dict(f) for f in con.execute(f"SELECT * FROM {t}")]
            tablas.append({"nombre": t, "sql": f"SELECT * FROM {t}", "columnas": columnas, "filas": filas})
        return tablas
    finally:
        con.close()


# --------------------------------------------------------------------------
# Impresión en la terminal de la API
# --------------------------------------------------------------------------

_imprimir = threading.Lock()   # que los bloques de dos pedidos no se mezclen

HEADERS_IMPORTANTES = {"content-type", "content-length", "idempotency-key", "idempotent-replayed", "if-match"}


def _ancho():
    return max(50, min(shutil.get_terminal_size((100, 30)).columns, 130))


def _color_codigo(codigo):
    return "verde" if codigo < 300 else "amarillo" if codigo < 500 else "rojo"


def _json_lindo(texto, maximo=16):
    if not texto:
        return []
    try:
        lineas = json.dumps(json.loads(texto), ensure_ascii=False, indent=2).splitlines()
    except (ValueError, TypeError):
        lineas = str(texto).splitlines()
    if len(lineas) > maximo:
        lineas = lineas[:maximo] + [f"… ({len(lineas) - maximo} líneas más)"]
    return lineas


def _valor(v):
    return f"'{v}'" if isinstance(v, str) else ("NULL" if v is None else str(v))


def texto_cambio(c):
    if c["tipo"] == "UPDATE":
        return ", ".join(f"{col}: {_valor(a)} → {_valor(d)}" for col, (a, d) in c["columnas"].items())
    return " ".join(f"{col}={_valor(v)}" for col, v in c["fila"].items())


def imprimir(p):
    """Imprime el bloque completo de un pedido (o una línea, si es de la prueba con hilos)."""
    codigo_txt = f"{p['codigo']} {p['frase']}"
    col_codigo = _color_codigo(p["codigo"])

    if p["carga"]:
        with _imprimir:
            print(f"  {color('⇉', 'gris')} #{p['numero']:<4} {p['metodo']:<4} {p['ruta']:<38} → "
                  f"{color(codigo_txt, col_codigo)} {color('(prueba con hilos)', 'gris')}", flush=True)
        return

    w = _ancho()
    salida = []
    barra = color("│", "gris")

    def linea(texto="", col=None, sangria=3, *estilos):
        ancho_util = w - sangria - 3
        partes = textwrap.wrap(texto, ancho_util, subsequent_indent="    ") if texto else [""]
        for parte in partes:
            salida.append(f"{barra}{' ' * sangria}{color(parte, col, *estilos) if col else parte}")

    def titulo(numero, nombre, detalle, col):
        salida.append(barra)
        salida.append(f"{barra} {color(numero + ' ' + nombre, col, 'negrita')}  {color(detalle, 'gris')}")

    encabezado = f"┌─ #{p['numero']} · {p['hora']} · {p['metodo']} {p['ruta']} → "
    resto = max(0, w - len(encabezado) - len(codigo_txt) - 2)
    salida.append(color(encabezado, "gris") + color(codigo_txt, col_codigo, "negrita") + " " + color("─" * resto, "gris"))

    # ① PEDIDO
    titulo("①", "PEDIDO", "cliente → servidor · capa de presentación (Postman)", "cian")
    linea(f"{p['metodo']} {p['ruta_completa']} {p['version']}", "cian", 3, "negrita")
    for nombre, valor in p["headers_pedido"]:
        importante = nombre.lower() in HEADERS_IMPORTANTES
        if nombre.lower() == "idempotency-key":
            linea(f"{nombre}: {valor}", "cian", 3, "negrita")
        else:
            linea(f"{nombre}: {valor}", None if importante else "gris")
    if p["body_pedido"]:
        linea()
        for l in _json_lindo(p["body_pedido"]):
            linea(l, "amarillo")

    # ② LÓGICA
    funcion = next((e for e in p["eventos"] if e[0] == "funcion"), None)
    detalle = (f"capa de aplicación · {funcion[1]}() en {funcion[2]}" if funcion
               else "capa de aplicación · api.py (no llegó a una función de los casos)")
    titulo("②", "LÓGICA", detalle, "violeta")
    if p["ruta"] == "/reset":
        linea("db.reiniciar(): DROP TABLE + CREATE TABLE de las 5 tablas, e INSERT de Carlos y Diana", "gris")
    elif not p["eventos"]:
        linea("sin pasos ni SQL", "gris")
    eventos = [] if p["ruta"] == "/reset" else p["eventos"]
    if eventos and eventos[0][0] != "funcion":
        linea("api.py valida el pedido:", "gris")
    for tipo, *datos in eventos:
        if tipo == "funcion":
            linea(f"→ llama a {datos[0]}()  [{datos[1]}]", "violeta", 3, "negrita")
        elif tipo == "paso":
            linea(f"· {datos[0]}", None, 3)
        elif tipo == "sql":
            for i, parte in enumerate(textwrap.wrap(datos[0], w - 14, subsequent_indent="  ") or [""]):
                prefijo = color("SQL› ", "gris") if i == 0 else "     "
                salida.append(f"{barra}   {prefijo}{color(parte, 'naranja')}")
        elif tipo == "filas":
            n = datos[0]
            salida.append(f"{barra}        {color(f'↳ {n} fila' + ('' if n == 1 else 's'), 'gris' if n else 'amarillo', *(() if n else ('negrita',)))}")
        elif tipo == "error":
            linea(f"   ↳ ✘ {datos[0]}", "rojo", 5, "negrita")
    if p.get("error"):
        linea(f"✘ {p['error']}", col_codigo, 3, "negrita")

    # ③ BASE DE DATOS
    titulo("③", "BASE DE DATOS", f"capa de datos · {os.path.basename(db.RUTA)} (SQLite)", "amarillo")
    if p["ruta"] == "/reset":
        linea("todas las tablas vuelven al estado inicial", "amarillo")
    elif not p["cambios"]:
        linea("sin cambios" + ("  (GET es seguro: solo lee, no modifica el estado)" if p["metodo"] == "GET" else ""), "gris")
    else:
        ancho_tabla = max(len(c["tabla"]) for c in p["cambios"])
        for c in p["cambios"]:
            col = {"INSERT": "verde", "UPDATE": "amarillo", "DELETE": "rojo"}[c["tipo"]]
            cabeza = f"{c['tabla']:<{ancho_tabla}}  "
            donde = f"  ({c['pk']} = {_valor(c['clave'])})"
            salida.append(f"{barra}   {color(cabeza, 'negrita')}{color(c['tipo'], col, 'negrita')}{color(donde, 'gris')}")
            linea(texto_cambio(c), col, 5)

    # ④ RESPUESTA
    titulo("④", "RESPUESTA", "servidor → cliente", col_codigo)
    linea(f"{p['version']} {codigo_txt}", col_codigo, 3, "negrita")
    for nombre, valor in p["headers_respuesta"]:
        if nombre.lower() == "idempotent-replayed":
            linea(f"{nombre}: {valor}", "cian", 3, "negrita")
        else:
            linea(f"{nombre}: {valor}", None if nombre.lower() in HEADERS_IMPORTANTES else "gris")
    linea()
    for l in _json_lindo(p["body_respuesta"]):
        linea(l, col_codigo)
    salida.append(color("└" + "─" * (w - 2), "gris"))

    with _imprimir:
        print("\n".join(salida), flush=True)
        print(flush=True)


def ahora():
    return time.strftime("%H:%M:%S")
