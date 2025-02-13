# standard
from __future__ import (
    annotations,  # used to manage type annotation for method that return Self in Python < 3.11
)

from qgis.core import QgsAbstractFeatureIterator, QgsCoordinateTransform, QgsFeatureRequest, \
    QgsGeometry, QgsPointXY, QgsLineString, QgsFeature
from . import pandapower_feature_source
#from .pandapower_provider import PandapowerProvider

import pandas as pd

class PandapowerFeatureIterator(QgsAbstractFeatureIterator):
    def __init__(self, source: pandapower_feature_source.PandapowerFeatureSource, request: QgsFeatureRequest):
        """
        피처 이터레이터를 초기화합니다. 이 클래스는 판다파워의 데이터프레임을
        QGIS 피처로 변환하는 핵심 로직을 담당합니다.
        """
        super().__init__(request)
        self._provider  = source.get_provider()
        self._request = request
        self._index = 0

        # 좌표계 변환 설정 - 판다파워에는 필요없을듯
        self._transform = QgsCoordinateTransform()
        if (request.destinationCrs().isValid() and
            request.destinationCrs() != source.get_provider().crs()):
            self._transform = QgsCoordinateTransform(
                self._provider().crs(),         # 원본 좌표계
                request.destinationCrs(),       # 목적지 좌표계
                request.transformContext()      # 변환 컨텍스트
            )

        # 지오메트리 데이터 준비
        self.df_geodata = getattr(self._provider.net, f'{self._provider.network_type}_geodata')
        if self.df_geodata is None:
            return False
        self.df_geodata.sort_index(inplace=True)

        # 메인 데이터프레임 준비
        self.df = self._provider.df
        if self.df is None:
            return False
        self.df.sort_index(inplace=True)


    def fetchFeature(self, feature: QgsFeature) -> bool:
        """
        Transform one row as QGIS feature and fetch as next feature.
        Return true on success.
        :param feature: Next feature
        :type feature: QgsFeature
        :return: True if success
        :rtype: bool
        """
        # 더 이상 처리할 행이 없으면 종료
        if self._index >= len(self.df):
            return False

        # 현재 행 가져오기
        idx = self.df.index[self._index]
        row = self.df.iloc[self._index]

        # 피처 기본 설정
        feature.setFields(self._provider.fields())
        feature.setValid(True)

        # 지오메트리 설정
        if idx in self.df_geodata.index:
            row_geo = self.df_geodata.loc[idx]

            if self._provider.network_type in ['bus', 'junction']:
                # 포인트 지오메트리 생성
                x = row_geo.get('x', 0)
                y = row_geo.get('y', 0)
                geometry = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                feature.setGeometry(geometry)
                if x == 0 or y == 0:
                    print(f"Warning: No coordinates found for {self._provider.network_type} index {idx}")

            elif self._provider.network_type in ['line', 'pipe']:
                # 라인 지오메트리 생성
                coords = row_geo.get('coords', [])
                if coords:
                    points = [QgsPointXY(x, y) for x, y in coords]
                    geometry = QgsGeometry(QgsLineString(points))
                    feature.setGeometry(geometry)
                else:
                    print(f"Warning: No coordinates found for {self._provider.network_type} index {idx}")

            # 좌표계 변환 적용
            if not self._transform.isShortCircuited():
                self.geometryToDestinationCrs(feature, self._transform)

        # 피처에 속성값 설정
        attributes = []
        for field in self._provider.fields():
            value = row.get(field.name(), None)
            if pd.isna(value):
                value = None
            attributes.append(value)
        feature.setAttributes(attributes)

        # 피처 ID 설정
        feature.setId(idx) # 추측: df의 index = pp_index, 즉 둘은 동일하며 비연속, 따라서 id는 유용

        # 인덱스 증가
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
        """이터레이터를 처음으로 되돌립니다"""
        self._index = 0
        return True


    def close(self) -> bool:
        """이터레이터를 종료하고 정리합니다"""
        self._index = -1
        return True