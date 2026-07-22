# coding=utf-8
"""Smoke tests for the pandapower data provider registration.

These tests guard the corrective fixes made in phase 0 of the data provider
rework (see docs/dataprovider_v2_plan.md):

* the provider metadata registers under the expected key,
* ``PandapowerProviderMetadata.icon()`` does not raise (it previously used
  ``os`` and ``QIcon`` without importing them),
* closing a single layer does not deregister the shared provider type.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.
"""

import os
import sys
import unittest

from qgis.core import QgsProviderRegistry
from qgis.PyQt.QtGui import QIcon

from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()

PROVIDER_KEY = 'PandapowerProvider'

# The plugin package lives in the "pandapower-qgis" directory next to "test".
# Its name is not a valid Python identifier, so it is imported by path rather
# than with a plain "import pandapower-qgis".
PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'pandapower-qgis'))


def load_provider_metadata_class():
    """Import PandapowerProviderMetadata from the plugin directory.

    :returns: The PandapowerProviderMetadata class.
    """
    import importlib

    parent = os.path.dirname(PLUGIN_DIR)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    # Register the plugin directory under an importable package alias so the
    # relative imports inside the plugin ("from .pandapower_provider import ...")
    # resolve correctly.
    package = 'pandapower_qgis_plugin'
    if package not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            package,
            os.path.join(PLUGIN_DIR, '__init__.py'),
            submodule_search_locations=[PLUGIN_DIR])
        module = importlib.util.module_from_spec(spec)
        sys.modules[package] = module
        spec.loader.exec_module(module)

    metadata_module = importlib.import_module(
        '{}.ppprovider_metadata'.format(package))
    return metadata_module.PandapowerProviderMetadata


class TestProviderRegistration(unittest.TestCase):
    """Test registration and lifetime of the pandapower provider."""

    @classmethod
    def setUpClass(cls):
        cls.metadata_class = load_provider_metadata_class()
        registry = QgsProviderRegistry.instance()
        if PROVIDER_KEY not in registry.providerList():
            registry.registerProvider(cls.metadata_class())

    def test_provider_is_registered(self):
        """The provider appears in the QGIS provider registry."""
        registry = QgsProviderRegistry.instance()
        self.assertIn(PROVIDER_KEY, registry.providerList())

    def test_provider_metadata_is_retrievable(self):
        """The registered metadata can be fetched back by key."""
        metadata = QgsProviderRegistry.instance().providerMetadata(PROVIDER_KEY)
        self.assertIsNotNone(metadata)

    def test_icon_does_not_raise(self):
        """icon() returns a QIcon instead of raising NameError.

        Regression test: the implementation used os.path and QIcon without
        importing either, so the first call from QGIS raised NameError.
        """
        metadata = self.metadata_class()
        icon = metadata.icon()
        self.assertIsInstance(icon, QIcon)

    def test_uri_round_trip(self):
        """encodeUri and decodeUri are inverse operations."""
        metadata = self.metadata_class()
        parts = {
            'path': 'C:/networks/mv_oberrhein.json',
            'network_type': 'bus',
            'voltage_level': '20.0',
            'epsg': '4326',
        }
        decoded = metadata.decodeUri(metadata.encodeUri(parts))
        self.assertEqual(parts, decoded)

    def test_unload_does_not_deregister_provider_type(self):
        """Unloading one provider instance leaves the registry entry intact.

        Regression test: PandapowerProvider.unload() called
        QgsProviderRegistry.removeProvider(), which removed the shared provider
        type and invalidated every other open pandapower layer.
        """
        import inspect
        import importlib

        provider_module = importlib.import_module(
            'pandapower_qgis_plugin.pandapower_provider')
        source = inspect.getsource(
            provider_module.PandapowerProvider.unload)
        self.assertNotIn('removeProvider', source)

        # The provider type must still be registered afterwards.
        self.assertIn(PROVIDER_KEY,
                      QgsProviderRegistry.instance().providerList())


if __name__ == '__main__':
    unittest.main()
