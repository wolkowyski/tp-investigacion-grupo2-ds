"""
API HTTP de la demo · Grupo 2

Los mismos casos de la terminal, pero como endpoints HTTP de verdad, para
probarlos con Postman (o curl) y ver los métodos, headers, bodies JSON y
códigos de estado reales: 200, 201, 400, 404, 409, 422.

No hay lógica nueva: cada endpoint llama a la MISMA función del caso
correspondiente (reservar() del caso 5, procesar_con_deduplicacion() del
caso 2, ...). Solo se agrega lo propio de HTTP: leer el pedido, validar y
traducir el resultado a un código de estado.

Usa solo la biblioteca estándar de Python (http.server): no hay que instalar nada.

Ejecutar:
    python api.py               escucha en http://127.0.0.1:5050
    PORT=6000 python api.py     en otro puerto (en PowerShell: $env:PORT=6000; python api.py)

Endpoints, por caso (A = sin el concepto, B = con el concepto):
    Caso 1   A  POST /reservas/sin-idempotencia            crear_reserva_sin_idempotencia()
             B  POST /reservas  + header Idempotency-Key   reservar()  (la idempotencia del caso 1
                                                            + el bloqueo optimista del caso 4)
    Caso 2   A  POST /pagos/sin-deduplicacion              procesar_sin_deduplicacion()
             B  POST /pagos                                procesar_con_deduplicacion()
    Caso 3   A  POST /conductores/{id}/acreditar/sin-control   acreditar_ganancia()
             B  POST /conductores/{id}/acreditar           acreditar_ganancia_atomica()
    Caso 4   A  POST /asignaciones/sin-control             asignar_sin_control()
             B  POST /asignaciones                         asignar_con_bloqueo_optimista()
    Caso 5      POST /reservas  + header Idempotency-Key   reservar()

    Consultas:  GET /conductores, GET /conductores/{id}, GET /reservas, GET /reservas/{id}
    POST /reset                                            deja la base como al principio
"""
import json
import os
import re
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# La API usa su propia base (api.db), para que correr main.py al mismo tiempo
# no le borre los datos. Tiene que ir ANTES de importar db y los casos.
os.environ.setdefault("DB_PATH", "api.db")

from caso1_idempotencia import crear_reserva_sin_idempotencia
from caso2_deduplicacion import procesar_con_deduplicacion, procesar_sin_deduplicacion
from caso3_condicion_carrera import acreditar_ganancia, acreditar_ganancia_atomica
from caso4_control_concurrencia import asignar_con_bloqueo_optimista, asignar_sin_control
from caso5_todo_junto import reservar
import registro
from consola import color
from db import conectar, reiniciar

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5050"))


# ==========================================================================
# Ejecutar un pedido
# ==========================================================================

def ejecutar(pedido):
    """Corre una función generadora de los casos hasta el final, sin pausas,
    y devuelve lo que retorna. En la terminal los `yield` servían para pausar
    con Enter; acá el pedido avanza solo, como en un servidor real.
    Cada texto de un `yield` se anota en el registro: son los mismos pasos que en main.py."""
    registro.anotar_funcion(pedido.__name__, os.path.basename(pedido.gi_code.co_filename))
    while True:
        try:
            registro.anotar_paso(next(pedido))
        except StopIteration as fin:
            return fin.value


def fila(sql, *parametros):
    con = conectar()
    try:
        r = con.execute(sql, parametros).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def todas(sql, *parametros):
    con = conectar()
    try:
        return [dict(r) for r in con.execute(sql, parametros).fetchall()]
    finally:
        con.close()


class ErrorHTTP(Exception):
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


# ==========================================================================
# Validación del pedido
# ==========================================================================

def datos_de_reserva(body):
    pasajero = body.get("pasajero")
    conductor_id = body.get("conductor_id")
    if not isinstance(pasajero, str) or not pasajero.strip():
        raise ErrorHTTP(400, "falta 'pasajero' (texto)")
    if not isinstance(conductor_id, int) or isinstance(conductor_id, bool):
        raise ErrorHTTP(400, "falta 'conductor_id' (número)")
    if not fila("SELECT id FROM conductores WHERE id = ?", conductor_id):
        raise ErrorHTTP(404, f"no existe el conductor {conductor_id}")
    return pasajero.strip(), conductor_id


def datos_de_mensaje(body):
    mensaje = {"id": body.get("id_mensaje"), "conductor_id": body.get("conductor_id"), "monto": body.get("monto")}
    if not isinstance(mensaje["id"], str) or not mensaje["id"].strip():
        raise ErrorHTTP(400, "falta 'id_mensaje' (texto)")
    if not isinstance(mensaje["monto"], int) or mensaje["monto"] <= 0:
        raise ErrorHTTP(400, "falta 'monto' (número mayor a 0)")
    if not isinstance(mensaje["conductor_id"], int) or isinstance(mensaje["conductor_id"], bool):
        raise ErrorHTTP(400, "falta 'conductor_id' (número)")
    if not fila("SELECT id FROM conductores WHERE id = ?", mensaje["conductor_id"]):
        raise ErrorHTTP(404, f"no existe el conductor {mensaje['conductor_id']}")
    return mensaje


# ==========================================================================
# Los endpoints: cada uno devuelve (código, body, headers extra)
# ==========================================================================

def post_reservas(body, headers):
    """CASO 5: idempotencia (tema 9) + bloqueo optimista (tema 10)."""
    clave = headers.get("Idempotency-Key")
    if not clave:
        raise ErrorHTTP(400, "falta el header Idempotency-Key")
    pasajero, conductor_id = datos_de_reserva(body)

    r = ejecutar(reservar(clave, pasajero, conductor_id))   # <- la función del caso 5

    extra = {"Idempotency-Key": clave}
    if r.get("repetida"):
        extra["Idempotent-Replayed"] = "true"   # mismo nombre que usa Stripe
    return r["codigo"], r, extra


def post_reservas_sin_idempotencia(body, headers):
    """CASO 1, parte A: cada pedido crea una reserva nueva."""
    pasajero, conductor_id = datos_de_reserva(body)
    r = ejecutar(crear_reserva_sin_idempotencia(pasajero, conductor_id))
    return r["codigo"], r, {}


def post_pagos(body, headers):
    """CASO 2: el consumidor de Pagos deduplica por el id del mensaje.
    Duplicado o no, responde 200: es el ACK, para que el emisor no reintente más."""
    mensaje = datos_de_mensaje(body)
    ack = ejecutar(procesar_con_deduplicacion(mensaje))      # <- la función del caso 2
    saldo = fila("SELECT saldo FROM conductores WHERE id = ?", mensaje["conductor_id"])["saldo"]
    return 200, {"ack": ack, "duplicado": "descartado" in ack, "saldo": saldo}, {}


def post_pagos_sin_deduplicacion(body, headers):
    """CASO 2, parte A: cada entrega paga."""
    mensaje = datos_de_mensaje(body)
    ack = ejecutar(procesar_sin_deduplicacion(mensaje))
    saldo = fila("SELECT saldo FROM conductores WHERE id = ?", mensaje["conductor_id"])["saldo"]
    return 200, {"ack": ack, "duplicado": False, "saldo": saldo}, {}


def monto_de(body):
    monto = body.get("monto")
    if not isinstance(monto, int) or isinstance(monto, bool) or monto <= 0:
        raise ErrorHTTP(400, "falta 'monto' (número mayor a 0)")
    return monto


def conductor_existente(cid):
    if not fila("SELECT id FROM conductores WHERE id = ?", cid):
        raise ErrorHTTP(404, f"no existe el conductor {cid}")


def post_acreditar_sin_control(cid, body, headers):
    """CASO 3, parte A: leer, calcular y escribir separados (se puede perder una acreditación)."""
    conductor_existente(cid)
    monto = monto_de(body)
    saldo = ejecutar(acreditar_ganancia(cid, monto))         # <- la función del caso 3
    return 200, {"conductor_id": cid, "acreditado": monto, "saldo": saldo}, {}


def post_acreditar(cid, body, headers):
    """CASO 3, la solución: la base suma en una sola operación (saldo = saldo + ?)."""
    conductor_existente(cid)
    monto = monto_de(body)
    saldo = ejecutar(acreditar_ganancia_atomica(cid, monto))
    return 200, {"conductor_id": cid, "acreditado": monto, "saldo": saldo}, {}


def post_asignaciones_sin_control(body, headers):
    """CASO 4, parte A: verificar y después actuar, sin volver a verificar."""
    pasajero, conductor_id = datos_de_reserva(body)
    r = ejecutar(asignar_sin_control(pasajero, conductor_id))   # <- la función del caso 4
    return r["codigo"], r, {}


def post_asignaciones(body, headers):
    """CASO 4, parte B: bloqueo optimista con la columna version (409 si otro ganó)."""
    pasajero, conductor_id = datos_de_reserva(body)
    r = ejecutar(asignar_con_bloqueo_optimista(pasajero, conductor_id))
    return r["codigo"], r, {}


def post_reset(body, headers):
    reiniciar()
    return 200, {"mensaje": "base reiniciada: Carlos (id 1) y Diana (id 2) disponibles, saldo $10000"}, {}


def get_inicio():
    return 200, {"endpoints": {
        "Caso 1": ["POST /reservas/sin-idempotencia", "POST /reservas  (header Idempotency-Key)"],
        "Caso 2": ["POST /pagos/sin-deduplicacion", "POST /pagos"],
        "Caso 3": ["POST /conductores/{id}/acreditar/sin-control", "POST /conductores/{id}/acreditar"],
        "Caso 4": ["POST /asignaciones/sin-control", "POST /asignaciones"],
        "Caso 5": ["POST /reservas  (header Idempotency-Key)"],
        "Consultas": ["GET /conductores", "GET /conductores/{id}", "GET /reservas", "GET /reservas/{id}"],
        "Reiniciar": ["POST /reset"],
    }}, {}


def get_conductores():
    return 200, todas("SELECT id, nombre, disponible, version, saldo FROM conductores"), {}


def get_conductor(cid):
    c = fila("SELECT id, nombre, disponible, version, saldo FROM conductores WHERE id = ?", cid)
    if not c:
        raise ErrorHTTP(404, f"no existe el conductor {cid}")
    return 200, c, {}


def get_reservas():
    return 200, todas("SELECT id, pasajero, conductor_id FROM reservas"), {}


def get_reserva(rid):
    r = fila("SELECT id, pasajero, conductor_id FROM reservas WHERE id = ?", rid)
    if not r:
        raise ErrorHTTP(404, f"no existe la reserva {rid}")
    return 200, r, {}


POST = {
    "/reservas": post_reservas,
    "/reservas/sin-idempotencia": post_reservas_sin_idempotencia,
    "/pagos": post_pagos,
    "/pagos/sin-deduplicacion": post_pagos_sin_deduplicacion,
    "/asignaciones": post_asignaciones,
    "/asignaciones/sin-control": post_asignaciones_sin_control,
    "/reset": post_reset,
}
POST_CON_ID = {
    re.compile(r"^/conductores/(\d+)/acreditar$"): post_acreditar,
    re.compile(r"^/conductores/(\d+)/acreditar/sin-control$"): post_acreditar_sin_control,
}
GET = {
    "/": get_inicio,
    "/conductores": get_conductores,
    "/reservas": get_reservas,
}
GET_CON_ID = {
    re.compile(r"^/conductores/(\d+)$"): get_conductor,
    re.compile(r"^/reservas/(\d+)$"): get_reserva,
}


# ==========================================================================
# El servidor HTTP (lectura del pedido y escritura de la respuesta)
# ==========================================================================

PANEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel.html")


def get_estado():
    """Lo que dibuja el panel: las tablas de la base y los últimos pedidos."""
    pedidos, contador = registro.historial()
    return {"base": os.path.basename(registro.db.RUTA), "contador": contador,
            "tablas": registro.estado_de_la_base(), "pedidos": pedidos}


class Manejador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    silencioso = False

    def do_GET(self):
        ruta = self.path.split("?")[0].rstrip("/") or "/"
        if ruta == "/panel":
            with open(PANEL, "rb") as f:
                return self._enviar_crudo(200, f.read(), "text/html; charset=utf-8")
        if ruta == "/estado":
            datos = json.dumps(get_estado(), ensure_ascii=False).encode("utf-8")
            return self._enviar_crudo(200, datos, "application/json; charset=utf-8")
        if ruta == "/favicon.ico":
            return self._enviar_crudo(204, b"", "image/x-icon")
        self._atender(self._get)   # /panel, /estado y /favicon.ico no se registran: el panel pide /estado cada segundo

    def do_POST(self):
        self._atender(self._post)

    def _enviar_crudo(self, codigo, datos, tipo):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def send_header(self, nombre, valor):
        # Guardamos los headers que mandamos, para mostrarlos en el registro.
        if hasattr(self, "_headers_enviados"):
            self._headers_enviados.append((nombre, str(valor)))
        super().send_header(nombre, valor)

    def _get(self):
        ruta = self.path.split("?")[0].rstrip("/") or "/"
        if ruta in GET:
            return GET[ruta]()
        for patron, funcion in GET_CON_ID.items():
            m = patron.match(ruta)
            if m:
                return funcion(int(m.group(1)))
        if ruta in POST or any(p.match(ruta) for p in POST_CON_ID):
            raise ErrorHTTP(405, f"{ruta} solo acepta POST")
        raise ErrorHTTP(404, f"no existe {ruta}")

    def _post(self):
        ruta = self.path.split("?")[0].rstrip("/") or "/"
        funcion, id_en_ruta = POST.get(ruta), ()
        for patron, f in POST_CON_ID.items():
            m = patron.match(ruta)
            if m:
                funcion, id_en_ruta = f, (int(m.group(1)),)   # p. ej. /conductores/1/acreditar → 1
        if funcion is None:
            if ruta in GET or any(p.match(ruta) for p in GET_CON_ID):
                raise ErrorHTTP(405, f"{ruta} solo acepta GET")
            raise ErrorHTTP(404, f"no existe {ruta}")
        largo = int(self.headers.get("Content-Length") or 0)
        crudo = self.rfile.read(largo) if largo else b""
        self._body_pedido = crudo.decode("utf-8", "replace")
        try:
            body = json.loads(crudo or b"{}")
        except json.JSONDecodeError:
            raise ErrorHTTP(400, "el body no es un JSON válido")
        if not isinstance(body, dict):
            raise ErrorHTTP(400, "el body tiene que ser un objeto JSON")
        return funcion(*id_en_ruta, body, self.headers)

    def _atender(self, funcion):
        # La prueba con hilos (prueba_http.py) manda este header: de esos pedidos
        # se guarda una sola línea, para no llenar la terminal con 50 bloques.
        carga = self.headers.get("X-Prueba-Carga") == "1"
        self._body_pedido = ""
        antes = None if carga else registro.foto()
        registro.iniciar_captura()
        error = None
        try:
            codigo, respuesta, extra = funcion()
        except ErrorHTTP as e:
            codigo, respuesta, extra, error = e.codigo, {"codigo": e.codigo, "error": e.mensaje}, {}, e.mensaje
        except Exception as e:  # noqa: BLE001 - que un error inesperado no tire el servidor
            codigo, respuesta, extra, error = 500, {"codigo": 500, "error": str(e)}, {}, str(e)
        finally:
            eventos = registro.terminar_captura()
        cambios = [] if carga else registro.cambios(antes, registro.foto())

        datos = json.dumps(respuesta, ensure_ascii=False, indent=2).encode("utf-8")
        self._headers_enviados = []
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        for nombre, valor in extra.items():
            self.send_header(nombre, valor)
        self.end_headers()
        self.wfile.write(datos)

        self._registrar(codigo, carga, eventos, cambios, datos.decode("utf-8"), error)

    def _registrar(self, codigo, carga, eventos, cambios, body_respuesta, error):
        """Arma el registro del pedido: lo imprime en la terminal y lo guarda para el panel."""
        pedido = {
            "numero": registro.nuevo_numero(), "hora": registro.ahora(), "carga": carga,
            "metodo": self.command, "ruta": self.path.split("?")[0], "ruta_completa": self.path,
            "version": self.request_version, "headers_pedido": list(self.headers.items()),
            "body_pedido": self._body_pedido, "eventos": eventos, "cambios": cambios,
            "codigo": codigo, "frase": HTTPStatus(codigo).phrase, "error": error,
            "headers_respuesta": self._headers_enviados, "body_respuesta": body_respuesta,
            "clave": self.headers.get("Idempotency-Key"),
        }
        registro.guardar(pedido)
        if not self.silencioso:
            registro.imprimir(pedido)

    def log_message(self, *args):  # reemplazado por _registrar
        pass


class Servidor(ThreadingHTTPServer):
    daemon_threads = True       # un hilo por pedido: los pedidos se atienden a la vez
    request_queue_size = 128    # conexiones en espera (por defecto son 5 y con 50 pedidos a la vez se pierden)
    # En Windows, "reusar la dirección" deja que DOS servidores escuchen en el mismo puerto
    # sin avisar, y los pedidos le llegan a uno cualquiera. Lo apagamos: la segunda API falla.
    allow_reuse_address = os.name != "nt"


def crear_servidor(host=HOST, port=PORT, silencioso=False):
    reiniciar()
    manejador = type("ManejadorConfigurado", (Manejador,), {"silencioso": silencioso})
    return Servidor((host, port), manejador)


def arrancar_en_segundo_plano(port=0):
    """Levanta la API en un hilo (para las pruebas). Devuelve (servidor, url)."""
    servidor = crear_servidor("127.0.0.1", port, silencioso=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}"


if __name__ == "__main__":
    try:
        servidor = crear_servidor()
    except OSError as e:
        # En Windows, Hyper-V/Docker reservan rangos de puertos (WinError 10013) y
        # a veces el puerto ya está en uso (WinError 10048 / EADDRINUSE).
        print(color(f"\n  No se pudo usar el puerto {PORT}: {e}", "rojo", "negrita"))
        print(color("  ¿Ya hay otra API corriendo en otra terminal? Cerrala (Ctrl+C) y volvé a probar.", "gris"))
        print(color("  Si no, probá con otro puerto, por ejemplo en PowerShell:  $env:PORT=6000; py api.py", "gris"))
        print(color("  (y cambiá la variable baseUrl en Postman a ese puerto)\n", "gris"))
        raise SystemExit(1)
    if os.name == "nt" and sys.stdout.isatty():
        os.system(f"title API Grupo 2 · puerto {PORT}")   # el nombre de la ventana
    print(color(f"\n  API de la demo escuchando en http://{HOST}:{PORT}", "cian", "negrita"))
    print(color(f"  Base de datos en vivo: http://127.0.0.1:{PORT}/panel", "cian"))
    print(color("  Probala con Postman (postman/Grupo2-demo.postman_collection.json) o con curl.", "gris"))
    print(color("  Cada pedido aparece acá: ① pedido → ② lógica → ③ base de datos → ④ respuesta.", "gris"))
    print(color("  Ctrl+C para cortar.\n", "gris"))
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print(color("\n  API detenida.", "gris"))
        servidor.server_close()
