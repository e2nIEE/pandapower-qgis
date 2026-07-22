# coding=utf-8
"""Tests for the Browser tree items.

Covers the rules from docs/dataprovider_v2_plan.md sections 3.2 and 5.2:
file sniffing must stay cheap, only populated input tables are listed, bus and
line split by voltage level, and empty ``res_*`` tables are listed but greyed.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.
"""

import os
import sys
import tempfile
import time
import unittest

from qgis.core import Qgis, QgsProviderRegistry

from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()

PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'pandapower-qgis'))


def load_plugin_module(name):
    """Import a module from the plugin directory by name.

    :param name: Module name inside the plugin package.
    :returns: The imported module.
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

    return importlib.import_module('{}.{}'.format(package, name))


class SniffTest(unittest.TestCase):
    """Test the file sniff that decides what appears in the Browser."""

    @classmethod
    def setUpClass(cls):
        cls.items = load_plugin_module('pandapower_data_items')
        cls.directory = tempfile.mkdtemp()

    def _write(self, name, content):
        path = os.path.join(self.directory, name)
        with open(path, 'w') as handle:
            handle.write(content)
        return path

    def test_detects_pandapower_marker(self):
        """A pandapower network is recognised."""
        path = self._write('power.json', '{"_module": "pandapowerNet"}')
        self.assertEqual(self.items.sniff_network_kind(path), 'power')

    def test_detects_pandapipes_marker(self):
        """A pandapipes network is recognised too (plan 5.4)."""
        path = self._write('pipes.json', '{"_module": "pandapipesNet"}')
        self.assertEqual(self.items.sniff_network_kind(path), 'pipes')

    def test_rejects_unrelated_json(self):
        """A plain GeoJSON file is not a pandapower network."""
        path = self._write('other.json', '{"type": "FeatureCollection"}')
        self.assertIsNone(self.items.sniff_network_kind(path))

    def test_missing_file_is_not_an_error(self):
        """A vanished file returns None rather than raising."""
        missing = os.path.join(self.directory, 'gone.json')
        self.assertIsNone(self.items.sniff_network_kind(missing))

    def test_sniff_is_a_bounded_read(self):
        """A large non-matching file is rejected without being read whole.

        The Browser calls this for every .json in every expanded directory, so
        a full read would stall the UI on a folder of large networks.
        """
        path = self._write('big.json', '{"x": "' + ('y' * 5_000_000) + '"}')

        start = time.time()
        result = self.items.sniff_network_kind(path)
        elapsed = time.time() - start

        self.assertIsNone(result)
        self.assertLess(elapsed, 0.5)

    def test_marker_beyond_the_sniff_window_is_missed(self):
        """Document the bound: the marker must appear early in the file.

        pandapower writes its module marker in the first bytes, so this is a
        deliberate trade rather than a defect. The test pins the behaviour so
        a future change to SNIFF_BYTES is a conscious one.
        """
        padding = ' ' * (self.items.SNIFF_BYTES + 100)
        path = self._write('late.json', '{' + padding + '"pandapowerNet"}')

        self.assertIsNone(self.items.sniff_network_kind(path))


@unittest.skipIf(os.environ.get('SKIP_PANDAPOWER_TESTS'),
                 'pandapower tests disabled')
class TreeStructureTest(unittest.TestCase):
    """Test the shape of the tree built for a real network."""

    @classmethod
    def setUpClass(cls):
        import pandapower as pp
        import pandapower.networks as ppn

        metadata_module = load_plugin_module('ppprovider_metadata')
        registry = QgsProviderRegistry.instance()
        if 'PandapowerProvider' not in registry.providerList():
            registry.registerProvider(
                metadata_module.PandapowerProviderMetadata())

        cls.items = load_plugin_module('pandapower_data_items')
        cls.session_module = load_plugin_module('network_session')

        cls.directory = tempfile.mkdtemp()

        # mv_oberrhein ships with results already computed.
        cls.net = ppn.mv_oberrhein()
        cls.with_results = os.path.join(cls.directory, 'with_results.json')
        pp.to_json(cls.net, cls.with_results)

        # cigre_mv has empty res_* tables.
        cls.net_empty = ppn.create_cigre_network_mv()
        cls.without_results = os.path.join(cls.directory, 'no_results.json')
        pp.to_json(cls.net_empty, cls.without_results)

    def setUp(self):
        self.session_module.NetworkSession.clear()
        self.provider = self.items.PandapowerDataItemProvider()

    def tearDown(self):
        self.session_module.NetworkSession.clear()

    def _top_level(self, path):
        root = self.provider.createDataItem(path, None)
        return {child.name(): child for child in root.createChildren()}

    def test_only_populated_input_tables_are_listed(self):
        """Empty input tables are hidden so the tree stays readable.

        A pandapower 3 net defines ~33 input tables; a typical grid fills
        fewer than ten.
        """
        import pandas as pd

        children = self._top_level(self.with_results)

        empty = [name for name in dir(self.net)
                 if not name.startswith('_')
                 and not name.startswith('res_')
                 and isinstance(getattr(self.net, name, None), pd.DataFrame)
                 and len(getattr(self.net, name)) == 0]

        self.assertGreater(len(empty), 0, 'fixture should have empty tables')
        for name in empty:
            self.assertNotIn(name, children)

    def test_populated_tables_are_listed(self):
        """The tables the network actually uses are all present."""
        children = self._top_level(self.with_results)

        for name in ('bus', 'line', 'trafo', 'load', 'switch'):
            self.assertIn(name, children)

    def test_results_group_is_last(self):
        """Results sit in their own group at the end of the tree."""
        root = self.provider.createDataItem(self.with_results, None)
        names = [child.name() for child in root.createChildren()]

        self.assertEqual(names[-1], 'Results')

    def test_bus_splits_into_voltage_levels(self):
        """bus expands into one child per voltage level."""
        children = self._top_level(self.with_results)
        bus = children['bus']

        self.assertIsInstance(bus, self.items.PandapowerLevelledTableItem)

        levels = bus.createChildren()
        self.assertEqual(len(levels), len(self.net.bus.vn_kv.unique()))
        for item in levels:
            self.assertIn('kV', item.name())

    def test_attribute_only_table_is_a_leaf(self):
        """trafo has no levels, so it is directly addable."""
        children = self._top_level(self.with_results)

        self.assertIsInstance(children['trafo'],
                              self.items.PandapowerTableItem)

    def test_leaf_yields_a_mime_uri(self):
        """A leaf can be dragged onto the canvas."""
        children = self._top_level(self.with_results)
        item = children['bus'].createChildren()[0]

        uris = item.mimeUris()
        self.assertEqual(len(uris), 1)
        self.assertEqual(uris[0].providerKey, 'PandapowerProvider')
        self.assertIn('table=', uris[0].uri)

    def test_populated_result_table_is_enabled(self):
        """A result table with rows can be opened."""
        children = self._top_level(self.with_results)
        results = {item.name(): item
                   for item in children['Results'].createChildren()}

        self.assertTrue(results['res_bus'].enabled)
        self.assertTrue(results['res_bus'].hasDragEnabled())

    def test_empty_result_table_is_listed_but_disabled(self):
        """An empty res_* stays visible, greyed, to advertise the power flow."""
        children = self._top_level(self.without_results)
        results = {item.name(): item
                   for item in children['Results'].createChildren()}

        self.assertIn('res_bus', results)
        self.assertFalse(results['res_bus'].enabled)
        self.assertFalse(results['res_bus'].hasDragEnabled())
        self.assertEqual(results['res_bus'].mimeUris(), [])

    def test_expanding_does_not_leak_a_session(self):
        """Building children releases the session it borrowed.

        Otherwise merely browsing a directory would pin every network in it
        into memory for the rest of the QGIS session.
        """
        root = self.provider.createDataItem(self.with_results, None)
        root.createChildren()

        self.assertEqual(self.session_module.NetworkSession.all_sessions(), [])


if __name__ == '__main__':
    unittest.main()
