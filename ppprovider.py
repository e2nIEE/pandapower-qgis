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

from qgis.core import QgsVectorDataProvider, QgsVectorLayer, QgsFeature, QgsField, QgsFields, \
    QgsGeometry, QgsPoint, QgsLineString, QgsWkbTypes, QgsProject, QgsCoordinateReferenceSystem, \
    QgsFeatureRequest, QgsFeatureIterator, QgsFeatureSource
from qgis.PyQt.QtCore import QVariant
import json
import pandas as pd
import pandapower as pp


class PandapowerFeatureSource(QgsFeatureSource):
    def __init__(self, provider):
        self.provider = provider


def convert_dtype_to_qvariant(dtype):
    if pd.api.types.is_integer_dtype(dtype):
        return QVariant.Int
    elif pd.api.types.is_unsigned_integer_dtype(dtype):
        return QVariant.UInt
    elif pd.api.types.is_float_dtype(dtype):
        return QVariant.Double
    elif pd.api.types.is_bool_dtype(dtype):
        return QVariant.Bool
    elif pd.api.types.is_string_dtype(dtype):
        return QVariant.String
    elif pd.api.types.is_object_dtype(dtype):   # object is string?
        return QVariant.String
    else:
        print("Unexpected dtype detected. Add it or check if it is not available.")
        return QVariant.Invalid


class PandapowerProvider(QgsVectorDataProvider):
    def __init__(self, net, network_type, current_crs=False, uri=None):
        # Call the constructor of the parent class # optional
        self.uri = uri
        providerOptions = QgsDataProvider.ProviderOptions()
        flags = QgsDataProvider.ReadFlags()
        super().__init__(self.uri, providerOptions, flags)

        self.net = net
        if network_type not in ['bus', 'line', 'junction', 'pipe']:
            raise ValueError("Invalid network_type. Expected 'bus', 'line', 'junction', 'pipe'.")  # necessary?
        self.network_type = network_type
        self.layer = None
        self.fields_list = QgsFields()
        self.current_crs = current_crs if current_crs else "EPSG:4326"
        self.crs = self.sourceCrs()
        # self.non_vector_data = {}

        self.create_layers()

    def create_layers(self):
        # get a pandapower dataframe of a specific network type
        df = getattr(self.net, self.network_type)

        # generate fields_list dynamically from column of the dataframe
        for column in df.columns:
            dt = df[column].dtype
            qv = convert_dtype_to_qvariant(dt)
            self.fields_list.append(QgsField(column, qv))

        self.layer = QgsVectorLayer(f"Point?crs={self.crs.authid()}", self.network_type, "memory")
        self.layer.addAttributes(self.fields_list)
        self.layer.updateFields()  # check updateFields() of parent

        self.populate_features()

    def populate_features(self):
        features = []

        # Populate features
        for idx, row in getattr(self.net, self.network_type).iterrows():
            feature = QgsFeature()

            # Set geometry based on network type
            if self.network_type in ['bus', 'junction']:
                geo_data = row.get('geo', '{}')
                if isinstance(geo_data, str):
                    geo_data = json.loads(geo_data)
                feature.setGeometry(
                    QgsGeometry.fromPointXY(QgsPoint(geo_data['coordinates'][0], geo_data['coordinates'][1])))
            elif self.network_type in ['line', 'pipe']:
                from_geo = row['from_geo']
                to_geo = row['to_geo']
                feature.setGeometry(QgsGeometry.fromPolylineXY([
                    QgsPoint(from_geo['coordinates'][0], from_geo['coordinates'][1]),
                    QgsPoint(to_geo['coordinates'][0], to_geo['coordinates'][1])
                ]))

            # Collect attributes dynamically
            attributes = []
            for field in self.fields_list:
                field_name = field.name()
                if field_name in row:
                    attributes.append(row[field_name])
                else:
                    attributes.append(None)

            feature.setAttributes(attributes)
            features.append(feature)

        self.layer.addFeatures(features)
            ########################################################### 수정할것
            ##### need? oder doppeltarbeit? populatefeature selbst ist adding features
        self.update_layer()

    def update_pandapower_net(self):  # tmp idea
        bus_layer = self.layers["buses"]
        for feature in bus_layer.getFeatures():
            idx = feature.id()
            self.net.bus.at[idx, 'name'] = feature['name']
            self.net.bus.at[idx, 'vn_kv'] = feature['vn_kv']
            self.net.bus.at[idx, 'type'] = feature['type']
            self.net.bus.at[idx, 'zone'] = feature['zone']
            self.net.bus.at[idx, 'in_service'] = feature['in_service']
            self.net.bus.at[idx, 'geo'] = feature['geo']
            # Restore non-vector data
            for key, value in self.non_vector_data[f"bus {idx}"].items():
                self.net.bus.at[idx, key] = value

    def featureSource(self):
        return PandapowerFeatureSource(self)

    # Returns the permanent storage type for this layer as a friendly name.
    def storageType(self):
        return f"{self.network_type} layer is Pandapower Network in json format"

    # filter with id and type? no... it returns feature"s"  iterator
    # but what does request look like
    def getFeatures(self, request=QgsFeatureRequest()):
        return self.layer.getFeatures(request)  # QgsVectorLayer.getFeatures()

    def wkbType(self):
        if self.network_type == 'bus' or self.network_type == 'junction':
            return QgsWkbTypes.Point
        elif self.network_type == 'line' or self.network_type == 'pipe':
            return QgsWkbTypes.Line

    def featureCount(self):
        """
        Returns the number of features in the provider.
        :return: Number of features.
        :rtype: int
        """
        try:
            df = getattr(self.net, self.network_type)
            return len(df)
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
        return QgsCoordinateReferenceSystem(self.current_crs)

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
        데이터프레임의 변경사항을 벡터 레이어에 반영합니다.
        :param provider: PandapowerProvider 객체
        """
        self.populate_features()  # 피처를 다시 생성하여 벡터 레이어에 추가
        # 그럼 그냥 populate만 호출하면 되는 거아님? 굳이 함수로? 그런데 populate 너무 과도한 거 아님?

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
        """
        try:
            # Add features to Pandapower dataframe
            df = getattr(self.net, self.network_type)

            # Validation of Field Structure for Added Features
            for feature in feature_list:
                if feature.fields().names() != [field.name() for field in self.fields_list]:
                    raise ValueError("Feature fields do not match the existing fields list")

            # Add feature to pandapower dataframe
            for feature in feature_list:
                new_row = {}
                # Save attribute to field of new row
                for i, field in enumerate(self.fields_list):
                    new_row[field.name()] = feature.attribute(i)
                df = df.append(new_row, ignore_index=True)

            self.update_layer()
            return True
        except Exception as e:
            self.pushError(f"Failed to add features: {str(e)}")
            return False"""
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
                    pass
                else:
                    raise ValueError(f"Unsupported network_type '{self.network_type}'")

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
            df = getattr(self.net, self.network_type)

            # 삭제할 피처의 ID 리스트를 반복하면서 데이터프레임에서 삭제
            for feature_id in ids:
                df = df.drop(feature_id)  # inplace=True, then data removed from original df. Default returns new df
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
            df = getattr(self.net, self.network_type)

            # Change value of attribute in field of changed feature
            for feature_id, changed_map in attr_map.items():
                for attr_index, new_value in changed_map.items():
                    field_name = self.fields_list[attr_index].name()
                    df.at[feature_id, field_name] = new_value

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
            '''
            df = getattr(self.net, self.network_type)

            # Convert new geometry value as pandapower dataframe format and save it
            for feature_id, new_geometry in geometry_map.items():
                if self.network_type in ['bus', 'junction']:
                    df.at[feature_id, 'geo'] = json.dumps({
                        'type': 'Point',
                        'coordinates': [new_geometry.asPoint().x(), new_geometry.asPoint().y()]
                    })
                elif self.network_type in ['line', 'pipe']:
                    df.at[feature_id, 'from_geo'] = json.dumps({
                        'type': 'Point',
                        'coordinates': [new_geometry.asPolyline()[0].x(), new_geometry.asPolyline()[0].y()]
                    })
                    df.at[feature_id, 'to_geo'] = json.dumps({
                        'type': 'Point',
                        'coordinates': [new_geometry.asPolyline()[-1].x(), new_geometry.asPolyline()[-1].y()]
                    })'''

            # 변경된 지오메트리를 벡터 레이어에 반영
            for feature_id, new_geometry in geometry_map.items():
                # 벡터 레이어의 피처 지오메트리 업데이트
                feature = QgsFeature()
                if self.layer.getFeatures(QgsFeatureRequest(feature_id)).nextFeature(feature):
                    feature.setGeometry(new_geometry)
                    self.layer.updateFeature(feature) ##############작성할 것

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
            # Check if both operations were successful
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
            # Add attributes to the internal fields list
            for attribute in attributes:
                self.fields_list.append(attribute)
            self.layer.updateFields()
            return success
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
            # Delete attributes from the layer's data provider
            success = self.layer.dataProvider().deleteAttributes(attributesIds)
            if success:
                self.layer.updateFields()
            return success
        except Exception as e:
            self.pushError(f"Failed to delete attributes: {str(e)}")
            return False

    def renameAttributes(self):
        pass








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