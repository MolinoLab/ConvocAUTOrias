"""Tests de ventana semanal de agenda."""
from __future__ import annotations

import unittest
from datetime import date

from src.fecha_display import lunes_semana_entrante


class TestLunesSemanaEntrante(unittest.TestCase):
    def test_domingo_es_lunes_siguiente(self) -> None:
        dom = date(2026, 5, 24)  # domingo
        self.assertEqual(lunes_semana_entrante(dom), date(2026, 5, 25))

    def test_lunes_no_salta_siete_dias(self) -> None:
        lun = date(2026, 5, 25)  # lunes
        self.assertEqual(lunes_semana_entrante(lun), date(2026, 5, 25))

    def test_martes_es_lunes_de_su_semana(self) -> None:
        mar = date(2026, 5, 26)  # martes
        self.assertEqual(lunes_semana_entrante(mar), date(2026, 5, 25))


if __name__ == "__main__":
    unittest.main()
