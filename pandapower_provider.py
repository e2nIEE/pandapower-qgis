# 2. version von ppprovider

from qgis.core import QgsVectorDataProvider, QgsVectorLayer, QgsFeature, QgsField, QgsFields, \
    QgsGeometry, QgsPointXY, QgsLineString, QgsWkbTypes, QgsProject, QgsCoordinateReferenceSystem, \
    QgsFeatureRequest, QgsFeatureIterator, QgsFeatureSource, QgsAbstractFeatureSource, QgsFeatureSink, \
    QgsDataProvider, QgsProviderRegistry
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
            print("설마 너냐??????????????????????????????????????????????")
            return

        # 네트워크 데이터 설정
        self.net = network_data['net']
        print("/////////////////////////net 값 뭔지 디버깅", self.net)
        self.type_layer_name = network_data['type_layer_name']
        print("/////////////////////////타입 레이어 네임 뭔지 디버깅", self.type_layer_name)
        if self.uri_parts['network_type'] not in ['bus', 'line', 'junction', 'pipe']:
            raise ValueError("Invalid network_type. Expected 'bus', 'line', 'junction', 'pipe'.")  # necessary?
        else:
            self.network_type = self.uri_parts['network_type']
        self.current_crs = int(network_data['current_crs']) if network_data['current_crs'] else 4326
        self.crs = self.sourceCrs()
        self.vn_kv = None
        self.fields_list = QgsFields()
        self.df = None
        #self.changed_feature_ids = set()

        provider_list = QgsProviderRegistry.instance().providerList()
        print("provider list by init ppprovider", provider_list)
        self._is_valid = True


    def merge_df(self):
        """
        Merges the network type dataframe with its corresponding result dataframe.
        """
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

            print("Merged DataFrame (2):")  # Debugging
            print(self.df.head())

        except Exception as e:
            print(f"Error merging dataframes for {self.network_type}: {str(e)}")
            return pd.DataFrame()  # Return an empty DataFrame in case of error


    def fields(self) -> QgsFields:
        """
        테이블의 필드 정보를 반환합니다.
        지연 초기화(lazy initialization) 패턴을 사용하여 실제로 필요할 때만 데이터베이스를 조회합니다.
        """
        if not self.fields_list:  # 첫 호출 시에만 데이터베이스를 조회합니다
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


    def capabilities(self) -> QgsVectorDataProvider.Capabilities:
        return (
            #QgsVectorDataProvider.CreateSpatialIndex | QgsVectorDataProvider.SelectAtId |
            QgsVectorDataProvider.AddFeatures |  # 피처 추가
            QgsVectorDataProvider.DeleteFeatures |  # 피처 삭제
            QgsVectorDataProvider.ChangeAttributeValues |  # 속성값 변경
            QgsVectorDataProvider.AddAttributes |  # 속성 필드 추가
            QgsVectorDataProvider.DeleteAttributes  # 속성 필드 삭제
        )


    def crs(self):
        return self.sourceCrs()

    def sourceCrs(self):
        crs = QgsCoordinateReferenceSystem.fromEpsgId(int(self.current_crs))
        if not crs.isValid():
            raise ValueError(f"CRS ID {self.current_crs} is not valid.")
        print(f"CRS is valid: {crs.authid()}") # Debugging
        return crs

    def name(self):
        return "PandapowerProvider"

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