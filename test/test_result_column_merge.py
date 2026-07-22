# coding=utf-8
"""Guard the res_* merge that layer styling depends on.

Renderers colour buses by ``vm_pu`` and lines by ``loading_percent``
(see renderer_utils.create_power_renderer). Those columns only exist on a
bus/line layer because merge_df() folds the matching ``res_*`` table into it.

Removing that merge would break colouring **silently** — the layer still loads,
the renderer still applies, every rule just stops matching and the map goes
blank or single-coloured. Nothing raises. These tests make that failure loud.

See docs/dataprovider_v2_plan.md section 5.2 and the risk noted in section 6.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.
"""

import os
import sys
import tempfile
import unittest

from qgis.core import QgsProviderRegistry, QgsWkbTypes

from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()

PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'pandapower-qgis'))

# Columns the renderers reference. If a refactor drops these from the layer,
# styling breaks without any error being raised.
BUS_STYLING_COLUMN = 'vm_pu'
LINE_STYLING_COLUMN = 'loading_percent'


def load_plugin_module(name):
    """Import a module from the plugin directory by name.

    :param name: Module name inside the plugin package, e.g. 'network_session'.
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


@unittest.skipIf(os.environ.get('SKIP_PANDAPOWER_TESTS'),
                 'pandapower tests disabled')
class ResultColumnMergeTest(unittest.TestCase):
    """Test that result columns reach the layers that are styled by them."""

    @classmethod
    def setUpClass(cls):
        import pandapower as pp
        import pandapower.networks as ppn

        metadata_module = load_plugin_module('ppprovider_metadata')
        registry = QgsProviderRegistry.instance()
        if 'PandapowerProvider' not in registry.providerList():
            registry.registerProvider(
                metadata_module.PandapowerProviderMetadata())

        cls.factory = load_plugin_module('pandapower_layer_factory')
        cls.session_module = load_plugin_module('network_session')

        # A calculated network, so the res_* tables are populated.
        cls.net = ppn.mv_oberrhein()
        pp.runpp(cls.net)

        cls.directory = tempfile.mkdtemp()
        cls.path = os.path.join(cls.directory, 'merge_test.json')
        pp.to_json(cls.net, cls.path)

        cls.level = sorted(cls.net.bus.vn_kv.unique())[0]

    def setUp(self):
        self.session_module.NetworkSession.clear()

    def tearDown(self):
        self.session_module.NetworkSession.clear()

    def _field_names(self, layer):
        return [field.name() for field in layer.fields()]

    # -- the merge itself -------------------------------------------------

    def test_bus_layer_carries_its_styling_column(self):
        """A bus layer exposes vm_pu, which its renderer filters on."""
        layer = self.factory.create_layer(
            self.path, 'bus', level=self.level, epsg=4326)

        self.assertTrue(layer.isValid())
        self.assertIn(BUS_STYLING_COLUMN, self._field_names(layer))

    def test_line_layer_carries_its_styling_column(self):
        """A line layer exposes loading_percent, which its renderer filters on."""
        layer = self.factory.create_layer(
            self.path, 'line', level=self.level, epsg=4326)

        self.assertTrue(layer.isValid())
        self.assertIn(LINE_STYLING_COLUMN, self._field_names(layer))

    def test_styling_columns_hold_real_values(self):
        """The merged columns are populated, not present-but-empty.

        A left join on mismatched indices would keep the column and fill it
        with NULL, which passes a name-only check but still breaks colouring.
        """
        layer = self.factory.create_layer(
            self.path, 'line', level=self.level, epsg=4326)

        feature = next(layer.getFeatures(), None)
        self.assertIsNotNone(feature)

        value = feature[LINE_STYLING_COLUMN]
        self.assertIsNotNone(value)
        self.assertNotEqual(str(value), 'NULL')
        self.assertGreater(float(value), 0.0)

    def test_input_columns_survive_the_merge(self):
        """Merging results must not displace the table's own columns."""
        layer = self.factory.create_layer(
            self.path, 'line', level=self.level, epsg=4326)
        names = self._field_names(layer)

        self.assertIn('length_km', names)
        self.assertIn('from_bus', names)

    def test_no_column_name_collision_between_table_and_results(self):
        """A name shared by a table and its res_* twin would be masked.

        merge_df() merges with suffixes=('', '_res'), so a collision silently
        renames the result column and any renderer referencing the bare name
        reads the input value instead. Assert the collision does not exist.
        """
        for table in ('bus', 'line'):
            input_columns = set(getattr(self.net, table).columns)
            result_columns = set(getattr(self.net, 'res_{}'.format(table)).columns)
            collisions = input_columns & result_columns

            self.assertEqual(
                collisions, set(),
                '{} and res_{} share column(s) {} — the merge would mask '
                'them under a _res suffix'.format(table, table, collisions))

    # -- the separate res_* layers (plan section 5.2) ----------------------

    def test_res_table_also_opens_as_its_own_layer(self):
        """res_* is reachable as a standalone non-spatial table."""
        layer = self.factory.create_layer(self.path, 'res_line', epsg=4326)

        self.assertTrue(layer.isValid())
        self.assertEqual(layer.wkbType(), QgsWkbTypes.NoGeometry)
        self.assertIn(LINE_STYLING_COLUMN, self._field_names(layer))

    def test_both_views_read_one_shared_network(self):
        """The merged column and the res_* layer are two views of one net.

        Neither holds a copy, so results cannot drift between them.
        """
        line = self.factory.create_layer(
            self.path, 'line', level=self.level, epsg=4326)
        res_line = self.factory.create_layer(self.path, 'res_line', epsg=4326)

        self.assertIs(line.dataProvider().net, res_line.dataProvider().net)
        self.assertIs(line.dataProvider().session,
                      res_line.dataProvider().session)


if __name__ == '__main__':
    unittest.main()
