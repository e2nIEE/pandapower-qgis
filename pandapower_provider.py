# current version of ppprovider
# C:\Users\slee\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\pandapower-qgis

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
    '''
    # Check if dtype is pandas Index object
    if isinstance(dtype, pd.Index):
        # Check data type of index
        index_dtype_str = str(dtype.dtype)
        print(f"Processing pandas Index with dtype: {index_dtype_str}")
        # 정수형 인덱스인 경우에도 안전하게 문자열로 변환합니다
        # 이는 불연속적인 인덱스나 범위가 큰 인덱스를 처리할 때 더 안정적입니다
        # int format index can occur problem: when the index is discontinuous or large
        return QMetaType.QString

    # int64 can occur problem in QGIS
    if pd.api.types.is_integer_dtype(dtype):
        dtype_str = str(dtype)
        if 'int64' in dtype_str or 'uint64' in dtype_str:
            print(f"Converting 64-bit integer type {dtype} to QString for better compatibility.")
            return QMetaType.QString
        return QMetaType.Int
    '''

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
        print(f"Unexpected dtype detected: {dtype}. Add it or check if it is not available.")
        return QMetaType.Invalid


class PandapowerProvider(QgsVectorDataProvider):
    @classmethod
    def createProvider(cls, uri, providerOptions = QgsDataProvider.ProviderOptions(), flags = QgsDataProvider.ReadFlags()):
        """Factory methode that create provider instance"""
        return PandapowerProvider(uri, providerOptions, flags)


    def __init__(self, uri = "", providerOptions = QgsDataProvider.ProviderOptions(), flags = QgsDataProvider.ReadFlags()):
        super().__init__(uri)
        # Bring metadata instace from registry
        metadata_provider = QgsProviderRegistry.instance().providerMetadata("PandapowerProvider")
        self.uri = uri
        self.uri_parts = metadata_provider.decodeUri(uri)
        self._provider_options = providerOptions
        self._flags = flags

        # Bring network data from container
        network_data = NetworkContainer.get_network(uri)
        if network_data is None:
            self._is_valid = False
            print("Warning: Failed to load Network data from Network container.\n")
            return

        # Setting network data
        self.net = network_data['net']
        print("\nvalue of net: ", self.net)
        self.vn_kv = network_data['vn_kv']
        self.type_layer_name = network_data['type_layer_name']
        print("type of layer name: \n", self.type_layer_name)
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

            # Filter vn_kv before sort
            if self.vn_kv is not None:
                # If line, pipe: merge all
                if self.network_type == 'bus':
                    filtered_indices = df_network_type[df_network_type['vn_kv'] == self.vn_kv].index
                    df_network_type = df_network_type.loc[filtered_indices]
                    if df_res_network_type is not None:
                        df_res_network_type = df_res_network_type.loc[filtered_indices]
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
                self.df = pd.merge(df_network_type, df_res_network_type, left_index=True, right_index=True, suffixes=('', '_res'))
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
            # Convert pandas index to string
            self.df.insert(1, 'pp_index', self.df.index.astype(str).tolist())

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
        Return field data of table
        Using lazy initialization pattern, search database only when it needed.
        """
        #if not self.fields_list:  # 첫 호출 시에만 데이터베이스를 조회합니다
        #print("length of self.fields_list: ", len(self.fields_list))
        #if len(self.fields_list) == 0:  # 첫 호출 시에만 데이터베이스를 조회합니다
        if not self.fields_list:
            self.fields_list = QgsFields()

            print("length is 0, called merge df")
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
        #print(f"Geodata indices: {list(getattr(self.net, f'{self.network_type}_geodata').index)}\n")
        print(f"Geodata indices: {list(getattr(self.net, f'{self.network_type}').geo.index)}\n")
        try:
            # Update Geodata of Pandapower Network
            for feature_id, new_geometry in geometry_map.items():
                if self.network_type in ['bus', 'junction']:
                    # If bus or junction, update x, y geometry
                    x = new_geometry.asPoint().x()
                    y = new_geometry.asPoint().y()

                    # Update geodata of dataframe
                    #geodata_df = getattr(self.net, f'{self.network_type}_geodata')
                    geodata_df = getattr(self.net, f'{self.network_type}').geo
                    if feature_id in geodata_df.index:
                        #geodata_df.at[feature_id, 'x'] = x
                        #geodata_df.at[feature_id, 'y'] = y
                        try:
                            # 기존 JSON 문자열 파싱
                            geo_str = geodata_df.loc[feature_id]
                            geo_data = json.loads(geo_str)

                            # 좌표 업데이트
                            geo_data['coordinates'] = [x, y]

                            # 업데이트된 데이터를 JSON 문자열로 변환하여 저장
                            geodata_df.loc[feature_id] = json.dumps(geo_data)
                            print(f"Updated {self.network_type} geometry at ID {feature_id}: ({x}, {y})")
                        except Exception as e:
                            print(f"Error updating geometry for ID {feature_id}: {str(e)}")
                    else:
                        print(f"Warning: {self.network_type} with ID {feature_id} not found in geodata")

                elif self.network_type in ['line', 'pipe']:
                    # If line or pipe, update coord list
                    points = new_geometry.asPolyline()
                    coords = [(point.x(), point.y()) for point in points]

                    # Update geodata of dataframe
                    #geodata_df = getattr(self.net, f'{self.network_type}_geodata')
                    geodata_df = getattr(self.net, f'{self.network_type}').geo
                    if feature_id in geodata_df.index:
                        #geodata_df.at[feature_id, 'coords'] = coords
                        try:
                            # 기존 JSON 문자열 파싱
                            geo_str = geodata_df.loc[feature_id]
                            geo_data = json.loads(geo_str)

                            # 좌표 업데이트
                            geo_data['coordinates'] = coords

                            # 업데이트된 데이터를 JSON 문자열로 변환하여 저장
                            geodata_df.loc[feature_id] = json.dumps(geo_data)
                            print(f"Updated {self.network_type} geometry at ID {feature_id} with {len(coords)} points")
                        except Exception as e:
                            print(f"Error updating line geometry for ID {feature_id}: {str(e)}")
                    else:
                        print(f"Warning: {self.network_type} with ID {feature_id} not found in geodata")

            try:
                # 변경된 좌표를 원본 파일에 반영 # 메서드 마지막에 레이어 다시 그린 다음에 하는 게 맞아보이는데 일단 고
                # 투두: 수동 저장 옵션
                if self.update_geodata_in_json():
                    print(f"좌표 변경 사항이 '{self.uri_parts.get('path', '')}'에 저장되었습니다")
            except Exception as e:
                print(f"Failed to save changed geo data: {str(e)}")
                raise

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


    def update_geodata_in_json(self, auto_save=True):
        """
        Update changed geodata of original json file with pandapower API.
        If auto_save False, changed geodata kept in memory only.
        Currently support auto save only.
        """
        if not auto_save:
            # 변경 사항을 저장하지 않고 메모리에만 유지
            print("Changes are kept in memory only.")
            return True

        try:
            import pandapower as pp
            import os
            import shutil
            from datetime import datetime

            original_path = self.uri_parts.get('path', '')
            if not original_path or not os.path.exists(original_path):
                self.pushError(f"Cannot find original file at: {original_path}")
                return False

            # 백업 파일 생성 (날짜/시간 스탬프 추가)
            backup_path = f"{original_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            try:
                shutil.copy2(original_path, backup_path)
                print(f"백업 파일이 생성되었습니다: {backup_path}")
            except Exception as e:
                print(f"백업 파일 생성 중 오류 발생: {str(e)}")
                # continue

            # Load original network from json
            original_net = pp.from_json(original_path)

            # Changed geodata of current memory
            #current_geodata = getattr(self.net, f"{self.network_type}_geodata")
            current_geodata = getattr(self.net, f"{self.network_type}").geo

            # Update geodata of original network as changed coordinate
            # Only filtered data considered
            #original_geodata = getattr(original_net, f"{self.network_type}_geodata")
            original_geodata = getattr(original_net, f"{self.network_type}").geo

            for idx in current_geodata.index:
                if idx in original_geodata.index:
                    '''
                    if self.network_type in ['bus', 'junction']:
                        if 'x' in current_geodata.columns and 'y' in current_geodata.columns:
                            original_geodata.at[idx, 'x'] = current_geodata.at[idx, 'x']
                            original_geodata.at[idx, 'y'] = current_geodata.at[idx, 'y']
                    elif self.network_type in ['line', 'pipe']:
                        if 'coords' in current_geodata.columns:
                            original_geodata.at[idx, 'coords'] = current_geodata.at[idx, 'coords']
                    '''
                    # 현재 JSON 문자열을 원본에 복사
                    original_geodata.loc[idx] = current_geodata.loc[idx]

            # Save updated network to json
            try:
                pp.to_json(original_net, original_path)
                print(f"좌표 변경 사항이 저장되었습니다: {original_path}")
                return True
            except PermissionError:
                self.pushError(f"파일에 접근할 수 없습니다. 파일이 다른 프로그램에서 열려있거나 쓰기 권한이 없습니다: {original_path}")
                return False
            except Exception as e:
                self.pushError(f"파일 저장 중 오류 발생: {str(e)}")
                return False

        except Exception as e:
            self.pushError(f"Error occurs while updating geodata: {str(e)}")
            import traceback
            traceback.print_exc()
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

                #df_geodata = getattr(self.net, f'{self.network_type}_geodata')
                df_geodata = getattr(self.net, f'{self.network_type}').geo
                if df_geodata is None or df_geodata.empty:
                    return QgsRectangle()

                # Point geometry (bus/junction)
                if self.network_type in ['bus', 'junction']:
                    '''
                    min_x = df_geodata['x'].min()
                    max_x = df_geodata['x'].max()
                    min_y = df_geodata['y'].min()
                    max_y = df_geodata['y'].max()
                    '''
                    for idx, geo_str in df_geodata.items():
                        try:
                            if geo_str:
                                geo_data = json.loads(geo_str)
                                if ('coordinates' in geo_data and isinstance(geo_data['coordinates'], list)
                                        and len(geo_data['coordinates']) == 2):
                                    x = geo_data['coordinates'][0]
                                    y = geo_data['coordinates'][1]
                                    min_x = min(min_x, x)
                                    max_x = max(max_x, x)
                                    min_y = min(min_y, y)
                                    max_y = max(max_y, y)
                                else:
                                    print(f"Incorrect coordinate format for {self.network_type}.")
                                    return
                        except Exception as e:
                            print(f"Warning: Bus/Junction data of index {idx} failed to produce: {str(e)}")

                # Line geometry (line/pipe)
                elif self.network_type in ['line', 'pipe']:
                    # Iterate through the coordinates of each line
                    '''
                    for _, row in df_geodata.iterrows():
                        coords = row.get('coords', [])
                        if coords:
                            # coords is already in the form of a list of (x, y) pairs
                            for x, y in coords:
                                min_x = min(min_x, x)
                                max_x = max(max_x, x)
                                min_y = min(min_y, y)
                                max_y = max(max_y, y)
                    '''
                    for idx, geo_str in df_geodata.items():
                        try:
                            if geo_str:
                                geo_data = json.loads(geo_str)
                                if 'coordinates' in geo_data and isinstance(geo_data['coordinates'], list):
                                    for coord_pair in geo_data['coordinates']:
                                        if isinstance(coord_pair, list) and len(coord_pair) == 2:
                                            x, y = coord_pair[0], coord_pair[1]
                                            min_x = min(min_x, x)
                                            max_x = max(max_x, x)
                                            min_y = min(min_y, y)
                                            max_y = max(max_y, y)
                                        else:
                                            print(f"Incorrect coordinate format for {self.network_type}.")
                                            return
                        except Exception as e:
                            print(f"Warning: Lind/Pipe data of index {idx} failed to produce: {str(e)}")

                # Check if the valid range has been calculated
                if min_x == float('inf') or max_x == float('-inf'):
                    print("Warning: extent is infinite.")
                    return QgsRectangle()

                return QgsRectangle(min_x, min_y, max_x, max_y)

            except Exception as e:
                self.pushError(f"Error calculating extent: {str(e)}")
                import traceback
                traceback.print_exc()
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
        """
        Return the validity of the data provider.
        """
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