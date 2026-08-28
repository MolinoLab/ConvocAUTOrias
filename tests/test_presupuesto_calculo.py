"""Tests de cálculo de costes de presupuestos (sin red)."""
from __future__ import annotations

import unittest

from src.presupuesto_calculo import (
    MODO_ALOJAMIENTO,
    MODO_DIARIO,
    MODO_NINGUNO,
    MODO_UNICO,
    calcular_costes,
    formatear_euros,
    generar_markdown,
    parsear_float,
    resolver_modo,
)
from src.db_presupuestos import Presupuesto


class TestCalcularCostes(unittest.TestCase):
    def test_solo_jornadas(self) -> None:
        r = calcular_costes(
            jornadas=3,
            precio_dia=280,
            modo=MODO_NINGUNO,
            km_ida=45,
            coste_km=0.30,
        )
        self.assertEqual(r.coste_jornadas, 840.0)
        self.assertEqual(r.coste_desplazamiento, 0.0)
        self.assertEqual(r.coste_alojamiento, 0.0)
        self.assertEqual(r.total, 840.0)
        self.assertEqual(r.viajes, 0)

    def test_ida_vuelta_diaria(self) -> None:
        r = calcular_costes(
            jornadas=3,
            precio_dia=280,
            modo=MODO_DIARIO,
            km_ida=45,
            coste_km=0.30,
        )
        # 45 * 2 * 3 * 0.30 = 81
        self.assertEqual(r.coste_desplazamiento, 81.0)
        self.assertEqual(r.coste_jornadas, 840.0)
        self.assertEqual(r.total, 921.0)
        self.assertEqual(r.viajes, 3)

    def test_ida_vuelta_unica(self) -> None:
        r = calcular_costes(
            jornadas=3,
            precio_dia=280,
            modo=MODO_UNICO,
            km_ida=45,
            coste_km=0.30,
        )
        # 45 * 2 * 1 * 0.30 = 27
        self.assertEqual(r.coste_desplazamiento, 27.0)
        self.assertEqual(r.total, 867.0)
        self.assertEqual(r.viajes, 1)

    def test_alojamiento(self) -> None:
        r = calcular_costes(
            jornadas=3,
            precio_dia=280,
            modo=MODO_ALOJAMIENTO,
            km_ida=100,
            noches=2,
            precio_noche=50,
            coste_km=0.30,
        )
        # gasolina 100 * 2 * 0.30 = 60; alojamiento 100
        self.assertEqual(r.coste_desplazamiento, 60.0)
        self.assertEqual(r.coste_alojamiento, 100.0)
        self.assertEqual(r.total, 1000.0)

    def test_total_combinado(self) -> None:
        r = calcular_costes(
            jornadas=2,
            precio_dia=280,
            modo=MODO_DIARIO,
            km_ida=10,
            coste_km=0.30,
        )
        self.assertEqual(r.coste_jornadas, 560.0)
        self.assertEqual(r.coste_desplazamiento, 12.0)
        self.assertEqual(r.total, 572.0)

    def test_formatear_euros(self) -> None:
        self.assertEqual(formatear_euros(921.0), "921 EUR")
        self.assertEqual(formatear_euros(12.5), "12.50 EUR")

    def test_resolver_modo(self) -> None:
        self.assertEqual(resolver_modo("diario"), MODO_DIARIO)
        self.assertEqual(resolver_modo("unico"), MODO_UNICO)
        self.assertEqual(resolver_modo("alojamiento"), MODO_ALOJAMIENTO)
        self.assertIsNone(resolver_modo("patata"))

    def test_parsear_float(self) -> None:
        self.assertEqual(parsear_float("280€"), 280.0)
        self.assertEqual(parsear_float("1,5"), 1.5)
        self.assertEqual(parsear_float("", 9.0), 9.0)

    def test_markdown_incluye_total(self) -> None:
        p = Presupuesto(
            id="abc",
            id_proyecto="proy",
            titulo="Valle del Duero",
            descripcion="Rodaje",
            lugar="Castronuño, Valladolid",
            necesidades_tecnicas="camara 4k",
            jornadas="3",
            precio_dia="280",
            modo_desplazamiento=MODO_DIARIO,
            km_ida="45",
            coste_desplazamiento="81",
            noches_alojamiento="0",
            coste_alojamiento="0",
            total_aproximado="921",
            ruta="",
            fecha_creacion="",
            fuente="test",
        )
        md = generar_markdown(p, ideas=[])
        self.assertIn("# Presupuesto: Valle del Duero", md)
        self.assertIn("921 EUR", md)
        self.assertIn("Castronuño", md)
        self.assertIn("ida y vuelta diaria", md)


if __name__ == "__main__":
    unittest.main()
