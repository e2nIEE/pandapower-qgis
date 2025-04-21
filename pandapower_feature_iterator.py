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

        # 좌표계 변환 설정 - 판다파워에는 필요없을듯
        self._transform = QgsCoordinateTransform()
        if (request.destinationCrs().isValid() and
            request.destinationCrs() != source.get_provider().crs()):
            self._transform = QgsCoordinateTransform(
                self._provider().crs(),         # 원본 좌표계
                request.destinationCrs(),       # 목적지 좌표계
                request.transformContext()      # 변환 컨텍스트
            )

        # Prepare geometry data
        # self.df_geodata = getattr(self._provider.net, f'{self._provider.network_type}_geodata')
        self.df_geodata = getattr(self._provider.net, f'{self._provider.network_type}').geo
        #self.df_geodata2 = self._provider.net.bus.geo
        #print("current network type: ", self._provider.network_type, "\n")
        #print(".geo head: ", self.df_geodata.head, "\n")
        #print("net.bus.geo head", self.df_geodata2.head, "\n")

        # Prepare main dataframe
        self.df = self._provider.df
        #print("self.df .head", self.df, "\n\n\n")

        # 유효성 검사는 추후 별도의 메서드나 플래그로 처리
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
            #print("network type: ", self._provider.network_type, "\n")
            #raw_geo = self.df_geodata.loc[idx]
            #print(f"Raw data for idx {idx}: {raw_geo}\n")
            row_geo = json.loads(self.df_geodata.loc[idx])
            #print(f"Parsed data structure: {type(row_geo)}, content: {row_geo}\n")
            try:
                if self._provider.network_type in ['bus', 'junction']:
                    if 'coordinates' in row_geo and isinstance(row_geo['coordinates'], list) and len(row_geo['coordinates']) >= 2:
                        # Create point geometry
                        #x = row_geo.get('x', 0)
                        #y = row_geo.get('y', 0)
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

                    # 좌표계 변환 적용
                    if has_valid_geometry and not self._transform.isShortCircuited():
                        self.geometryToDestinationCrs(feature, self._transform)

                    # Spatial filter to select features from the layer
                    # 라인 레이어에 대한 공간 필터 적용
                    filter_rect = self.filterRectToSourceCrs(self._transform)
                    if not filter_rect.isNull():
                        # 공간 연산을 위해 filter_rect를 qgsgeometry 객체로 변환
                        filter_geom = QgsGeometry.fromRect(filter_rect)
                        # 교차 여부 확인
                        if not feature.geometry().intersects(filter_geom):
                            # 교차하지 않으면 거리 기반 근접성 확인
                            distance = feature.geometry().distance(filter_geom)
                            # 허용 오차 설정 (지도 스케일에 따라 조정 필요)
                            tolerance = 0.00001  # 약 1m 정도의 허용 오차
                            # 오차 범위를 넘으면 건너뜀
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
            attributes.append(value)
        feature.setAttributes(attributes)

        # Set feature id
        feature.setId(idx) # 추측: df의 index = pp_index, 즉 둘은 동일하며 비연속, 따라서 id는 유용

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