# TP de Investigación · Grupo 2 · Desarrollo de Software · UTN FRRe 2026

**Tema 9:** Idempotencia y deduplicación
**Tema 10:** Condiciones de carrera y control de concurrencia

Demo por terminal, paso a paso: 4 casos, cada uno **sin** y **con** el concepto, y un caso 5 con todo junto. Cada Enter ejecuta un paso real contra la base de datos y se ve en qué orden avanzan los pedidos.

Escenario de todos los casos: la plataforma de movilidad del TPI (pasajeros que reservan conductores, pagos a conductores).

## Los casos

| Caso | Archivo | A) sin el concepto | B) con el concepto |
|---|---|---|---|
| 1 · Idempotencia | `caso1_idempotencia.py` | La app reintenta → 2 reservas | Idempotency-Key → 1 reserva y la misma respuesta para los 2 intentos |
| 2 · Deduplicación | `caso2_deduplicacion.py` | La cola reentrega el mensaje → se paga 2 veces | Se guarda el id del mensaje → la reentrega se descarta |
| 3 · Condición de carrera | `caso3_condicion_carrera.py` | Dos acreditaciones en serie → saldo correcto | Las mismas, intercaladas → se pierde una (actualización perdida) |
| 4 · Control de concurrencia | `caso4_control_concurrencia.py` | Ana y Beto piden a Carlos → doble asignación | Bloqueo optimista con versión → un éxito y un conflicto |
| 5 · Todo junto | `caso5_todo_junto.py` | Ana y Beto piden a Carlos y cada app reintenta → 4 reservas | Idempotencia + bloqueo optimista → 1 reserva, y cada pasajero recibe siempre la misma respuesta |

Cada caso termina con una **comprobación con hilos reales** (20 a 50 pedidos a la vez, sin pausas) para mostrar que el problema aparece solo y que la solución lo resuelve.

## Requisitos

Solo **Python 3.10 o superior**. No hay que instalar nada más: la base de datos es SQLite, que viene con Python.
(Para las pruebas automáticas hace falta `pytest`.)

## Cómo ejecutarla

### Opción 1: VS Code

1. Abrir la carpeta del proyecto en VS Code.
2. Abrir la terminal: **Terminal → Nueva terminal**.
3. Ejecutar:

```bash
python main.py
```

Aparece un menú: se elige el caso (1 a 5), `t` para todos seguidos o `6` para el resumen. Después, **Enter** para avanzar cada paso.

Atajos:

```bash
python main.py 1        # directo al caso 1 (también 2, 3, 4, 5)
python main.py todos    # los 5 casos seguidos
python main.py --auto   # todo sin pausas (para ensayar)
```

### Opción 2: en un contenedor (Docker)

```bash
docker compose run --rm demo
```

Construye la imagen la primera vez y abre la demo en la terminal. Se usa `run` (y no `up`) para que la terminal quede conectada y funcionen los Enter. Para ir directo a un caso: `docker compose run --rm demo python main.py 3`.

## Pruebas automáticas

```bash
pip install pytest
python -m pytest -v
```

Son 15 pruebas: cada caso se prueba con el mismo orden intercalado de la demo y con hilos reales.

## Cómo está armado el código

| Archivo | Qué tiene |
|---|---|
| `main.py` | Menú y resumen |
| `caso1_…` a `caso5_…` | Arriba, **la lógica** que se explica (las funciones sin/con cada concepto). Abajo, la demo (solo textos y pantallas) |
| `planificador.py` | Cómo se ejecutan los pedidos: paso a paso con Enter, o en hilos reales |
| `db.py` | La base SQLite y sus tablas |
| `consola.py` | Colores, tablas y la línea de tiempo en columnas (solo presentación) |

**Por qué los pedidos tienen `yield`:** cada pedido es una función generadora. Cada `yield` es un punto donde el pedido se pausa y donde, en un sistema real, otro pedido podría meterse en el medio. Eso permite elegir el orden y ver el intercalado paso a paso. Las operaciones contra la base son reales; lo único que se controla es el orden, como en un depurador. La comprobación con hilos reales muestra lo mismo sin controlar nada.

## Las funciones a mostrar en cada caso

| Caso | Sin | Con | La línea clave |
|---|---|---|---|
| 1 | `crear_reserva_sin_idempotencia` | `crear_reserva_con_idempotencia` | `INSERT INTO idempotencia …` (la clave es PRIMARY KEY) |
| 2 | `procesar_sin_deduplicacion` | `procesar_con_deduplicacion` | `INSERT INTO mensajes_procesados …` en la misma transacción que el pago |
| 3 | `acreditar_ganancia` (en serie) | `acreditar_ganancia` (intercalada) | leer → calcular → escribir separados; la solución, `saldo = saldo + ?` |
| 4 | `asignar_sin_control` | `asignar_con_bloqueo_optimista` | `UPDATE … WHERE id = ? AND version = ?` y `rowcount == 0` |
| 5 | `asignar_sin_control` | `reservar` | `yield from asignar_con_bloqueo_optimista(...)` dentro de la lógica de idempotencia |
