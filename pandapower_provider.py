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
    Note: It does not convert actual values. It just returns the corresponding Qt data type for the given pandas data type.

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

        # 🔄 한 번만 네트워크 데이터 가져오기
        print("=" * 50)
        print("pandapower_provider.py, init method")
        print(f"[DEBUG] Getting network data from container with URI: {uri}")
        # Bring network data from container
        network_data = NetworkContainer.get_network(uri)
        if network_data is None:
            print(f"[DEBUG] Failed to get network data from container")
            self._is_valid = False
            print("Warning: Failed to load Network data from Network container.\n")
            return
        else:
            print(f"[DEBUG] Successfully got network data from container")
            print(f"[DEBUG] Network data keys: {list(network_data.keys())}")

        # Setting network data
        self.net = network_data['net']
        print(f"\n[DEBUG] Network object type: {type(self.net)}")
        print(f"[DEBUG] Network object keys: {list(self.net.keys()) if hasattr(self.net, 'keys') else 'No keys method'}")
        print("[DEBUG] value of net: ", self.net)

        if self.uri_parts['network_type'] in ['bus', 'line']:
            self.vn_kv = network_data['vn_kv']
        elif self.uri_parts['network_type'] in ['junction', 'pipe']:
            self.pn_bar = network_data['pn_bar']
        else:
            raise ValueError("Invalid network_type. Expected 'bus', 'line', 'junction', 'pipe'.")  # necessary?
        self.network_type = self.uri_parts['network_type']
        self.type_layer_name = network_data['type_layer_name']

        print(f"\nType of layer name: {self.type_layer_name}")
        print(f"Network type: {self.network_type}")
        print(f"vn_kv/pn_bar: {getattr(self, 'vn_kv', getattr(self, 'pn_bar', 'None'))}")

        self.current_crs = int(network_data['current_crs']) if network_data['current_crs'] else 4326
        self.crs = self.sourceCrs()
        self.fields_list = None
        self.df = None
        self._extent = None

        provider_list = QgsProviderRegistry.instance().providerList()
        print("provider list by init ppprovider", provider_list)
        self._is_valid = True

        # State tracking variables for asynchronous save operation of the changeGeometryValues method
        self._save_in_progress = False  # Indicates whether a save operation is in progress
        self._save_thread = None  # QThread instance performing the save operation

        # print("")
        # print("")
        #
        # print("=" * 50)
        # print("pandapower_provider.py, init method")
        # # Bring network data from container
        # print(f"[DEBUG] Getting network data from container with URI: {uri}")
        # #network_data = NetworkContainer.get_network(uri)
        #
        # if network_data is None:
        #     print(f"[DEBUG] Failed to get network data from container")
        #     self._is_valid = False
        #     print("Warning: Failed to load Network data from Network container.\n")
        #     return
        # else:
        #     print(f"[DEBUG] Successfully got network data from container")
        #     print(f"[DEBUG] Network data keys: {list(network_data.keys())}")
        #
        # # Setting network data
        # self.net = network_data['net']
        # print(f"[DEBUG] Network object type: {type(self.net)}")
        # print(
        #     f"[DEBUG] Network object keys: {list(self.net.keys()) if hasattr(self.net, 'keys') else 'No keys method'}")
        # print("=" * 50)

        # 🌟 새로운 기능: NetworkContainer에 "나 알림 받을래!" 등록
        NetworkContainer.add_listener(self.uri, self)
        print(f"📢 Provider {self.uri}: NetworkContainer에 알림 등록 완료")
        print(f"📋 현재 등록된 리스너들: {NetworkContainer._listeners}")
        print(f"📋 내가 등록됐나?: {self in NetworkContainer._listeners.get(self.uri, [])}")
        print("=" * 50)

    # 원본
    def merge_df(self):
        """
        Merges the network type dataframe with its corresponding result dataframe.
        Only includes data with matching vn_kv value.
        """
        print("=" * 50)
        print("=" * 50)
        print("\n\nnow in merge_df\n\n")

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

            # 🔍 핵심: 어떤 상황인지 판단하기
            has_result_data = (df_res_network_type is not None and
                               not df_res_network_type.empty and
                               len(df_res_network_type) > 0)

            # when res column not empty
            if has_result_data:
                print("✅ 계산 결과가 있어요! 기존 방식 사용")
                # Filter vn_kv before sort
                if self.vn_kv is not None:
                    # If line, pipe: merge all
                    if self.network_type == 'bus':
                        filtered_indices = df_network_type[df_network_type['vn_kv'] == self.vn_kv].index
                        df_network_type = df_network_type.loc[filtered_indices]
                        if df_res_network_type is not None:
                            df_res_network_type = df_res_network_type.loc[filtered_indices]
                    elif self.network_type == 'junction':   # pn_bar
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

            # when res column of json file is cleared
            elif not has_result_data:
                print("⚠️ 계산 결과가 없어요! 새로운 방식 사용")

                # 🎯 핵심: 기본 데이터에 빈 결과 컬럼들 추가
                self.df = df_network_type.copy()  # 기본 데이터 복사

                # 🔧 빈 컬럼들 추가
                res_columns = df_res_network_type.columns.tolist()
                for col_name in res_columns:
                    self.df[col_name] = None  # 또는 적절한 기본값

                print(f"✅ {len(res_columns)}개의 빈 결과 컬럼 추가 완료!")

            # Check if the merged dataframe is empty
            if self.df.empty:
                print(f"Warning: Merged dataframe for {self.network_type} is empty.")

            # Create 'pp_type' and 'pp_index' columns
            self.df.insert(0, 'pp_type', self.network_type)
            self.df.insert(1, 'pp_index', self.df.index)
            # Convert pandas index to string
            #self.df.insert(1, 'pp_index', self.df.index.astype(str).tolist())

            print("Merged DataFrame (2):")  # Debugging
            print(self.df.head())
            print("="*50)
            print("=" * 50)

        except Exception as e:
            print(f"Error merging dataframes for {self.network_type}: {str(e)}")
            print("=" * 50)
            print("=" * 50)
            return pd.DataFrame()  # Return an empty DataFrame in case of error

    # 1차 수정본 - 핵심 수정: vn_kv 필터링을 공통으로 먼저 적용
    # 왜 주석처리됐는지 알아보기
    # def merge_df(self):
    #     """
    #     Merges the network type dataframe with its corresponding result dataframe.
    #     Only includes data with matching vn_kv value.
    #     """
    #     print("=" * 50)
    #     print("=" * 50)
    #     print("\n\nnow in merge_df\n\n")
    #
    #     try:
    #         # Get the dataframes for the network type and its result
    #         df_network_type = getattr(self.net, self.network_type)
    #         df_res_network_type = getattr(self.net, f'res_{self.network_type}')
    #
    #         # df_network_type의 인덱스를 출력합니다.
    #         print(f"Index of df_{self.network_type}:")
    #         print(df_network_type.index)  # Debugging
    #         # df_res_network_type의 인덱스를 출력합니다.
    #         print(f"Index of df_res_{self.network_type}:")
    #         print(df_res_network_type.index)
    #
    #         if df_network_type is None:
    #             print(f"Error: No dataframe found for {self.network_type}.")
    #             self.df = pd.DataFrame()  # Set to empty DataFrame
    #             return
    #
    #         print(f"Before sorting df_{self.network_type}\n", df_network_type.head())
    #         print(f"Before sorting df_res_{self.network_type}\n", df_res_network_type.head())
    #         print(f"Original df_{self.network_type} shape: {df_network_type.shape}")
    #         if df_res_network_type is not None:
    #             print(f"Original df_res_{self.network_type} shape: {df_res_network_type.shape}")
    #
    #         # 🔍 핵심: 어떤 상황인지 판단하기
    #         has_result_data = (df_res_network_type is not None and
    #                            not df_res_network_type.empty and
    #                            len(df_res_network_type) > 0)
    #
    #         # 🎯 핵심 수정: vn_kv 필터링을 공통으로 먼저 적용
    #         # Filter vn_kv BEFORE checking result data
    #         original_df_network_type = df_network_type.copy()  # 원본 백업
    #
    #         if hasattr(self, 'vn_kv') and self.vn_kv is not None:
    #             print(f"🔍 vn_kv 필터링 적용: {self.vn_kv}")
    #
    #             if self.network_type == 'bus':
    #                 # 버스의 경우 vn_kv로 필터링
    #                 filtered_indices = df_network_type[df_network_type['vn_kv'] == self.vn_kv].index
    #                 df_network_type = df_network_type.loc[filtered_indices]
    #                 print(f"🔍 버스 필터링 후 shape: {df_network_type.shape}")
    #
    #                 # 결과 데이터도 같은 인덱스로 필터링
    #                 if df_res_network_type is not None and not df_res_network_type.empty:
    #                     df_res_network_type = df_res_network_type.loc[
    #                         df_res_network_type.index.intersection(filtered_indices)
    #                     ]
    #                     print(f"🔍 결과 데이터 필터링 후 shape: {df_res_network_type.shape}")
    #
    #             elif self.network_type == 'junction':  # pn_bar의 경우
    #                 if hasattr(self, 'pn_bar') and self.pn_bar is not None:
    #                     if 'pn_bar' in df_network_type.columns:
    #                         filtered_indices = df_network_type[df_network_type['pn_bar'] == self.pn_bar].index
    #                         df_network_type = df_network_type.loc[filtered_indices]
    #
    #                         if df_res_network_type is not None and not df_res_network_type.empty:
    #                             df_res_network_type = df_res_network_type.loc[
    #                                 df_res_network_type.index.intersection(filtered_indices)
    #                             ]
    #
    #             # line과 pipe는 from_bus/to_bus를 통해 연결된 것들만 포함
    #             elif self.network_type in ['line', 'pipe']:
    #                 # 이미 ppqgis_import.py에서 필터링된 상태로 전달됨
    #                 pass
    #
    #         # 필터링 후 상태 확인
    #         has_result_data = (df_res_network_type is not None and
    #                            not df_res_network_type.empty and
    #                            len(df_res_network_type) > 0)
    #
    #         # when res column not empty
    #         if has_result_data:
    #             print("✅ 계산 결과가 있어요! 기존 방식 사용")
    #
    #             # Sort indices
    #             df_network_type.sort_index(inplace=True)
    #             df_res_network_type.sort_index(inplace=True)
    #
    #             print(f"After sorting df_{self.network_type}\n", df_network_type.head())
    #             print(f"After sorting df_res_{self.network_type}\n", df_res_network_type.head())
    #
    #             # Merge the two dataframes on their indices
    #             self.df = pd.merge(df_network_type, df_res_network_type, left_index=True, right_index=True,
    #                                suffixes=('', '_res'))
    #             print("Merged DataFrame (1):")  # Debugging
    #             print(self.df.head())
    #
    #         # when res column of json file is cleared
    #         elif not has_result_data:
    #             print("⚠️ 계산 결과가 없어요! 새로운 방식 사용")
    #
    #             # 🎯 핵심: 이미 필터링된 기본 데이터 사용
    #             self.df = df_network_type.copy()  # 필터링된 데이터 복사
    #             print(f"✅ 필터링된 기본 데이터 shape: {self.df.shape}")
    #
    #             # 🔧 빈 결과 컬럼들 추가 (원본 res 컬럼 구조 참고)
    #             # 원본에서 res 컬럼 구조 가져오기
    #             original_res = getattr(self.net, f'res_{self.network_type}')
    #             if original_res is not None and not original_res.empty:
    #                 res_columns = original_res.columns.tolist()
    #                 for col_name in res_columns:
    #                     self.df[col_name] = None  # 또는 적절한 기본값
    #                 print(f"✅ {len(res_columns)}개의 빈 결과 컬럼 추가 완료!")
    #             else:
    #                 print("⚠️ 원본 결과 컬럼 구조를 찾을 수 없음")
    #
    #         # Check if the merged dataframe is empty
    #         if self.df.empty:
    #             print(f"Warning: Merged dataframe for {self.network_type} is empty.")
    #
    #         # Create 'pp_type' and 'pp_index' columns
    #         self.df.insert(0, 'pp_type', self.network_type)
    #         self.df.insert(1, 'pp_index', self.df.index)
    #
    #         print("Final DataFrame:")  # Debugging
    #         print(f"Shape: {self.df.shape}")
    #         print(f"Columns: {list(self.df.columns)}")
    #         print(self.df.head())
    #         print("=" * 50)
    #         print("=" * 50)
    #
    #     except Exception as e:
    #         print(f"Error merging dataframes for {self.network_type}: {str(e)}")
    #         print("=" * 50)
    #         print("=" * 50)
    #         return pd.DataFrame()  # Return an empty DataFrame in case of error



    def fields(self) -> QgsFields:
        """
        테이블의 필드 정보를 반환합니다.
        지연 초기화(lazy initialization) 패턴을 사용하여 실제로 필요할 때만 데이터베이스를 조회합니다.
        Return field data of table.
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

        # Check if an existing save operation is in progress
        if self._save_in_progress:
            from qgis.utils import iface
            from qgis.core import Qgis
            iface.messageBar().pushMessage(
                "Notification",
                "The previous save operation is still in progress. Please try again after it is completed.",
                level=Qgis.Warning,
                duration=5
            )
            return False  # Operation denied

        # Proceed to update and save the dataframe only when a save operation is not in progress
        try:
            # Update Geodata of Pandapower Network
            for feature_id, new_geometry in geometry_map.items():
                if self.network_type in ['bus', 'junction']:
                    # If bus or junction, update x, y geometry
                    x = new_geometry.asPoint().x()
                    y = new_geometry.asPoint().y()

                    # Update geodata of dataframe
                    geodata_df = getattr(self.net, f'{self.network_type}').geo
                    if feature_id in geodata_df.index:
                        #geodata_df.at[feature_id, 'x'] = x
                        #geodata_df.at[feature_id, 'y'] = y
                        try:
                            # Load geo data of existing dataframe and convert it into python dict
                            geo_str = geodata_df.loc[feature_id]
                            geo_data = json.loads(geo_str)

                            # Update coordinates in 'coordinates' key of the dictionary
                            geo_data['coordinates'] = [x, y]

                            # Convert back into json String and save updated data in dataframe
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
                            # Load geo data of existing dataframe and convert it into python dict
                            geo_str = geodata_df.loc[feature_id]
                            geo_data = json.loads(geo_str)

                            # Update coordinates in 'coordinates' key of the dictionary
                            geo_data['coordinates'] = coords

                            # Convert back into json String and save updated data in dataframe
                            geodata_df.loc[feature_id] = json.dumps(geo_data)
                            print(f"Updated {self.network_type} geometry at ID {feature_id} with {len(coords)} points")
                        except Exception as e:
                            print(f"Error updating line geometry for ID {feature_id}: {str(e)}")
                    else:
                        print(f"Warning: {self.network_type} with ID {feature_id} not found in geodata")

            '''
            # Synchronous file saving tasks
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
            '''

            # Asynchronous file saving tasks
            # Define a callback function to be executed after saving
            def on_save_complete(success, message, backup_path=None):
                self._save_in_progress = False

                # UI Feedback for success or failure
                from qgis.core import Qgis
                from qgis.utils import iface

                if success:
                    # Display success message in UI
                    iface.messageBar().pushMessage(
                        "Saved Successfully",
                        message,
                        level=Qgis.Success,
                        duration=5
                    )

                    # Display backup file information
                    if backup_path:
                        iface.messageBar().pushMessage(
                            "Backup file created",
                            f"path: {backup_path}",
                            level=Qgis.Info,
                            duration=8
                        )

                    # Change Notification Triggered
                    self.dataChanged.emit()

                    # 캐시 무효화 (이 메서드가 있다면)
                    #if hasattr(self, 'cacheInvalidate'):
                        #self.cacheInvalidate()

                    # Explicit Layer Update
                    # Maybe not necessary
                    try:
                        layers = QgsProject.instance().mapLayersByName(self.type_layer_name)
                        if layers:
                            layers[0].triggerRepaint()
                            print(f"Triggered repaint for layer: {self.type_layer_name}")
                    except Exception as e:
                        print(f"Warning: Could not trigger layer repaint: {str(e)}")
                else:
                    # Display failure message to UI
                    iface.messageBar().pushMessage(
                        "Save failed",
                        message,
                        level=Qgis.Critical,
                        duration=10
                    )

            # Start asynchronous save
            self.update_geodata_in_json_async(on_save_complete)
            # Notify that the save operation has started
            return True

        except Exception as e:
            self.pushError(f"Failed to change geometries: {str(e)}")
            import traceback
            traceback.print_exc()
            return False




    # def on_update_changed_network(self, network_data):
    #     """
    #     ✅ 최종 안정화된 버전 - 디버깅 코드 제거
    #     NetworkContainer로부터 "데이터 바뀌었어!" 알림을 받는 메서드
    #     """
    #     try:
    #         # 1️⃣ 네트워크 객체 업데이트
    #         self.net = network_data['net']
    #
    #         여기서 그냥 self.net 데이터 그대로 받으면 안됨? 웨안되게 해놧지?
    #         # 2️⃣ 데이터프레임 재생성 (결과 컬럼 포함)
    #         self.fields_list = None  # 필드 캐시 초기화
    #         self.df = None  # 데이터프레임 캐시 초기화
    #
    #         # 3️⃣ QGIS에게 데이터 변경 알림
    #         self.dataChanged.emit()
    #
    #         print(f"✅ Provider {self.uri}: 데이터 업데이트 완료")
    #
    #     except Exception as e:
    #         print(f"❌ Provider {self.uri}: 업데이트 실패 - {str(e)}")
    #         # 개별 Provider 실패는 전체 시스템을 중단하지 않음


    #0708 새벽에 디버깅하기 위해 주석처리중
    def on_update_changed_network(self, network_data):
        """
        🛡️ 최종 안전화된 데이터 업데이트 - Race Condition 방지
        """
        print("\n")
        print("="*50)
        print(f"🚚 여기는 on_update_changed_network: 네트워크 컨테이너에서 {self.uri} 배달 받음!")  # ← 이거 추가
        print(f"🔔 {self.uri}: 알림 받음!")
        print(f"🔔 이전 데이터 크기: {len(self.df) if self.df is not None else 0}")

        old_net = self.net
        try:
            print(f"📨 Provider {self.uri}: 안전한 데이터 업데이트 시작")

            # 🔒 1단계: 네트워크 객체 업데이트 (안전)
            self.net = network_data['net']

            # 🔒 2단계: 새로운 데이터프레임을 별도 변수에서 생성 (Race Condition 방지)
            new_df = self._create_updated_dataframe()
            if new_df is None:  # ← 이 경우 렌더러가 빈 데이터를 받을 수 있음
                print("⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️ DataFrame 생성 실패! ⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️")

            # 🔒 3단계: 검증 후 한 번에 교체 (Atomic Operation)
            if new_df is not None and not new_df.empty:
                # 성공적으로 생성된 경우에만 교체
                #self.fields_list = None  # 필드 캐시 초기화
                self.df = new_df  # 새 데이터프레임으로 교체

                # # 🔒 4단계: QGIS 알림 (데이터가 준비된 후)
                # print(f"🔔 새 데이터 크기: {len(new_df) if new_df is not None else 0}")
                # self.dataChanged.emit()
                # print(f"🔔 dataChanged 신호 발생!")
                # print(f"✅ Provider {self.uri}: 안전한 업데이트 완료 (크기: {len(new_df)})")
            else:
                # 실패한 경우 기존 데이터 유지
                print(f"⚠️ Provider {self.uri}: 새 데이터 생성 실패, 기존 데이터 유지")

        except Exception as e:
            print(f"❌ Provider {self.uri}: 업데이트 실패 - {str(e)}")
            # 오류 발생 시 원본 상태 복원 시도
            if 'old_net' in locals():
                self.net = old_net

    def _create_updated_dataframe(self):
        """
        🔧 별도 함수에서 안전하게 새 데이터프레임 생성
        기존 merge_df() 로직을 복사하되, self.df를 직접 수정하지 않음
        """
        try:
            # 기존 merge_df 로직을 새 변수에서 실행
            df_network_type = getattr(self.net, self.network_type)
            df_res_network_type = getattr(self.net, f'res_{self.network_type}')

            if df_network_type is None:
                print(f"⚠️ {self.network_type} 데이터가 없음")
                return None

            # 계산 결과 확인
            has_result_data = (df_res_network_type is not None and
                               not df_res_network_type.empty and
                               len(df_res_network_type) > 0)

            if has_result_data:
                print("✅ 계산 결과가 있어요! 기존 방식 사용")

                # vn_kv 필터링 (기존 로직)
                if hasattr(self, 'vn_kv') and self.vn_kv is not None:
                    if self.network_type == 'bus':
                        filtered_indices = df_network_type[df_network_type['vn_kv'] == self.vn_kv].index
                        df_network_type = df_network_type.loc[filtered_indices]
                        df_res_network_type = df_res_network_type.loc[filtered_indices]

                # 정렬
                df_network_type.sort_index(inplace=True)
                df_res_network_type.sort_index(inplace=True)

                # 병합
                new_df = pd.merge(df_network_type, df_res_network_type,
                                  left_index=True, right_index=True, suffixes=('', '_res'))
            else:
                print("⚠️ 계산 결과가 없어요! 새로운 방식 사용")
                new_df = df_network_type.copy()

                # 빈 결과 컬럼들 추가
                if df_res_network_type is not None:
                    res_columns = df_res_network_type.columns.tolist()
                    for col_name in res_columns:
                        new_df[col_name] = None

            # pp_type과 pp_index 컬럼 추가
            new_df.insert(0, 'pp_type', self.network_type)
            new_df.insert(1, 'pp_index', new_df.index)

            print(f"✅ 새 데이터프레임 생성 완료: {len(new_df)}행")
            return new_df

        except Exception as e:
            print(f"❌ 데이터프레임 생성 실패: {str(e)}")
            import traceback
            traceback.print_exc()
            return None



    def update_geodata_in_json_async(self, callback=None):
        """
        Asynchronously updates the changed geodata in the original JSON file.
        Note: It is method for asynchronous update. For synchronous update, see update_geodata_in_json()

        :param callback: Function to be called after saving is complete.
                        on_save_complete(success, message, backup_path)
        """
        # Do not process new requests if a save operation is already in progress
        if self._save_in_progress:
            from qgis.utils import iface
            from qgis.core import Qgis
            iface.messageBar().pushMessage(
                "Notify",
                "A save operation is already in progress. Please try again later.",
                level=Qgis.Info
            )
            return
        else:
            self._save_in_progress = True

        from PyQt5.QtCore import QThread, pyqtSignal

        class SaveThread(QThread):
            # Save Completion Signal (Success Status, Message, Backup Path)
            saveCompleted = pyqtSignal(bool, str, str)

            def __init__(self, provider):
                super().__init__()
                self.provider = provider

            def run(self):
                try:
                    import pandapower as pp
                    import os
                    import shutil
                    from datetime import datetime

                    original_path = self.provider.uri_parts.get('path', '')
                    if not original_path or not os.path.exists(original_path):
                        self.saveCompleted.emit(False, f"Cannot find original file at: {original_path}", "")
                        return

                    # Create Backup File (Add Date/Time Stamp)
                    backup_path = f"{original_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                    try:
                        shutil.copy2(original_path, backup_path)
                        print(f"The backup file has been created: {backup_path}")
                    except Exception as e:
                        print(f"An error occurred while creating the backup file: {str(e)}")
                        # 백업 생성 실패가 심각한 문제는 아니라고 간주하고 계속 진행하려면
                        #backup_path = ""
                        return

                    # Load original network from json file
                    try:
                        original_net = pp.from_json(original_path)
                    except Exception as e:
                        self.saveCompleted.emit(False, f"Fail to load original network: {str(e)}", backup_path)
                        return

                    # 현재 메모리의 변경된 geodata
                    current_geodata = getattr(self.provider.net, f"{self.provider.network_type}").geo

                    # 원본 네트워크의 geodata를 변경된 좌표로 업데이트
                    # 필터링된 데이터만 고려됨
                    original_geodata = getattr(original_net, f"{self.provider.network_type}").geo

                    for idx in current_geodata.index:
                        if idx in original_geodata.index:
                            # 현재 JSON 문자열을 원본에 복사
                            original_geodata.loc[idx] = current_geodata.loc[idx]

                    # 업데이트된 네트워크를 json으로 저장
                    try:
                        pp.to_json(original_net, original_path)
                        success_msg = f"좌표 변경 사항이 저장되었습니다: {original_path}"
                        self.saveCompleted.emit(True, success_msg, backup_path)
                    except PermissionError:
                        error_msg = f"파일에 접근할 수 없습니다. 파일이 다른 프로그램에서 열려있거나 쓰기 권한이 없습니다: {original_path}"
                        self.saveCompleted.emit(False, error_msg, backup_path)
                    except Exception as e:
                        error_msg = f"An error occurred while saving file: {str(e)}"
                        self.saveCompleted.emit(False, error_msg, backup_path)

                except Exception as e:
                    import traceback
                    error_msg = f"An error occurred while updating geodata: {str(e)}"
                    traceback.print_exc()
                    self.saveCompleted.emit(False, error_msg, "")

        # Create a thread for saving
        self._save_thread = SaveThread(self)

        # Connect callback
        if callback:
            self._save_thread.saveCompleted.connect(callback)

        # Starting thread
        self._save_thread.start()


    def update_geodata_in_json(self, auto_save=True):
        """
        Update changed geodata of original json file with pandapower API.
        If auto_save False, changed geodata kept in memory only.
        Currently support auto save only.
        Note: It is method for synchronous update. For asynchronous update, see update_geodata_in_json_async()
        """
        if not auto_save:
            print("Keep changes in memory without saving.")
            return True

        try:
            import pandapower as pp
            import os
            import shutil
            from datetime import datetime

            original_path = self.uri_parts.get('path', '')
            if not original_path or not os.path.exists(original_path):
                self.pushError(f"The original file cannot be found at: {original_path}")
                return False

            # Create backup of json file before editing (add Date/Time stamp)
            backup_path = f"{original_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            try:
                shutil.copy2(original_path, backup_path)
                print(f"A backup file has been created: {backup_path}")
            except Exception as e:
                print(f"An error occurred while creating backup file: {str(e)}")
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
                    # Copy current geodata (json String) to the original network
                    original_geodata.loc[idx] = current_geodata.loc[idx]

            # Save updated network to json
            try:
                pp.to_json(original_net, original_path)
                print(f"Changed coordinates of {original_path} is successfully saved.")
                return True
            except PermissionError:
                self.pushError(f"Cannot reach to {original_path}. The file may opened in another program or required permissions.")
                return False
            except Exception as e:
                self.pushError(f"An Error occurred while saving: {str(e)}")
                return False

        except Exception as e:
            self.pushError(f"Error occurred while updating geodata: {str(e)}")
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
        # Remove from listener
        NetworkContainer.remove_listener(self.uri, self)
        # Wait until the running save thread completes
        if self._save_thread and self._save_thread.isRunning():
            self._save_thread.wait()
        # Remove custom data provider when it is deleted
        QgsProviderRegistry.instance().removeProvider('PandapowerProvider')