# coding=utf-8
"""Tests for the commit-based write policy.

Edits mutate the shared network and only reach disk when the user commits the
layer's edit buffer (docs/dataprovider_v2_plan.md section 3.7). This replaced a
per-change async save whose overlapping writes were a standing source of bugs.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.
"""

import json
import os
import sys
import tempfile
import time
import unittest

from qgis.core import (QgsGeometry, QgsPointXY, QgsProject,
                       QgsProviderRegistry)

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


class AsyncMachineryRemovedTest(unittest.TestCase):
    """The per-change save machinery must be gone, not merely bypassed."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(PLUGIN_DIR, 'pandapower_provider.py'),
                  encoding='utf-8') as handle:
            cls.source = handle.read()

    def test_save_state_flags_are_gone(self):
        """No provider-level save-in-progress state remains."""
        self.assertNotIn('_save_in_progress', self.source)
        self.assertNotIn('_save_thread', self.source)

    def test_async_save_methods_are_gone(self):
        """The three async writers were removed."""
        for name in ('update_geodata_in_json_async',
                     'update_attributes_in_json_async',
                     'update_entire_network_in_json_async'):
            self.assertNotIn(name, self.source)

    def test_no_save_threads_remain(self):
        """No QThread subclass is left in the provider."""
        self.assertNotIn('QThread', self.source)

    def test_the_save_race_warning_is_gone(self):
        """The "previous save is still running" path no longer exists."""
        self.assertNotIn('still running', self.source)


@unittest.skipIf(os.environ.get('SKIP_PANDAPOWER_TESTS'),
                 'pandapower tests disabled')
class CommitWriteTest(unittest.TestCase):
    """Test when edits reach disk, and when they must not."""

    @classmethod
    def setUpClass(cls):
        metadata_module = load_plugin_module('ppprovider_metadata')
        registry = QgsProviderRegistry.instance()
        if 'PandapowerProvider' not in registry.providerList():
            registry.registerProvider(
                metadata_module.PandapowerProviderMetadata())

        cls.factory = load_plugin_module('pandapower_layer_factory')
        cls.session_module = load_plugin_module('network_session')

    def setUp(self):
        import pandapower as pp
        import pandapower.networks as ppn

        self.session_module.NetworkSession.clear()
        QgsProject.instance().removeAllMapLayers()

        self.directory = tempfile.mkdtemp()
        self.path = os.path.join(self.directory, 'net.json')
        pp.to_json(ppn.mv_oberrhein(), self.path)

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()
        self.session_module.NetworkSession.clear()

    def _bus_layer(self):
        """Create and register a bus layer for the temp network."""
        layer = self.factory.create_layer(
            self.path, 'bus', level=20.0, epsg=4326)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _first_bus_xy(self, path=None):
        """Read the first bus coordinate straight from the file on disk."""
        import pandapower as pp

        net = pp.from_json(path or self.path)
        return tuple(json.loads(net.bus.geo.iloc[0])['coordinates'])

    def _backups(self):
        """List backup files sitting next to the network."""
        return [name for name in os.listdir(self.directory)
                if name.endswith('.bak')]

    def test_uncommitted_edit_does_not_touch_the_file(self):
        """An edit sitting in the layer buffer never reaches disk."""
        before = self._first_bus_xy()
        layer = self._bus_layer()
        fid = next(layer.getFeatures()).id()

        layer.startEditing()
        layer.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(9.99, 49.99)))

        self.assertEqual(self._first_bus_xy(), before)

    def test_commit_writes_the_edit(self):
        """Committing the buffer writes the network once."""
        layer = self._bus_layer()
        fid = next(layer.getFeatures()).id()

        layer.startEditing()
        layer.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(9.99, 49.99)))
        self.assertTrue(layer.commitChanges())

        x, y = self._first_bus_xy()
        self.assertAlmostEqual(x, 9.99)
        self.assertAlmostEqual(y, 49.99)

    def test_session_is_clean_after_commit(self):
        """A successful write clears the dirty flag."""
        layer = self._bus_layer()
        fid = next(layer.getFeatures()).id()

        layer.startEditing()
        layer.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(9.9, 49.9)))
        layer.commitChanges()

        self.assertFalse(layer.dataProvider().session.dirty)

    def test_rollback_leaves_the_file_alone(self):
        """Discarding an edit writes nothing at all."""
        before = self._first_bus_xy()
        layer = self._bus_layer()
        fid = next(layer.getFeatures()).id()

        layer.startEditing()
        layer.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(1.0, 2.0)))
        layer.rollBack()

        self.assertEqual(self._first_bus_xy(), before)
        self.assertEqual(self._backups(), [])

    def test_commit_writes_a_backup_of_the_previous_file(self):
        """The pre-edit file is kept aside before being overwritten."""
        before = self._first_bus_xy()
        layer = self._bus_layer()
        fid = next(layer.getFeatures()).id()

        layer.startEditing()
        layer.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(9.99, 49.99)))
        layer.commitChanges()

        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(
            self._first_bus_xy(os.path.join(self.directory, backups[0])),
            before)

    def test_two_layers_of_one_file_write_only_once(self):
        """Sibling commits coalesce; the file is not written twice.

        The first write clears the dirty flag, so any further commit in the
        same action finds a clean session and skips.
        """
        bus = self._bus_layer()
        line = self.factory.create_layer(
            self.path, 'line', level=20.0, epsg=4326)
        QgsProject.instance().addMapLayer(line)
        self.assertIs(bus.dataProvider().session, line.dataProvider().session)

        writes = []
        original = self.session_module.NetworkSession.write

        def counting_write(session_self, backup=True):
            writes.append(session_self.path)
            return original(session_self, backup=backup)

        self.session_module.NetworkSession.write = counting_write
        try:
            fid = next(bus.getFeatures()).id()
            bus.startEditing()
            bus.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(8.5, 48.5)))
            bus.commitChanges()

            line.startEditing()
            line.commitChanges()
        finally:
            self.session_module.NetworkSession.write = original

        self.assertEqual(len(writes), 1)

    def test_external_change_is_detected_before_writing(self):
        """A file rewritten behind our back is noticed."""
        layer = self._bus_layer()
        session = layer.dataProvider().session
        self.assertFalse(session.file_changed_externally())

        time.sleep(0.01)
        os.utime(self.path, (time.time() + 5, time.time() + 5))

        self.assertTrue(session.file_changed_externally())

    def test_refusing_the_overwrite_prompt_keeps_the_file(self):
        """Declining the prompt leaves both the file and the edit intact."""
        layer = self._bus_layer()
        provider = layer.dataProvider()
        session = provider.session

        os.utime(self.path, (time.time() + 5, time.time() + 5))
        marker = self._first_bus_xy()
        provider._confirm_overwrite_external_change = lambda: False

        fid = next(layer.getFeatures()).id()
        layer.startEditing()
        layer.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(3.0, 4.0)))
        layer.commitChanges()

        self.assertEqual(self._first_bus_xy(), marker)
        self.assertTrue(session.dirty)

    def test_attribute_edits_take_the_same_path(self):
        """Attribute changes are also buffered until commit."""
        layer = self._bus_layer()
        fid = next(layer.getFeatures()).id()
        index = layer.fields().indexFromName('name')

        layer.startEditing()
        layer.changeAttributeValue(fid, index, 'RENAMED BY TEST')

        with open(self.path, encoding='utf-8') as handle:
            self.assertNotIn('RENAMED BY TEST', handle.read())

        layer.commitChanges()

        with open(self.path, encoding='utf-8') as handle:
            self.assertIn('RENAMED BY TEST', handle.read())


if __name__ == '__main__':
    unittest.main()
