"""
Base de datos de la demo: SQLite, que viene incluido con Python (no hay que instalar nada).

Tablas:
  conductores          id, nombre, disponible, version, saldo
  reservas             id, pasajero, conductor_id
  idempotencia         clave (PRIMARY KEY), datos, respuesta        -> caso 1
  mensajes_procesados  id_mensaje (PRIMARY KEY)                     -> caso 2
  pagos                id, mensaje_id, conductor_id, monto          -> caso 2
"""
import os
import sqlite3

RUTA = os.environ.get("DB_PATH", "demo.db")
TABLAS = ["conductores", "reservas", "idempotencia", "mensajes_procesados", "pagos"]

# Si alguien define esta función, recibe cada sentencia SQL que se ejecuta (con los
# valores reales, la informa el propio SQLite) y su resultado: cuántas filas tocó o el
# error. La usa la API para mostrar el SQL de cada pedido. En la demo de la terminal
# queda en None y no hace nada.
observador_sql = None


def _avisar(tipo, texto):
    if observador_sql:
        observador_sql(tipo, texto)


class _Conexion(sqlite3.Connection):
    """Una conexión normal que, además, avisa el resultado de cada sentencia."""

    def execute(self, sql, parametros=()):
        try:
            cursor = super().execute(sql, parametros)
        except sqlite3.Error as e:
            _avisar("error", f"{type(e).__name__}: {e}")   # p. ej. UNIQUE constraint failed
            raise
        if sql.split(None, 1)[0].upper() in ("INSERT", "UPDATE", "DELETE"):
            _avisar("filas", cursor.rowcount)                # p. ej. el UPDATE con versión: 0 filas
        return cursor


def conectar():
    # isolation_level=None: cada sentencia se confirma sola (autocommit).
    # Cuando hace falta una transacción, la abrimos a mano con BEGIN ... COMMIT.
    con = sqlite3.connect(RUTA, timeout=30, isolation_level=None, factory=_Conexion)
    con.row_factory = sqlite3.Row
    con.set_trace_callback(lambda sentencia: _avisar("sql", sentencia))
    return con


def reiniciar():
    con = conectar()
    con.executescript("""
        DROP TABLE IF EXISTS conductores;
        DROP TABLE IF EXISTS reservas;
        DROP TABLE IF EXISTS idempotencia;
        DROP TABLE IF EXISTS mensajes_procesados;
        DROP TABLE IF EXISTS pagos;

        CREATE TABLE conductores (
            id INTEGER PRIMARY KEY, nombre TEXT,
            disponible INTEGER DEFAULT 1, version INTEGER DEFAULT 0, saldo INTEGER DEFAULT 10000);
        CREATE TABLE reservas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, pasajero TEXT, conductor_id INTEGER);
        CREATE TABLE idempotencia (
            clave TEXT PRIMARY KEY, datos TEXT, respuesta TEXT);
        CREATE TABLE mensajes_procesados (
            id_mensaje TEXT PRIMARY KEY);
        CREATE TABLE pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, mensaje_id TEXT, conductor_id INTEGER, monto INTEGER);

        INSERT INTO conductores (id, nombre) VALUES (1, 'Carlos'), (2, 'Diana');
    """)
    con.close()


def filas(sql, *parametros):
    con = conectar()
    resultado = [dict(f) for f in con.execute(sql, parametros)]
    con.close()
    return resultado


def valor(sql, *parametros):
    con = conectar()
    resultado = con.execute(sql, parametros).fetchone()[0]
    con.close()
    return resultado


def saldo_de(con, conductor_id):
    return con.execute("SELECT saldo FROM conductores WHERE id = ?", (conductor_id,)).fetchone()[0]
