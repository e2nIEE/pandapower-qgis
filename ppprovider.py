"""QGIS에서 데이터 소스를 직접 GeoJSON으로 변환하지 않고 pandapower 객체를 벡터로 변환하려면
QgsVectorDataProvider 클래스를 오버라이딩해야 합니다. 아래 단계에 따라 작업을 진행할 수 있습니다:

1. QgsVectorDataProvider 클래스 오버라이딩:
QgsVectorDataProvider 클래스를 상속받아 pandapower 객체를 처리하는 커스텀 프로바이더를 만듭니다.

2. 필드 정의:
벡터 레이어에 포함될 필드를 정의합니다.

3. 피처 생성:
pandapower 객체의 데이터를 읽어 QGIS 피처로 변환합니다.

4. 벡터 레이어 생성:
커스텀 프로바이더를 사용하여 QGIS 벡터 레이어를 만듭니다."""

# overwrite qgis.core.QgsVectorDataProvider.h

# print("Before settrace")
# import pydevd_pycharm
# pydevd_pycharm.settrace('127.0.0.1', port=53100, stdoutToServer=True, stderrToServer=True)

from qgis.core import QgsVectorDataProvider, QgsVectorLayer, QgsFeature, QgsField, QgsFields, \
    QgsGeometry, QgsPointXY, QgsLineString, QgsWkbTypes, QgsProject, QgsCoordinateReferenceSystem, \
    QgsFeatureRequest, QgsFeatureIterator, QgsFeatureSource, QgsAbstractFeatureSource, QgsFeatureSink, \
    QgsDataProvider
from qgis.PyQt.QtCore import QMetaType
import json
import pandas as pd
import pandapower as pp


class PandapowerFeatureSource(QgsAbstractFeatureSource):
    def __init__(self, provider):
        super().__init__()
        self.provider = provider

    def getFeatures(self, request):
        # 여기서 PandapowerProvider의 데이터를 사용하여 피처를 생성하고 반환합니다.
        # 이 예제에서는 PandapowerProvider의 getFeatures 메소드를 호출합니다.
        return self.provider.getFeatures(request)


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
    def __init__(self, net, type_layer_name, network_type, current_crs, uri=None):
        # Call the constructor of the parent class # optional
        self.uri = uri
        providerOptions = QgsDataProvider.ProviderOptions()
        flags = QgsDataProvider.ReadFlags()
        super().__init__(self.uri, providerOptions, flags)

        self.net = net
        self.type_layer_name = type_layer_name
        if network_type not in ['bus', 'line', 'junction', 'pipe']:
            raise ValueError("Invalid network_type. Expected 'bus', 'line', 'junction', 'pipe'.")  # necessary?
        self.network_type = network_type
        self.layer = None
        self.fields_list = QgsFields()
        self.current_crs = current_crs if current_crs else 4326
        self.crs = self.sourceCrs()
        self.df = None

        self.create_layers()

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

    def create_layers(self):
        """
        Create a QgsVectorLayer and generate fields from pandapower network.
        """
        # get a pandapower dataframe of a specific network type
        # df = getattr(self.net, self.network_type)
        self.merge_df()

        # Check if dataframe is empty
        if self.df.empty:
            print(f"No data available for network type: {self.network_type}, called in create_layers")  # Debugging
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
        self.layer = QgsVectorLayer(f"{geometry_type}?crs={self.crs.authid()}", self.type_layer_name, "memory")

        # add fields(attribute fields) to layer
        self.layer.startEditing()
        for field in self.fields_list:
            if not self.layer.addAttribute(field):
                raise RuntimeError(f"Failed to add attribute: {field.name()}")
            # print(f"Added attribute fields to layer: {field.name()}")  # Debugging
        self.layer.commitChanges()

        self.layer.updateFields()  # check updateFields() of parent
        print(f"Layer CRS after creation: {self.layer.crs().authid()}")  # Debugging
        self.populate_features()

    def populate_features(self):
        """
        Populates the QgsVectorLayer with features from pandapower network.
        This function iterates over the rows of the Pandapower DataFrame, creates a QgsFeature for each row,
        sets the feature's geometry and attributes based on the row data, and adds the feature to the QgsVectorLayer.
        """
        # df = getattr(self.net, self.network_type)
        features = []

        print(f"Populating features for network type: {self.network_type}")  # Debugging
        print(f"Number of rows in dataframe: {len(self.df)}")
        print(f"Number of unique indices in dataframe: {len(self.df.index.unique())}")
        print(f"Layer CRS before adding features: {self.layer.crs().authid()}")  # Debugging

        # Populate features
        for idx, row in self.df.iterrows():
            feature = QgsFeature()

            # Set geometry based on network type
            if self.network_type in ['bus', 'junction']:
                geo_data = row.get('geo', '{}')
                if isinstance(geo_data, str):
                    geo_data = json.loads(geo_data)
                coordinates = geo_data.get('coordinates', [0, 0])
                # print(f"Bus/Junction coordinates for index {idx}: {coordinates}")  # Debugging #########
                if not coordinates:
                    print(f"Warning: No coordinates found for index {idx}")  # Debugging
                feature.setGeometry(
                    QgsGeometry.fromPointXY(QgsPointXY(coordinates[0], coordinates[1])))
            elif self.network_type in ['line', 'pipe']:
                geo_data = row.get('geo', '{}')
                if isinstance(geo_data, str):
                    geo_data = json.loads(geo_data)
                coordinates = geo_data.get('coordinates', [])
                if not coordinates:
                    print(f"Warning: No coordinates found for index {idx}")  # Debugging
                # print(f"Line/Pipe coordinates for index {idx}: {coordinates}")  # Debugging ############
                if not coordinates:
                    print(f"Warning: No coordinates found for index {idx}")  # Debugging
                # Turn Coord into QgsPoint Object
                points = [QgsPointXY(coord[0], coord[1]) for coord in coordinates]
                # Create QgsLineString Object
                linestring = QgsLineString(points)
                feature.setGeometry(QgsGeometry(linestring))

            # Check if geometry is valid
            if not feature.geometry().isGeosValid():
                print(f"Invalid geometry for feature at index {idx}")

            # Collect attributes dynamically
            attributes = []
            for field in self.fields_list:
                field_name = field.name()
                if field_name in row:
                    attributes.append(row[field_name])
                else:
                    attributes.append(None)
            # print(f"Debugging: Attributes for index {idx}: {attributes}")  # Debugging ####################

            feature.setAttributes(attributes)
            features.append(feature)

        print(f"Debugging: Number of features created: {len(features)}")  # Debugging
        print(f"Debugging: Layer CRS after adding to project: {self.layer.crs().authid()}")  # Debugging

        self.layer.addFeatures(features)
        self.update_layer()

    def featureSource(self):
        return PandapowerFeatureSource(self)

    def storageType(self):
        """
        Returns the permanent storage type for this layer as a friendly name.
        """
        return f"{self.network_type} layer is Pandapower Network in json format"

    # filter with id and type? no... it returns feature"s"  iterator
    # but what does request look like
    def getFeatures(self, request=QgsFeatureRequest()):
        return self.layer.getFeatures(request)  # QgsVectorLayer.getFeatures()

    def wkbType(self):
        if self.network_type == 'bus' or self.network_type == 'junction':
            return QgsWkbTypes.Point
        elif self.network_type == 'line' or self.network_type == 'pipe':
            return QgsWkbTypes.LineString

    def featureCount(self):
        """
        Returns the number of features in the provider.

        :return: Number of features.
        :rtype: int
        """
        try:
            # df = getattr(self.net, self.network_type)
            return len(self.df)
        except Exception as e:
            self.pushError(f"Failed to count features: {str(e)}")
            return 0
        # return self.layer.featureCount()

    def fields(self):
        return self.fields_list

    @staticmethod
    def name():
        return "Pandapower Provider"

    # vllt unnötig?
    def sourceCrs(self):
        crs = QgsCoordinateReferenceSystem.fromEpsgId(self.current_crs)
        if not crs.isValid():
            raise ValueError(f"CRS ID {self.current_crs} is not valid.")
        print(f"CRS is valid: {crs.authid()}") # Debugging
        return crs

    @staticmethod
    def get_provider_name():
        return "Pandapower Provider"

    def update_layer(self):
        self.layer.updateExtents()
        self.layer.triggerRepaint()

    def update_fields(self):
        pass

    def update_layer_from_changed_dataframe(self):
        """
        Updates the vector layer to reflect changes in the DataFrame.
        """
        pass

    def update_pandapower_net(self):
        """
        Update Pandapower Net based on current QGIS Layer.
        Compare to changeAttributeValues, it is not for direct change,
        it updates all changes. (written just in case)
        """
        for feature in self.layer.getFeatures():
            idx = feature.id()
            for field in self.fields():
                field_name = field.name()
                getattr(self.net, self.network_type).at[idx, field_name] = feature[field_name]

    def addFeatures(self, feature_list, flags=QgsFeatureSink.Flags()):
        """
        Adds features to the data source.

        :param feature_list: List of features to add.
        :type feature_list: QgsFeatureList
        :param flags: Optional flags for feature addition.
        :type flags: QgsFeatureSink.Flags
        :return: True if features were added successfully, False otherwise.
        :rtype: bool
        """
        try:
            for feature in feature_list:
                # Validate that the feature fields match the existing fields list
                if feature.fields().names() != [field.name() for field in self.fields_list]:
                    raise ValueError("Feature fields do not match the existing fields list")
                # what if when feature with extra field must be added?

            for feature in feature_list:
                # Collect attributes dynamically
                attributes = {}
                for field_name in feature.fields().names():
                    attributes[field_name] = feature.attribute(field_name)

                # Convert geodata to appropriate format if it is a string
                if 'geo' in attributes and isinstance(attributes['geo'], str):
                    attributes['geo'] = json.loads(attributes['geo'])

                # Add features based on network_type          # line, trafo...?
                if self.network_type == 'bus':
                    # Ensure that 'vn_kv' is present in attributes
                    if 'vn_kv' not in attributes:
                        raise ValueError("Missing required attribute 'vn_kv'")
                    # Use pandapower API to create a bus with dynamic attributes
                    pp.create_bus(self.net, **attributes)
                elif self.network_type == 'line':
                    # Ensure that required attributes are present
                    required_attrs = ['from_bus', 'to_bus', 'length_km', 'std_type']
                    for attr in required_attrs:
                        if attr not in attributes:
                            raise ValueError(f"Missing required attribute '{attr}' for line")
                    # Use pandapower API to create a line with dynamic attributes
                    pp.create_line(self.net, **attributes)
                else:
                    raise ValueError(f"Unsupported network_type '{self.network_type}'")

            self.layer.addFeatures(feature_list)
            self.update_layer()
            return True
        except Exception as e:
            self.pushError(f"Failed to add features: {str(e)}")
            return False

    def deleteFeatures(self, ids):
        """
        Deletes one or more features from the provider.

        :param ids: List containing feature ids to delete.
        :type ids: QgsFeatureIds
        :return: True if features were deleted successfully, False otherwise.
        :rtype: bool
        """
        try:
            self.layer.startEditing()

            # Delete features from the Pandapower network
            for feature_id in ids:
                if self.network_type == 'bus':
                    pp.drop_buses(self.net, feature_id)
                elif self.network_type == 'line':
                    pp.drop_lines(self.net, feature_id)
                # elif self.network_type == 'junction':
                #    pp.drop_junctions(self.net, feature_id)
                # elif self.network_type == 'pipe':
                #    pp.drop_pipes(self.net, feature_id)
                else:
                    raise ValueError(f"Unsupported network_type '{self.network_type}'")
            # Delete features from the QGIS layer
            self.layer.deleteFeatures(ids)

            self.layer.commitChanges()
            self.update_layer()
            return True
        except Exception as e:
            self.pushError(f"Failed to delete features: {str(e)}")
            return False

    def changeAttributeValues(self, attr_map):
        """
        Changes attribute values of existing features.

        :param attr_map: A map containing changed attributes.
        :type attr_map: typedef QMap<QgsFeatureId, QgsAttributeMap> QgsChangedAttributesMap
        :return: True if attributes were changed successfully, False otherwise.
        :rtype: bool
        """
        try:
            # df = getattr(self.net, self.network_type)

            # Change value of attribute in field of changed feature
            for feature_id, changed_map in attr_map.items():
                for attr_index, new_value in changed_map.items():
                    field_name = self.fields_list[attr_index].name()
                    self.df.at[feature_id, field_name] = new_value

            # Change attribute values in the QGIS layer
            self.layer.dataProvider().changeAttributeValues(attr_map)
            self.update_layer()
            return True
        except Exception as e:
            self.pushError(f"Failed to change attribute values: {str(e)}")
            return False

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
        try:
            self.layer.startEditing()

            for feature_id, new_geometry in geometry_map.items():
                # Apply changed geometry to pandapower network
                if self.network_type in ['bus', 'junction']:
                    new_geo_value = [new_geometry.asPoint().x(), new_geometry.asPoint().y()]
                    self.net.bus.at[feature_id, 'geo'] = new_geo_value
                elif self.network_type in ['line', 'pipe']:
                    new_geo_value = [[point.x(), point.y()] for point in new_geometry.asPolyline()]
                    self.net.line.at[feature_id, 'geo'] = new_geo_value

                # Apply changed geometry to vector layer
                self.layer.changeGeometry(feature_id, new_geometry)

            self.layer.commitChanges()
            self.update_layer()
            return True
        except Exception as e:
            self.pushError(f"Failed to change geometries: {str(e)}")
            return False

    def changeFeatures(self, attr_map, geometry_map):
        """
        Changes attribute values and geometries of existing features.

        :param attr_map: A map containing changed attributes.
        :type attr_map: QgsChangedAttributesMap
        :param geometry_map: A QgsGeometryMap whose index contains the feature IDs
            that will have their geometries changed.
            The second map parameter being the new geometries themselves.
        :type geometry_map: QgsGeometryMap
        :return: True if features were changed successfully, False otherwise.
        :rtype: bool
        """
        try:
            attr_success = self.changeAttributeValues(attr_map)
            geom_success = self.changeGeometryValues(geometry_map)
            success = attr_success and geom_success
            return success
        except Exception as e:
            self.pushError(f"Failed to change features: {str(e)}")
            return False

    def addAttributes(self, attributes):
        """
        Adds new attributes to the provider.

        :param attributes: List of attributes to add.
        :type attributes: QList[QgsField]
        :return: True if attributes were added successfully, False otherwise.
        :rtype: bool
        """
        try:
            # df = getattr(self.net, self.network_type)
            self.layer.startEditing()

            for attribute in attributes:
                # add to fields_list of instance
                self.fields_list.append(attribute)
                # add to pandapower
                self.df[attribute.name()] = pd.Series(dtype=attribute.typeName())
                # add to layer
                self.layer.addAttribute(attribute)

            self.layer.commitChanges()
            self.layer.updateFields()
            return True
        except Exception as e:
            self.pushError(f"Failed to add attributes: {str(e)}")
            return False

    def deleteAttributes(self, attributesIds):
        """
        Deletes existing attributes from the provider.

        :param attributesIds: A set containing indices of attributes to delete.
        :type attributesIds: QgsAttributeIds
        :return: True if attributes were deleted successfully, False otherwise.
        :rtype: bool
        """
        try:
            # df = getattr(self.net, self.network_type)
            self.layer.startEditing()

            # Delete attributes from the internal fields list and the pandas DataFrame
            for attr_id in attributesIds:
                attr_name = self.fields_list[attr_id].name()

                # delete from fields_list of instance
                self.fields_list.remove(self.fields_list[attr_id])
                # delete from pandapower
                self.df.drop(columns=[attr_name], inplace=True)
                # delete from layer
                self.layer.deleteAttribute(attr_id)

            self.layer.commitChanges()
            self.layer.updateFields()
            return True
        except Exception as e:
            self.pushError(f"Failed to delete attributes: {str(e)}")
            return False

    def renameAttributes(self):
        pass

print('Ende des ppprovider')

'''
# Usage example:
net = pp.from_json("path_to_your_file.json")

# Create custom provider
provider = PandapowerProvider(net, network_type="bus")

# Create vector layer
layer = QgsVectorLayer(provider, "Pandapower Network", "memory")

# Add layer to QGIS project
QgsProject.instance().addMapLayer(layer)

# Example of updating non-vector data
provider.update_non_vector_data('bus 0', 'new_key', 'new_value')

# Update pandapower net with changes made in QGIS
provider.update_pandapower_net()  ##### pandapower 네트워크 업데이트
'''