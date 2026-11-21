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

## Qué técnica usa cada caso: ventajas, desventajas y cuándo no usarla

| Caso | Técnica | Ventaja | Desventaja (se ve en la demo) | Cuándo no usarla |
|---|---|---|---|---|
| 1 | Idempotency-Key (clave como PRIMARY KEY) | Reintentar es seguro: un solo efecto y siempre la misma respuesta | Hay que guardar claves y respuestas, y purgarlas (TTL) | GET, PUT o DELETE, que ya son idempotentes, o si los datos ya identifican la operación (alcanza un UNIQUE) |
| 2 | Deduplicación por id del mensaje | La cola puede reentregar sin pagar dos veces | La tabla `mensajes_procesados` crece: hace falta una ventana de deduplicación | Si la operación ya es idempotente, si un duplicado no importa o si el mensaje no tiene un id estable |
| 3 | Operación atómica (`saldo = saldo + ?`) | No hay ventana entre leer y escribir, sin esperas | Solo sirve si el cálculo se puede hacer en SQL | Si la decisión depende de lógica en la aplicación |
| 4 | Bloqueo optimista (columna `version`) | No bloquea a nadie; detecta el conflicto al escribir | 19 de 20 pedidos reciben 409 y el cliente tiene que manejarlo | Con mucha competencia por el mismo recurso: conviene el bloqueo pesimista (`SELECT … FOR UPDATE`) |
| 5 | Idempotencia + bloqueo optimista | Cada mecanismo cubre un problema distinto: reintentos de la misma intención e intenciones que compiten | Suma la complejidad de los dos | — |

Una condición de carrera (caso 3, parte B) no es una técnica sino el problema: aparece cuando hay un dato compartido, acceso concurrente y al menos una escritura. Si falta uno de los tres, no hay carrera.

La teoría completa y la relación con el TPI están en el informe y la presentación del grupo.

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

## La API HTTP (para probar con Postman)

Los mismos 5 casos, pero como endpoints HTTP de verdad, para ver en Postman los métodos, los headers, el body JSON y los códigos de estado reales. **No hay lógica nueva:** cada endpoint llama a la misma función del caso. Usa solo la biblioteca estándar de Python (`http.server`).

```bash
python api.py                 # escucha en http://127.0.0.1:5050  (en Windows puede ser: py api.py)
```

En la terminal del servidor aparece una línea por cada pedido (método, ruta, código y la Idempotency-Key). En Docker: `docker compose up api`.

### Cómo se conecta con la demo de la terminal

Cada caso se muestra en tres momentos, en este orden:

| Momento | Dónde | Qué muestra |
|---|---|---|
| 1. Paso a paso | `python main.py N` | **Cómo** funciona por dentro: el intercalado, las tablas, la explicación |
| 2. Como API real | Postman, carpeta **«Caso N»** → A) y después B) | Lo mismo como lo vería una app: pedido HTTP, header, JSON y código de estado |
| 3. Pedidos a la vez | `python prueba_http.py N` | Lo mismo con muchos pedidos HTTP simultáneos |

Al final de cada caso, `main.py` muestra qué carpeta de Postman sigue.

### Endpoints por caso

| Caso | A) sin el concepto | B) con el concepto | Qué se ve en Postman |
|---|---|---|---|
| 1 · Idempotencia | `POST /reservas/sin-idempotencia` | `POST /reservas` + header `Idempotency-Key` | A: 2 reservas. B: **201**, el reintento **201** con la misma reserva y el header `Idempotent-Replayed: true`, **422** misma clave con otros datos, **400** sin la clave |
| 2 · Deduplicación | `POST /pagos/sin-deduplicacion` | `POST /pagos` | A: cobra 2 veces ($13000). B: la reentrega se descarta (`"duplicado": true`, $11500) |
| 3 · Condición de carrera | `POST /conductores/{id}/acreditar/sin-control` | `POST /conductores/{id}/acreditar` | De a un pedido los dos dan bien ($13500): la carrera se ve con `prueba_http.py 3` |
| 4 · Control de concurrencia | `POST /asignaciones/sin-control` | `POST /asignaciones` | B: Ana **201**, Beto **409** y la versión de Carlos pasa de 0 a 1. La doble asignación de A se ve con `prueba_http.py 4` |
| 5 · Todo junto | — | `POST /reservas` + header `Idempotency-Key` | Ana **201** en sus 2 intentos y Beto **409** en los 2; 1 sola reserva |

`POST /reservas` llama a `reservar()` del caso 5, que adentro tiene la idempotencia del caso 1 y el bloqueo optimista del caso 4. Consultas: `GET /conductores`, `GET /conductores/{id}` (**404** si no existe), `GET /reservas`, `GET /reservas/{id}`. `POST /reset` deja la base como al principio.

### Postman

Importar `postman/Grupo2-demo.postman_collection.json` (Import, o arrastrar el archivo a la ventana). Las carpetas son las mismas que el menú de `main.py`: **Caso 1** a **Caso 5**, cada una con A) y B). Cada carpeta empieza con «Reiniciar la base», así que se puede correr cualquiera sola: un **Send** por pedido, de arriba a abajo. Cada pedido tiene un test que marca en verde lo esperado; con **Run** se corre una carpeta o la colección entera.

Al abrir la carpeta del repositorio en Postman, la app crea `.postman/` y archivos dentro de `postman/`: son configuración local y están en el `.gitignore`.

### Pedidos a la vez: `prueba_http.py`

Postman manda los pedidos de a uno (también el Collection Runner): por eso en los casos 3 y 4 la parte A da bien en Postman. Sin acceso concurrente no hay carrera. Para pedidos HTTP simultáneos:

```bash
python prueba_http.py         # los 5 casos
python prueba_http.py 3       # solo el caso 3: 50 acreditaciones a la vez
```

Usa la API que está corriendo; si no hay ninguna, levanta una propia.

**Si el puerto está bloqueado** (en Windows, Hyper-V y Docker reservan rangos de puertos y aparece `WinError 10013`): `$env:PORT=6000; python api.py` en PowerShell, y cambiar la variable `baseUrl` de la colección a ese puerto. Para ver los rangos reservados: `netsh interface ipv4 show excludedportrange protocol=tcp`.

## Pruebas automáticas

```bash
pip install pytest
python -m pytest -v
```

Son 34 pruebas. Las 16 de `tests/test_casos.py` prueban cada caso con el mismo orden intercalado de la demo y con hilos reales. Las 18 de `tests/test_api.py` levantan la API y le mandan pedidos HTTP de verdad, también desde muchos hilos a la vez.

## Cómo está armado el código

| Archivo | Qué tiene |
|---|---|
| `main.py` | Menú y resumen |
| `caso1_…` a `caso5_…` | Arriba, **la lógica** que se explica (las funciones sin/con cada concepto). Abajo, la demo (solo textos y pantallas) |
| `planificador.py` | Cómo se ejecutan los pedidos: paso a paso con Enter, o en hilos reales |
| `db.py` | La base SQLite y sus tablas |
| `consola.py` | Colores, tablas y la línea de tiempo en columnas (solo presentación) |
| `api.py` | La API HTTP: valida el pedido, llama a la función del caso y traduce el resultado a un código de estado |
| `cliente_http.py` | Un cliente HTTP mínimo (como Postman, pero desde Python) y el envío de pedidos en paralelo |
| `prueba_http.py` | La comprobación con hilos reales, por HTTP |
| `postman/` | La colección de Postman |
| `tests/` | `test_casos.py` (los 5 casos) y `test_api.py` (la API) |

**Por qué los pedidos tienen `yield`:** cada pedido es una función generadora. Cada `yield` es un punto donde el pedido se pausa y donde, en un sistema real, otro pedido podría meterse en el medio. Eso permite elegir el orden y ver el intercalado paso a paso. Las operaciones contra la base son reales; lo único que se controla es el orden, como en un depurador. La comprobación con hilos reales muestra lo mismo sin controlar nada.

## Las funciones a mostrar en cada caso

| Caso | Sin | Con | La línea clave |
|---|---|---|---|
| 1 | `crear_reserva_sin_idempotencia` | `crear_reserva_con_idempotencia` | `INSERT INTO idempotencia …` (la clave es PRIMARY KEY) |
| 2 | `procesar_sin_deduplicacion` | `procesar_con_deduplicacion` | `INSERT INTO mensajes_procesados …` en la misma transacción que el pago |
| 3 | `acreditar_ganancia` (en serie) | `acreditar_ganancia` (intercalada) | leer → calcular → escribir separados; la solución, `saldo = saldo + ?` |
| 4 | `asignar_sin_control` | `asignar_con_bloqueo_optimista` | `UPDATE … WHERE id = ? AND version = ?` y `rowcount == 0` |
| 5 | `asignar_sin_control` | `reservar` | `yield from asignar_con_bloqueo_optimista(...)` dentro de la lógica de idempotencia |
