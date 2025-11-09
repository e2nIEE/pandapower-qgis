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
        Initialize the feature iterator for converting pandapower dataframes to QGIS features.
        Args:
            source: PandapowerFeatureSource containing provider and network data
            request: QgsFeatureRequest specifying filtering and transformation requirements
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
        Fetch the next feature from the pandapower dataframe and convert it to QGIS format.
        Handles geometry creation for points (bus/junction) and lines (line/pipe) with coordinate
        transformations and spatial filtering.
        Args:
            feature: QgsFeature object to populate with data
        Returns:
            bool: True if feature was successfully fetched, False if no more features available
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
            geo_str = self.df_geodata.loc[idx]
            # Check if geo data exists (not None and not NaN) - simbench may have no line.geo
            geo_exists = geo_str is not None and not pd.isna(geo_str)

            try:
                if self._provider.network_type in ['bus', 'junction']:
                    if geo_exists:
                        row_geo = json.loads(geo_str)
                        if 'coordinates' in row_geo and isinstance(row_geo['coordinates'], list) and len(row_geo['coordinates']) >= 2:
                            # Create point geometry
                            x = row_geo['coordinates'][0]
                            y = row_geo['coordinates'][1]
                            geometry = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                            feature.setGeometry(geometry)
                            has_valid_geometry = (x != 0 or y != 0)
                        else:
                            print(f"Warning: Invalid coordinates structure for {self._provider.network_type} index {idx}")
                    else:
                        print(f"Warning: No geo data found for {self._provider.network_type} index {idx}")

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

                elif self._provider.network_type in ['line', 'pipe']:
                    # Process line/pipe geometry
                    coords = None

                    if geo_exists:
                        # Case 1: line geo data exists (like mv_oberrhein.json)
                        row_geo = json.loads(geo_str)
                        coords = row_geo.get('coordinates', [])
                        if not coords:
                            print(
                                f"Warning: Empty coordinates in geo data for {self._provider.network_type} index {idx}")
                    else:
                        # Case 2: no line geo data (SimBench format) - auto-generate straight line
                        # Determine the bus column names based on network type
                        if self._provider.network_type == 'line':
                            from_node = 'from_bus'
                            to_node = 'to_bus'
                            bus_table = 'bus'
                        else:  # pipe
                            from_node = 'from_junction'
                            to_node = 'to_junction'
                            bus_table = 'junction'

                        # Get from and to bus/junction indices
                        from_bus_idx = row[from_node]
                        to_bus_idx = row[to_node]

                        # Access bus/junction geodata from the network
                        bus_geodata = getattr(self._provider.net, bus_table).geo

                        # Check if both buses exist in geodata
                        if from_bus_idx in bus_geodata.index and to_bus_idx in bus_geodata.index:
                            from_geo_str = bus_geodata.loc[from_bus_idx]
                            to_geo_str = bus_geodata.loc[to_bus_idx]

                            # Parse bus coordinates
                            if from_geo_str and not pd.isna(from_geo_str) and to_geo_str and not pd.isna(to_geo_str):
                                from_geo = json.loads(from_geo_str)
                                to_geo = json.loads(to_geo_str)

                                # Create straight line coordinates
                                coords = [
                                    from_geo['coordinates'],
                                    to_geo['coordinates']
                                ]
                            else:
                                print(
                                    f"Warning: Missing bus geo data for {self._provider.network_type} index {idx} (from_bus={from_bus_idx}, to_bus={to_bus_idx})")
                        else:
                            print(
                                f"Warning: Bus not found in geodata for {self._provider.network_type} index {idx} (from_bus={from_bus_idx}, to_bus={to_bus_idx})")

                    # Create line geometry if we have coordinates
                    if coords and len(coords) >= 2:
                        points = [QgsPointXY(x, y) for x, y in coords]
                        geometry = QgsGeometry(QgsLineString(points))
                        feature.setGeometry(geometry)
                        has_valid_geometry = True
                    else:
                        print(f"Warning: Could not create line geometry for {self._provider.network_type} index {idx}")

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
        """
        Return the next QgsFeature in the iteration sequence.
        Returns:
            QgsFeature: Next feature in the dataset
        Raises:
            StopIteration: When no more features are available
        """
        feature = QgsFeature()
        if not self.nextFeature(feature):
            raise StopIteration
        else:
            return feature


    def __iter__(self) -> PandapowerFeatureIterator:
        """
        Return self as an iterator object and reset index to beginning.
        Returns:
            PandapowerFeatureIterator: Self reference for iteration protocol
        """
        self._index = 0
        return self


    def rewind(self) -> bool:
        """
        Reset the iterator index to the beginning of the dataset.
        Returns:
            bool: True indicating successful reset
        """
        self._index = 0
        return True


    def close(self) -> bool:
        """
        Terminate the iterator and clean up resources by setting index to invalid state.
        Returns:
            bool: True indicating successful cleanup
        """
        self._index = -1
        return True
