# coding=utf-8
"""Tests for the pandapower page of the Data Source Manager.

Covers docs/dataprovider_v2_plan.md section 3.1: the entry sits in the database
group, the widget lists a network's tables, and Add emits one layer signal per
selected table with a URI that actually builds a layer.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.
"""

import os
import sys
import tempfile
import unittest

from qgis.core import QgsProviderMetadata, QgsProviderRegistry, QgsVectorLayer
from qgis.gui import QgsSourceSelectProvider
from qgis.PyQt.QtCore import QItemSelectionModel

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


class ProviderMetadataTest(unittest.TestCase):
    """Test that the provider is no longer a generic vector file source."""

    @classmethod
    def setUpClass(cls):
        module = load_plugin_module('ppprovider_metadata')
        cls.metadata = module.PandapowerProviderMetadata()

    def test_capabilities_use_the_right_enum(self):
        """capabilities() returns ProviderMetadataCapability values.

        It previously returned FileBasedUris, which belongs to the unrelated
        ProviderCapability enum returned by providerCapabilities().
        """
        caps = self.metadata.capabilities()

        self.assertTrue(
            caps & QgsProviderMetadata.ProviderMetadataCapability.LayerTypesForUri)

    def test_file_based_uris_moved_to_provider_capabilities(self):
        """FileBasedUris is still declared, in the method it belongs to."""
        self.assertTrue(
            self.metadata.providerCapabilities()
            & QgsProviderMetadata.FileBasedUris)

    def test_no_vector_file_filter_is_contributed(self):
        """The provider does not appear in "Add Vector Layer -> File".

        Advertising "*.json" there made opening a network behave like an
        import, which is what this rework removes.
        """
        self.assertEqual(
            self.metadata.filters(QgsProviderMetadata.FilterType.FilterVector),
            '')


class SourceSelectProviderTest(unittest.TestCase):
    """Test the registry entry itself."""

    @classmethod
    def setUpClass(cls):
        module = load_plugin_module('pandapower_source_select')
        cls.provider = module.PandapowerSourceSelectProvider()

    def test_provider_key_matches_the_data_provider(self):
        """The page creates layers for the pandapower provider."""
        self.assertEqual(self.provider.providerKey(), 'PandapowerProvider')

    def test_entry_is_labelled_pandapower(self):
        """The list entry is named for the user, not for the code."""
        self.assertEqual(self.provider.text(), 'pandapower')

    def test_entry_sorts_into_the_database_group(self):
        """The entry sits with PostgreSQL, SAP HANA and Oracle."""
        ordering = self.provider.ordering()

        self.assertGreater(ordering,
                           QgsSourceSelectProvider.OrderDatabaseProvider)
        self.assertLess(ordering, QgsSourceSelectProvider.OrderOtherProvider)

    def test_entry_has_an_icon(self):
        """The list entry is not blank."""
        self.assertFalse(self.provider.icon().isNull())


@unittest.skipIf(os.environ.get('SKIP_PANDAPOWER_TESTS'),
                 'pandapower tests disabled')
class SourceSelectWidgetTest(unittest.TestCase):
    """Test the widget that lists tables and emits the add signal."""

    @classmethod
    def setUpClass(cls):
        import pandapower as pp
        import pandapower.networks as ppn

        metadata_module = load_plugin_module('ppprovider_metadata')
        registry = QgsProviderRegistry.instance()
        if 'PandapowerProvider' not in registry.providerList():
            registry.registerProvider(
                metadata_module.PandapowerProviderMetadata())

        cls.module = load_plugin_module('pandapower_source_select')
        cls.session_module = load_plugin_module('network_session')

        cls.directory = tempfile.mkdtemp()
        cls.net = ppn.mv_oberrhein()
        cls.path = os.path.join(cls.directory, 'oberrhein.json')
        pp.to_json(cls.net, cls.path)

        cls.decoy = os.path.join(cls.directory, 'decoy.json')
        with open(cls.decoy, 'w') as handle:
            handle.write('{"type": "FeatureCollection"}')

    def setUp(self):
        self.session_module.NetworkSession.clear()
        self.widget = self.module.PandapowerSourceSelectWidget()

    def tearDown(self):
        self.session_module.NetworkSession.clear()

    def _select_rows(self, *rows):
        """Select the given listing rows, as ctrl-click would."""
        model = self.widget.table.selectionModel()
        model.clearSelection()
        for row in rows:
            model.select(
                self.widget.table.model().index(row, 0),
                QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def test_lists_the_tables_of_a_network(self):
        """Loading a network fills the listing."""
        self.assertTrue(self.widget.load_network(self.path))
        self.assertGreater(len(self.widget.rows), 0)

    def test_geometry_tables_are_listed_once_per_level(self):
        """bus appears once per voltage level, as in the Browser tree."""
        self.widget.load_network(self.path)

        bus_rows = [row for row in self.widget.rows if row['table'] == 'bus']
        self.assertEqual(len(bus_rows), len(self.net.bus.vn_kv.unique()))

    def test_per_level_counts_add_up_to_the_whole_table(self):
        """The listed feature counts describe a partition of the table."""
        self.widget.load_network(self.path)

        bus_rows = [row for row in self.widget.rows if row['table'] == 'bus']
        self.assertEqual(sum(row['features'] for row in bus_rows),
                         len(self.net.bus))

    def test_attribute_only_tables_are_listed(self):
        """Non-spatial tables can be opened from here too."""
        self.widget.load_network(self.path)

        names = [row['table'] for row in self.widget.rows]
        self.assertIn('trafo', names)

    def test_rejects_a_json_that_is_not_a_network(self):
        """A plain GeoJSON is refused rather than half-loaded."""
        self.assertFalse(self.widget.load_network(self.decoy))
        self.assertEqual(self.widget.rows, [])

    def test_rejects_a_missing_file(self):
        """A vanished path is refused without raising."""
        missing = os.path.join(self.directory, 'nope.json')

        self.assertFalse(self.widget.load_network(missing))

    def test_listing_does_not_leak_a_session(self):
        """Listing releases the session it borrowed.

        Otherwise merely browsing networks in the dialog would pin each one
        into memory for the rest of the QGIS session.
        """
        self.widget.load_network(self.path)

        self.assertEqual(self.session_module.NetworkSession.all_sessions(), [])

    def test_add_ungrouped_emits_one_signal_per_selected_row(self):
        """With grouping off, Add emits a layer signal for each selection."""
        self.widget.load_network(self.path)
        self.widget.group_checkbox.setChecked(False)
        emitted = []
        self.widget.addVectorLayer.connect(
            lambda uri, name, key: emitted.append((uri, name, key)))

        self._select_rows(0, 1)
        self.widget.addButtonClicked()

        self.assertEqual(len(emitted), 2)

    def test_emitted_uri_builds_a_valid_layer(self):
        """What Add emits is directly usable as a layer source."""
        self.widget.load_network(self.path)
        self.widget.group_checkbox.setChecked(False)
        emitted = []
        self.widget.addVectorLayer.connect(
            lambda uri, name, key: emitted.append((uri, name, key)))

        self._select_rows(0)
        self.widget.addButtonClicked()

        uri, name, key = emitted[0]
        self.assertEqual(key, 'PandapowerProvider')

        layer = QgsVectorLayer(uri, name, key)
        self.assertTrue(layer.isValid())
        self.assertGreater(layer.featureCount(), 0)

    def test_add_grouped_places_layers_in_a_named_group(self):
        """With grouping on, Add puts the layers in a group per network."""
        from qgis.core import QgsProject

        QgsProject.instance().removeAllMapLayers()
        root = QgsProject.instance().layerTreeRoot()
        for group in root.findGroups():
            root.removeChildNode(group)

        self.widget.load_network(self.path)
        self.assertTrue(self.widget.group_checkbox.isChecked())

        self._select_rows(0, 1)
        self.widget.addButtonClicked()

        expected = os.path.basename(self.path).rsplit('.', 1)[0]
        group = root.findGroup(expected)
        self.assertIsNotNone(group)
        self.assertEqual(len(group.findLayers()), 2)

        QgsProject.instance().removeAllMapLayers()

    def test_add_selected_button_adds_every_selected_table(self):
        """One click on "Add selected" adds the whole selection.

        Regression guard: the only add triggers used to be the dialog's own
        Add button and a double-click, and a double-click collapses the
        selection to the clicked row first — so a multi-row selection could
        only ever be added one layer at a time.
        """
        from qgis.core import QgsProject

        QgsProject.instance().removeAllMapLayers()
        root = QgsProject.instance().layerTreeRoot()
        for group in list(root.findGroups()):
            root.removeChildNode(group)

        self.widget.load_network(self.path)
        self.widget.table.selectAll()
        selected = len(self.widget.selected_rows())
        self.assertGreater(selected, 1)

        self.widget.add_button.click()

        self.assertEqual(len(QgsProject.instance().mapLayers()), selected)
        QgsProject.instance().removeAllMapLayers()

    def test_double_click_adds_only_the_clicked_row(self):
        """Double-clicking adds one table, not the whole selection."""
        from qgis.core import QgsProject

        QgsProject.instance().removeAllMapLayers()
        self.widget.load_network(self.path)
        self.widget.table.selectAll()

        index = self.widget.table.model().index(0, 0)
        self.widget._on_row_double_clicked(index)

        self.assertEqual(len(QgsProject.instance().mapLayers()), 1)
        QgsProject.instance().removeAllMapLayers()

    def test_empty_result_tables_cannot_be_selected(self):
        """A res_* table with no rows is greyed out, so Add never opens it."""
        self.widget.load_network(self.path)

        self.widget.table.selectAll()
        selected = {row['table'] for row in self.widget.selected_rows()}

        for row in self.widget.rows:
            if row['table'].startswith('res_') and row['features'] == 0:
                self.assertNotIn(row['table'], selected)

    def test_add_without_a_selection_emits_nothing(self):
        """Pressing Add with nothing selected is a no-op, not an error."""
        self.widget.load_network(self.path)
        emitted = []
        self.widget.addVectorLayer.connect(
            lambda *args: emitted.append(args))

        self.widget.table.clearSelection()
        self.widget.addButtonClicked()

        self.assertEqual(emitted, [])

    def test_opened_networks_are_remembered(self):
        """The file is offered again next time the dialog opens."""
        self.widget.load_network(self.path)

        recent = self.module.recent_networks()
        self.assertTrue(any(os.path.normcase(entry) == os.path.normcase(self.path)
                            for entry in recent))


if __name__ == '__main__':
    unittest.main()
