# 2. version von ppprovider

from qgis.core import QgsVectorDataProvider, QgsVectorLayer, QgsFeature, QgsField, QgsFields, \
    QgsGeometry, QgsPointXY, QgsLineString, QgsWkbTypes, QgsProject, QgsCoordinateReferenceSystem, \
    QgsFeatureRequest, QgsFeatureIterator, QgsFeatureSource, QgsAbstractFeatureSource, QgsFeatureSink, \
    QgsDataProvider, QgsProviderRegistry, QgsRectangle
from qgis.PyQt.QtCore import QMetaType
import json
import pandas as pd
import pandapower as pp
import pandapipes as ppi
from . import pandapower_feature_iterator, pandapower_feature_source
from .network_container import NetworkContainer


def convert_dtype_to_qmetatype(dtype):
    """
    Converts a pandas data type (dtype) to a corresponding Qt data type (QMetatype).

    :param dtype: The pandas data type to convert.
    :type dtype: pandas dtype
    :return: The corresponding QMetaType type.
    :rtype: QMetaType
    """
    if pd.api.types.is_integer_dtype(dtype):
        return QMetaType.Int
    elif pd.api.types.is_unsigned_integer_dtype(dtype):
        return QMetaType.UInt
    elif pd.api.types.is_float_dtype(dtype):
        return QMetaType.Double
    elif pd.api.types.is_bool_dtype(dtype):
        return QMetaType.Bool
    elif pd.api.types.is_string_dtype(dtype):
        return QMetaType.QString
    elif pd.api.types.is_object_dtype(dtype):   # object is string?
        return QMetaType.QString
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return QMetaType.QDateTime
    else:
        print("Unexpected dtype detected. Add it or check if it is not available.")
        return QMetaType.Invalid


class PandapowerProvider(QgsVectorDataProvider):
    @classmethod
    def createProvider(cls, uri, providerOptions = QgsDataProvider.ProviderOptions(), flags = QgsDataProvider.ReadFlags()):
        """프로바이더 인스턴스를 생성하는 팩토리 메서드"""
        return PandapowerProvider(uri, providerOptions, flags)


    def __init__(self, uri = "", providerOptions = QgsDataProvider.ProviderOptions(), flags = QgsDataProvider.ReadFlags()):
        super().__init__(uri)
        # 레지스트리에서 메타데이터 인스턴스 가져오기
        metadata_provider = QgsProviderRegistry.instance().providerMetadata("PandapowerProvider")
        self.uri = uri
        self.uri_parts = metadata_provider.decodeUri(uri)
        self._provider_options = providerOptions
        self._flags = flags

        # 컨테이너에서 네트워크 데이터 가져오기
        network_data = NetworkContainer.get_network(uri)
        if network_data is None:
            self._is_valid = False
            print("Warning: Failed to load Network data from Network container.\n")
            return

        # 네트워크 데이터 설정
        self.net = network_data['net']
        print("\nnet 값 뭔지 디버깅", self.net)
        self.vn_kv = network_data['vn_kv']
        self.type_layer_name = network_data['type_layer_name']
        print("타입 레이어 네임 뭔지 디버깅\n", self.type_layer_name)
        print("")
        if self.uri_parts['network_type'] not in ['bus', 'line', 'junction', 'pipe']:
            raise ValueError("Invalid network_type. Expected 'bus', 'line', 'junction', 'pipe'.")  # necessary?
        else:
            self.network_type = self.uri_parts['network_type']
        self.current_crs = int(network_data['current_crs']) if network_data['current_crs'] else 4326
        self.crs = self.sourceCrs()
        #self.fields_list = QgsFields()
        self.fields_list = None
        #print(f"fields_list 초기 상태: 비어있음? {len(self.fields_list) == 0}")
        self.df = None
        #self.changed_feature_ids = set()
        self._extent = None

        provider_list = QgsProviderRegistry.instance().providerList()
        print("provider list by init ppprovider", provider_list)
        self._is_valid = True

        print("")
        print("")

    def merge_df(self):
        """
        Merges the network type dataframe with its corresponding result dataframe.
        Only includes data with matching vn_kv value.
        """
        print("")
        print("\nnow in merge_df")
        print("")

        try:
            # Get the dataframes for the network type and its result
            df_network_type = getattr(self.net, self.network_type)
            df_res_network_type = getattr(self.net, f'res_{self.network_type}')

            # df_network_type의 인덱스를 출력합니다.
            print(f"Index of df_{self.network_type}:")
            print(df_network_type.index) # Debugging
            # df_res_network_type의 인덱스를 출력합니다.
            print(f"Index of df_res_{self.network_type}:")
            print(df_res_network_type.index)

            if df_network_type is None:
                print(f"Error: No dataframe found for {self.network_type}.")
                self.df = pd.DataFrame()  # Set to empty DataFrame
                return

            print(f"Before sorting df_{self.network_type}\n", df_network_type.head())
            print(f"Before sorting df_res_{self.network_type}\n", df_res_network_type.head())
            print(f"Original df_{self.network_type} shape: {df_network_type.shape}")
            if df_res_network_type is not None:
                print(f"Original df_res_{self.network_type} shape: {df_res_network_type.shape}")

            # 정렬 전에 vn_kv 필터링
            if self.vn_kv is not None:
                # line, pipe의 경우 전체 출력
                # network_type이 'bus'인 경우
                if self.network_type == 'bus':
                    filtered_indices = df_network_type[df_network_type['vn_kv'] == self.vn_kv].index
                    df_network_type = df_network_type.loc[filtered_indices]
                    if df_res_network_type is not None:
                        df_res_network_type = df_res_network_type.loc[filtered_indices]
                # network_type이 'junction'인 경우
                elif self.network_type == 'junction':
                    if 'vn_kv' in df_network_type.columns:
                        filtered_indices = df_network_type[df_network_type['vn_kv'] == self.vn_kv].index
                        df_network_type = df_network_type.loc[filtered_indices]
                        if df_res_network_type is not None:
                            df_res_network_type = df_res_network_type.loc[filtered_indices]
                print(f"After filtering with vn_kv={self.vn_kv}, df_{self.network_type} shape: {df_network_type.shape}")

            # Sort indices
            df_network_type.sort_index(inplace=True)
            if df_res_network_type is not None:
                df_res_network_type.sort_index(inplace=True)

            print(f"After sorting df_{self.network_type}\n", df_network_type.head())
            print(f"After sorting df_res_{self.network_type}\n", df_res_network_type.head())

            # Check if the result dataframe exists
            if df_res_network_type is not None:
                # Merge the two dataframes on their indices
                self.df = pd.merge(df_network_type, df_res_network_type, left_index=True, right_index=True,
                                       suffixes=('', '_res'))
                print("Merged DataFrame (1):") # Debugging
                print(self.df.head())
            else:
                # If the result dataframe does not exist, use only the network type dataframe
                self.df = df_network_type
                print(f"Warning: No res_{self.network_type} exist. Only {self.network_type} returned.")

            # Check if the merged dataframe is empty
            if self.df.empty:
                print(f"Warning: Merged dataframe for {self.network_type} is empty.")

            # Create 'pp_type' and 'pp_index' columns
            self.df.insert(0, 'pp_type', self.network_type)
            self.df.insert(1, 'pp_index', self.df.index)

            print("\n@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@self.df.index: ", self.df.index)

            print("Merged DataFrame (2):")  # Debugging
            print(self.df.head())
            print("")

        except Exception as e:
            print(f"Error merging dataframes for {self.network_type}: {str(e)}")
            return pd.DataFrame()  # Return an empty DataFrame in case of error


    def fields(self) -> QgsFields:
        """
        테이블의 필드 정보를 반환합니다.
        지연 초기화(lazy initialization) 패턴을 사용하여 실제로 필요할 때만 데이터베이스를 조회합니다.
        """
        #if not self.fields_list:  # 첫 호출 시에만 데이터베이스를 조회합니다
        #print("length of self.fields_list: ", len(self.fields_list))
        #if len(self.fields_list) == 0:  # 첫 호출 시에만 데이터베이스를 조회합니다
        if not self.fields_list:
            self.fields_list = QgsFields()

            print("length is 0, merge df 호출중")
            self.merge_df()

            # Check if dataframe is empty
            if self.df.empty:
                print(f"No data available for network type: {self.network_type}, called in fields method while initializing")  # Debugging
                return
            else:
                print("print df.columns: ", self.df.columns)
                # print(f"Dataframe for {self.type_layer_name} has {len(df)} rows.")

            # generate fields_list dynamically from column of the dataframe
            for column in self.df.columns:
                dt = self.df[column].dtype
                qm = convert_dtype_to_qmetatype(dt)
                self.fields_list.append(QgsField(column, qm))
                # print(f"Generate field: {column} with type {qm}")  # Debugging

            # Determine geometry type based on network type
            geometry_type = "Point" if self.network_type in ['bus', 'junction'] else "LineString"
            print(f"Geometry type for {self.network_type}: {geometry_type}")  # Debugging
            print(f"URI type: {type(self.uri)}, value: {self.uri}")  # Debugging

            '''
            for field in self.fields_list:
                if not self.layer.addAttribute(field):
                    raise RuntimeError(f"Failed to add attribute: {field.name()}")
                # print(f"Added attribute fields to layer: {field.name()}")  # Debugging

            self.populate_features()
            '''

        return self.fields_list


    def getFeatures(self, request=QgsFeatureRequest()):
        """Return next feature"""
        return QgsFeatureIterator(
            pandapower_feature_iterator.PandapowerFeatureIterator(
                pandapower_feature_source.PandapowerFeatureSource(self), request
            )
        )


    def changeGeometryValues(self, geometry_map):
        """
        Changes geometries of existing features.

        :param geometry_map: A QgsGeometryMap whose index contains the feature IDs
            that will have their geometries changed.
            The second map parameter being the new geometries themselves.
        :type geometry_map: typedef QMap<QgsFeatureId, QgsGeometry> QgsGeometryMap
        :return: True if geometries were changed successfully, False otherwise.
        :rtype: bool
        """
        print("\nchangeGeometryValues")
        print(f"Feature IDs in geometry_map: {list(geometry_map.keys())}")
        print(f"Dataframe indices: {list(self.df.index)}")
        print(f"Geodata indices: {list(getattr(self.net, f'{self.network_type}_geodata').index)}\n")
        try:
            for feature_id, new_geometry in geometry_map.items():
                # 판다파워 네트워크의 지오데이터 업데이트
                if self.network_type in ['bus', 'junction']:
                    # 버스/정션의 경우 x, y 좌표 업데이트
                    x = new_geometry.asPoint().x()
                    y = new_geometry.asPoint().y()

                    # 지오데이터 프레임 업데이트
                    geodata_df = getattr(self.net, f'{self.network_type}_geodata')
                    if feature_id in geodata_df.index:
                        geodata_df.at[feature_id, 'x'] = x
                        geodata_df.at[feature_id, 'y'] = y
                        print(f"Updated {self.network_type} geometry at ID {feature_id}: ({x}, {y})")
                    else:
                        print(f"Warning: {self.network_type} with ID {feature_id} not found in geodata")

                elif self.network_type in ['line', 'pipe']:
                    # 라인/파이프의 경우 좌표 목록 업데이트
                    points = new_geometry.asPolyline()
                    coords = [(point.x(), point.y()) for point in points]

                    # 지오데이터 프레임 업데이트
                    geodata_df = getattr(self.net, f'{self.network_type}_geodata')
                    if feature_id in geodata_df.index:
                        geodata_df.at[feature_id, 'coords'] = coords
                        print(f"Updated {self.network_type} geometry at ID {feature_id} with {len(coords)} points")
                    else:
                        print(f"Warning: {self.network_type} with ID {feature_id} not found in geodata")

            # 변경 사항 알림을 보내기 위한 signal 발생
            # 이는 QGIS가 데이터 변경을 인식하고 화면을 다시 그리도록 하는 중요한 단계
            self.dataChanged.emit()
            # 캐시 무효화 시도 (이 메서드가 있다면)
            if hasattr(self, 'cacheInvalidate'):
                self.cacheInvalidate()
            # 레이어 명시적 갱신 시도
            try:
                # 레이어 객체 찾기
                layers = QgsProject.instance().mapLayersByName(self.type_layer_name)
                if layers:
                    # 명시적 리페인트 트리거
                    layers[0].triggerRepaint()
                    print(f"Triggered repaint for layer: {self.type_layer_name}")
            except Exception as e:
                print(f"Warning: Could not trigger layer repaint: {str(e)}")
            return True
        except Exception as e:
            self.pushError(f"Failed to change geometries: {str(e)}")
            return False


    def capabilities(self) -> QgsVectorDataProvider.Capabilities:
        return (
            QgsVectorDataProvider.CreateSpatialIndex |
            QgsVectorDataProvider.SelectAtId |
            QgsVectorDataProvider.ChangeGeometries
        )

    def crs(self) -> QgsCoordinateReferenceSystem:
        return self.sourceCrs()

    def sourceCrs(self) -> QgsCoordinateReferenceSystem:
        crs = QgsCoordinateReferenceSystem.fromEpsgId(int(self.current_crs))
        if not crs.isValid():
            raise ValueError(f"CRS ID {self.current_crs} is not valid.")
        print(f"CRS is valid: {crs.authid()}") # Debugging
        return crs

    @classmethod
    def name(cls) -> str:
        return "PandapowerProvider"

    @classmethod
    def description(cls) -> str:
        """Returns the memory provider description"""
        return "PandapowerProvider"

    def extent(self) -> QgsRectangle:
        """Calculates the extent of the bend and returns a QgsRectangle"""
        if not self._extent:
            try:
                min_x = float('inf')
                max_x = float('-inf')
                min_y = float('inf')
                max_y = float('-inf')

                df_geodata = getattr(self.net, f'{self.network_type}_geodata')
                if df_geodata is None or df_geodata.empty:
                    return QgsRectangle()

                # Point geometry (bus/junction)
                if self.network_type in ['bus', 'junction']:
                    min_x = df_geodata['x'].min()
                    max_x = df_geodata['x'].max()
                    min_y = df_geodata['y'].min()
                    max_y = df_geodata['y'].max()

                # Line geometry (line/pipe)
                elif self.network_type in ['line', 'pipe']:
                    # 각 라인의 좌표들을 순회
                    for _, row in df_geodata.iterrows():
                        coords = row.get('coords', [])
                        if coords:
                            # coords는 이미 (x, y) 쌍의 리스트 형태
                            for x, y in coords:
                                min_x = min(min_x, x)
                                max_x = max(max_x, x)
                                min_y = min(min_y, y)
                                max_y = max(max_y, y)

                # 유효한 범위가 계산되었는지 확인
                if min_x == float('inf') or max_x == float('-inf'):
                    print("Warning: extent is infinite")
                    return QgsRectangle()

                return QgsRectangle(min_x, min_y, max_x, max_y)

            except Exception as e:
                self.pushError(f"Error calculating extent: {str(e)}")
                return QgsRectangle()

    def featureCount(self):
        """
        Returns the number of features in the provider.

        :return: Number of features
        :rtype: int
        """
        try:
            return len(self.df)
        except Exception as e:
            self.pushError(f"Failed to count features: {str(e)}")
            return 0

    def featureSource(self):
        return pandapower_feature_source.PandapowerFeatureSource(self)

    def isValid(self):
        """데이터 프로바이더의 유효성을 반환합니다"""
        return self._is_valid

    def storageType(self):
        """
        Returns the permanent storage type for this layer as a friendly name.
        """
        return f"{self.network_type} layer is Pandapower Network in json format"

    def wkbType(self):
        if self.network_type == 'bus' or self.network_type == 'junction':
            return QgsWkbTypes.Point
        elif self.network_type == 'line' or self.network_type == 'pipe':
            return QgsWkbTypes.LineString

    def unload(self):
        # Remove custom data provider when it is deleted
        QgsProviderRegistry.instance().removeProvider('PandapowerProvider')