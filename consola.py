"""
Utilidades para mostrar la demo en la terminal: colores, pausas con Enter,
tablas y la "línea de tiempo" en columnas (una columna por pedido).

No tiene lógica de los temas: es solo presentación.
"""
import os
import shutil
import sys
import textwrap

os.system("")  # en Windows activa los colores ANSI de la terminal
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# python main.py --auto  -> corre sin pausas (para ensayar o para las pruebas)
AUTO = "--auto" in sys.argv or os.environ.get("DEMO_AUTO") == "1"

COLORES = {
    "azul": "\033[94m", "cian": "\033[96m", "violeta": "\033[95m",
    "naranja": "\033[38;5;215m", "amarillo": "\033[93m",
    "verde": "\033[92m", "rojo": "\033[91m", "gris": "\033[90m",
    "negrita": "\033[1m", "fin": "\033[0m",
}


def color(texto, *nombres):
    return "".join(COLORES[n] for n in nombres) + str(texto) + COLORES["fin"]


def ancho():
    return max(80, min(shutil.get_terminal_size((120, 30)).columns, 150))


def limpiar():
    if not AUTO:
        print("\033[2J\033[H", end="")


def pausa(mensaje="Enter para seguir"):
    if AUTO:
        return
    input(color(f"   ⏎  {mensaje}", "gris"))
    print("\033[F\033[K", end="")  # borra el aviso para que no ensucie la pantalla


def titulo(texto, col="cian"):
    w = ancho()
    print()
    print(color("═" * w, col))
    print(color("  " + texto, col, "negrita"))
    print(color("═" * w, col))


def seccion(texto, col="cian"):
    print()
    print(color(f"▌ {texto}", col, "negrita"))
    print()


def parrafo(texto, sangria=2, col=None):
    for linea in textwrap.wrap(texto, ancho() - sangria - 2):
        print(" " * sangria + (color(linea, col) if col else linea))
    print()


def bien(texto):
    print(color(f"  ✔  {texto}", "verde", "negrita"))


def mal(texto):
    print(color(f"  ✘  {texto}", "rojo", "negrita"))


def nota(texto):
    for linea in textwrap.wrap(texto, ancho() - 6):
        print(color(f"     {linea}", "gris"))


def codigo(lineas):
    """Muestra un fragmento de código o SQL en un recuadro."""
    for linea in lineas:
        print(color("     │ ", "gris") + color(linea, "amarillo"))
    print()


def tabla(titulo_tabla, filas, columnas, marcar=None):
    """Imprime una lista de diccionarios como tabla. `marcar(fila)` puede devolver un color."""
    anchos = {c: max([len(c)] + [len(str(f[c])) for f in filas]) for c in columnas}
    print(color(f"   ┌─ {titulo_tabla}", "gris"))
    print(color("   │ " + "   ".join(c.ljust(anchos[c]) for c in columnas), "gris"))
    if not filas:
        print(color("   │ (sin filas)", "gris"))
    for f in filas:
        linea = "   ".join(str(f[c]).ljust(anchos[c]) for c in columnas)
        col = marcar(f) if marcar else None
        print(color("   │ ", "gris") + (color(linea, col, "negrita") if col else linea))
    print(color("   └" + "─" * 20, "gris"))
    print()


class LineaDeTiempo:
    """Dibuja cada paso en la columna del pedido que lo ejecutó."""

    def __init__(self, nombres, colores):
        self.nombres = nombres
        self.colores = colores
        self.cw = max(26, (ancho() - 7) // len(nombres))

    def encabezado(self):
        celdas = "".join(
            color("│ ", "gris") + color(n[: self.cw - 3].ljust(self.cw - 2), self.colores[i], "negrita")
            for i, n in enumerate(self.nombres)
        )
        print(color(" paso ", "gris") + celdas)
        print(color("──────" + ("┼" + "─" * (self.cw - 1)) * len(self.nombres), "gris"))

    def paso(self, numero, nombre, texto, final=False):
        i = self.nombres.index(nombre)
        lineas = textwrap.wrap(str(texto), self.cw - 3) or [""]
        for k, linea in enumerate(lineas):
            prefijo = f" {numero:>3}  " if k == 0 else "      "
            fila = color(prefijo, "gris")
            for j in range(len(self.nombres)):
                contenido = linea if j == i else ""
                celda = contenido.ljust(self.cw - 2)
                if j == i:
                    celda = color(celda, self.colores[i], "negrita") if final else color(celda, self.colores[i])
                fila += color("│ ", "gris") + celda
            print(fila)
