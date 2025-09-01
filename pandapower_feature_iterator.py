# standard
from __future__ import (
    annotations,  # used to manage type annotation for method that return Self in Python < 3.11
)

from qgis.core import QgsAbstractFeatureIterator, QgsCoordinateTransform, QgsFeatureRequest, \
    QgsGeometry, QgsPointXY, QgsLineString, QgsFeature
from . import pandapower_feature_source
#from .pandapower_provider import PandapowerProvider

import pandas as pd
import numpy as np
import json

class PandapowerFeatureIterator(QgsAbstractFeatureIterator):
    def __init__(self, source: pandapower_feature_source.PandapowerFeatureSource, request: QgsFeatureRequest):
        """
        Initialize the feature iterator.
        This class is responsible for the core logic of converting a pandapower dataframe into QGIS features.
        """
        super().__init__(request)
        self._provider  = source.get_provider()
        self._request = request
        self._index = 0
        self._is_valid = False

        # Coordinate transformation settings - might not be needed for pandapower
        self._transform = QgsCoordinateTransform()
        if (request.destinationCrs().isValid() and
                request.destinationCrs() != source.get_provider().crs()):
            self._transform = QgsCoordinateTransform(
                self._provider().crs(),  # Source coordinate system
                request.destinationCrs(),  # Destination coordinate system
                request.transformContext()  # Transformation context
            )

        # Prepare geometry data
        # self.df_geodata = getattr(self._provider.net, f'{self._provider.network_type}_geodata')
        self.df_geodata = getattr(self._provider.net, f'{self._provider.network_type}').geo

        # Prepare main dataframe
        self.df = self._provider.df

        # Handle validation later via a separate method or flag
        self._is_valid = (self.df_geodata is not None and self.df is not None)

        if self._is_valid:
            self.df_geodata.sort_index(inplace=True)
            self.df.sort_index(inplace=True)
        else:
            print("Warning: Dataframe is empty in PandapowerFeatureIterator.")


    def fetchFeature(self, feature: QgsFeature) -> bool:
        """
        Transform one row as QGIS feature and fetch as next feature.
        Return true on success.
        :param feature: Next feature
        :type feature: QgsFeature
        :return: True if success
        :rtype: bool
        """
        # Exit if there are no more rows to process
        if self._index >= len(self.df):
            return False

        # Get the current row
        idx = self.df.index[self._index]
        row = self.df.iloc[self._index]

        # Feature default settings
        feature.setFields(self._provider.fields())
        feature.setValid(True)

        # Geometry settings
        has_valid_geometry = False
        if idx in self.df_geodata.index:
            row_geo = json.loads(self.df_geodata.loc[idx])
            try:
                if self._provider.network_type in ['bus', 'junction']:
                    if 'coordinates' in row_geo and isinstance(row_geo['coordinates'], list) and len(row_geo['coordinates']) >= 2:
                        # Create point geometry
                        x = row_geo['coordinates'][0]
                        y = row_geo['coordinates'][1]
                        geometry = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                        feature.setGeometry(geometry)
                        has_valid_geometry = (x != 0 or y != 0)
                    else:
                        print(f"Warning: Invalid coordinates structure for {self._provider.network_type} index {idx}")

                    if not has_valid_geometry:
                        print(f"Warning: No coordinates found for {self._provider.network_type} index {idx}")

                    # Apply coordinate transformation
                    if has_valid_geometry and not self._transform.isShortCircuited():
                        self.geometryToDestinationCrs(feature, self._transform)

                    # Spatial filter to select features from the layer
                    # Apply spatial filter to point layer
                    filter_rect = self.filterRectToSourceCrs(self._transform)
                    if has_valid_geometry and not filter_rect.isNull():
                        # Check if filter_rect intersects with feature.geometry
                        # skip if they do not intersect
                        if not filter_rect.contains(feature.geometry().asPoint()):
                            self._index += 1
                            return self.fetchFeature(feature)

                if self._provider.network_type in ['line', 'pipe']:
                    # Create line geometry
                    coords = row_geo.get('coordinates', [])
                    if coords:
                        points = [QgsPointXY(x, y) for x, y in coords]
                        geometry = QgsGeometry(QgsLineString(points))
                        feature.setGeometry(geometry)
                        has_valid_geometry = True
                    else:
                        print(f"Warning: No coordinates found for {self._provider.network_type} index {idx}")

                    # Apply CRS transformation
                    if has_valid_geometry and not self._transform.isShortCircuited():
                        self.geometryToDestinationCrs(feature, self._transform)

                    # Spatial filter to select features from the layer
                    # Apply a spatial filter to the line layer.
                    filter_rect = self.filterRectToSourceCrs(self._transform)
                    if not filter_rect.isNull():
                        # Convert filter_rect to QgsGeometry object for spatial operations
                        filter_geom = QgsGeometry.fromRect(filter_rect)
                        # Check intersection
                        if not feature.geometry().intersects(filter_geom):
                            # If no intersection, check distance-based proximity
                            distance = feature.geometry().distance(filter_geom)
                            # Set tolerance (needs adjustment based on map scale)
                            tolerance = 0.00001  # Tolerance of approximately 1m
                            # Skip if beyond tolerance range
                            if distance > tolerance:
                                self._index += 1
                                return self.fetchFeature(feature)
            except Exception as e:
                print(f"Error processing {self._provider.network_type} index {idx}: {str(e)}")

        # Set attribute values for the feature
        attributes = []
        for field in self._provider.fields():
            value = row.get(field.name(), None)
            if pd.isna(value):
                value = None
            elif isinstance(value, (bool, np.bool_)):  # handle numpy.bool_ type of pandas
                value = bool(value)  # Explicit conversion to Python native bool
            elif isinstance(value, (np.integer, int)):  # handle numpy integer types of pandas
                value = int(value)  # Explicit conversion to Python native int
            attributes.append(value)
        feature.setAttributes(attributes)

        # Set feature id
        feature.setId(idx) # df.index = pp_index, not equal to bus_name

        self._index += 1
        return True


    def __next__(self) -> QgsFeature:
        """Returns the next value till current is lower than high"""
        feature = QgsFeature()
        if not self.nextFeature(feature):
            raise StopIteration
        else:
            return feature


    def __iter__(self) -> PandapowerFeatureIterator:
        """Returns self as an iterator object"""
        self._index = 0
        return self


    def rewind(self) -> bool:
        """Reset the iterator to the beginning"""
        self._index = 0
        return True


    def close(self) -> bool:
        """Terminate and clean up the iterator"""
        self._index = -1
        return True