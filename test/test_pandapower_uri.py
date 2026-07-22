# coding=utf-8
"""Tests for the layer URI scheme.

The scheme was reworked in phase 2 (docs/dataprovider_v2_plan.md section 3.5):
``network_type`` became ``table``, ``voltage_level``/``pressure_level`` became
``level``, and ``geometry`` was dropped. Old URIs must keep decoding so that
projects saved by an earlier version still open.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.
"""

import os
import sys
import unittest

PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'pandapower-qgis'))


def load_uri_module():
    """Import pandapower_uri from the plugin directory.

    :returns: The imported pandapower_uri module.
    """
    import importlib

    parent = os.path.dirname(PLUGIN_DIR)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    package = 'pandapower_qgis_plugin'
    if package not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            package,
            os.path.join(PLUGIN_DIR, '__init__.py'),
            submodule_search_locations=[PLUGIN_DIR])
        module = importlib.util.module_from_spec(spec)
        sys.modules[package] = module
        spec.loader.exec_module(module)

    return importlib.import_module('{}.pandapower_uri'.format(package))


class UriSchemeTest(unittest.TestCase):
    """Test encoding, decoding and backwards compatibility of layer URIs."""

    @classmethod
    def setUpClass(cls):
        cls.uri = load_uri_module()

    # -- encoding ---------------------------------------------------------

    def test_encode_includes_all_parts(self):
        """A levelled table encodes path, table, level and epsg."""
        encoded = self.uri.encode_uri(
            'C:/net/mv.json', 'bus', level='20.0', epsg='4326')

        self.assertIn('path="C:/net/mv.json"', encoded)
        self.assertIn('table="bus"', encoded)
        self.assertIn('level="20.0"', encoded)
        self.assertIn('epsg="4326"', encoded)

    def test_encode_omits_absent_level(self):
        """A whole-table URI carries no level key at all."""
        encoded = self.uri.encode_uri('C:/net/mv.json', 'trafo', epsg='4326')

        self.assertNotIn('level=', encoded)
        self.assertIn('table="trafo"', encoded)

    def test_encode_drops_geometry_key(self):
        """The geometry key is gone; it is derivable from the table name."""
        encoded = self.uri.encode_uri(
            'C:/net/mv.json', 'bus', level='20.0', epsg='4326')

        self.assertNotIn('geometry=', encoded)

    def test_encode_accepts_numeric_level(self):
        """A float level is encoded without the caller having to stringify it."""
        encoded = self.uri.encode_uri('C:/net/mv.json', 'bus', level=20.0)

        self.assertIn('level="20.0"', encoded)

    # -- decoding ---------------------------------------------------------

    def test_decode_current_scheme(self):
        """The current keys decode as written."""
        decoded = self.uri.decode_uri({
            'path': 'C:/net/mv.json',
            'table': 'bus',
            'level': '20.0',
            'epsg': '4326',
        })

        self.assertEqual(decoded['path'], 'C:/net/mv.json')
        self.assertEqual(decoded['table'], 'bus')
        self.assertEqual(decoded['level'], '20.0')
        self.assertEqual(decoded['epsg'], '4326')

    def test_decode_legacy_network_type(self):
        """A pre-rework 'network_type' URI still decodes.

        Regression guard for projects saved before phase 2.
        """
        decoded = self.uri.decode_uri({
            'path': 'C:/net/mv.json',
            'network_type': 'bus',
            'voltage_level': '20.0',
            'geometry': 'Point',
            'epsg': '4326',
        })

        self.assertEqual(decoded['table'], 'bus')
        self.assertEqual(decoded['level'], '20.0')

    def test_decode_legacy_pressure_level(self):
        """The old pipe key folds into 'level' as well.

        The old scheme wrote 'pressure_level' for pipes but the provider only
        read 'voltage_level', so pipe layers silently lost their level. Both
        names now map onto 'level'.
        """
        decoded = self.uri.decode_uri({
            'path': 'C:/net/gas.json',
            'network_type': 'junction',
            'pressure_level': '1.0',
        })

        self.assertEqual(decoded['table'], 'junction')
        self.assertEqual(decoded['level'], '1.0')

    def test_decode_prefers_new_key_over_legacy(self):
        """When both spellings are present the current one wins."""
        decoded = self.uri.decode_uri({
            'path': 'C:/net/mv.json',
            'table': 'line',
            'network_type': 'bus',
            'level': '110.0',
            'voltage_level': '20.0',
        })

        self.assertEqual(decoded['table'], 'line')
        self.assertEqual(decoded['level'], '110.0')

    def test_decode_absent_level_is_none(self):
        """A whole-table URI decodes with level None, not an empty string."""
        decoded = self.uri.decode_uri({
            'path': 'C:/net/mv.json',
            'table': 'trafo',
        })

        self.assertIsNone(decoded['level'])

    def test_decode_tolerates_empty_input(self):
        """Decoding junk does not raise."""
        decoded = self.uri.decode_uri({})

        self.assertEqual(decoded['path'], '')
        self.assertIsNone(decoded['table'])
        self.assertIsNone(decoded['level'])

    def test_round_trip_through_local_encoder(self):
        """Encoding then decoding preserves every component."""
        import re

        encoded = self.uri.encode_uri(
            'C:/net/mv.json', 'line', level='110.0', epsg='25832')
        parts = dict(re.findall(r'(\w+)="((?:\\"|[^"])*)"', encoded))
        decoded = self.uri.decode_uri(parts)

        self.assertEqual(decoded['path'], 'C:/net/mv.json')
        self.assertEqual(decoded['table'], 'line')
        self.assertEqual(decoded['level'], '110.0')
        self.assertEqual(decoded['epsg'], '25832')

    # -- geometry derivation ----------------------------------------------

    def test_geometry_type_for_tables(self):
        """Geometry type follows from the table name."""
        self.assertEqual(self.uri.geometry_type_for('bus'), 'Point')
        self.assertEqual(self.uri.geometry_type_for('junction'), 'Point')
        self.assertEqual(self.uri.geometry_type_for('line'), 'LineString')
        self.assertEqual(self.uri.geometry_type_for('pipe'), 'LineString')
        self.assertEqual(self.uri.geometry_type_for('trafo'), 'None')

    def test_has_geometry(self):
        """Only the four geometry-bearing tables report geometry."""
        self.assertTrue(self.uri.has_geometry('bus'))
        self.assertTrue(self.uri.has_geometry('line'))
        self.assertFalse(self.uri.has_geometry('trafo'))
        self.assertFalse(self.uri.has_geometry('load'))
        self.assertFalse(self.uri.has_geometry('res_bus'))

    # -- layer naming -----------------------------------------------------

    def test_layer_name_with_level(self):
        """A levelled layer name carries file, level and table."""
        self.assertEqual(
            self.uri.layer_name_for('C:/net/mv_oberrhein.json', 'bus', '20.0'),
            'mv_oberrhein_20.0_bus')

    def test_layer_name_without_level(self):
        """A whole-table layer name omits the level."""
        self.assertEqual(
            self.uri.layer_name_for('C:/net/mv_oberrhein.json', 'trafo'),
            'mv_oberrhein_trafo')


if __name__ == '__main__':
    unittest.main()
