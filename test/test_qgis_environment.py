# coding=utf-8
"""Tests that the QGIS environment the plugin needs is present.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""
__author__ = 'tim@linfiniti.com'
__date__ = '20/01/2011'
__copyright__ = ('Copyright 2012, Australia Indonesia Facility for '
                 'Disaster Reduction')

import unittest

from qgis.core import QgsCoordinateReferenceSystem, QgsProviderRegistry

from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class QGISTest(unittest.TestCase):
    """Test the QGIS Environment"""

    def test_qgis_environment(self):
        """QGIS environment has the providers the plugin relies on.

        Only 'gdal' and 'ogr' are checked. The plugin does not use 'postgres',
        and that provider is absent from minimal OSGeo4W installations.
        """
        registry = QgsProviderRegistry.instance()
        self.assertIn('gdal', registry.providerList())
        self.assertIn('ogr', registry.providerList())

    def test_projection(self):
        """QGIS resolves the EPSG codes the plugin uses for network geodata.

        4326 is the default CRS assumed by PandapowerProvider when a network
        carries no explicit EPSG code.
        """
        crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        self.assertTrue(crs.isValid())
        self.assertEqual(crs.authid(), 'EPSG:4326')

    def test_projected_crs_round_trip(self):
        """A projected CRS survives a WKT round trip.

        Network geodata is frequently stored in a metric CRS such as
        EPSG:25832 (ETRS89 / UTM zone 32N) rather than in degrees.
        """
        crs = QgsCoordinateReferenceSystem.fromEpsgId(25832)
        self.assertTrue(crs.isValid())

        restored = QgsCoordinateReferenceSystem()
        restored.createFromWkt(crs.toWkt())
        self.assertTrue(restored.isValid())
        self.assertEqual(restored.authid(), 'EPSG:25832')


if __name__ == '__main__':
    unittest.main()
