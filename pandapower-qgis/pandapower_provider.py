from qgis.core import QgsVectorDataProvider, QgsVectorLayer, QgsFeature, QgsField, QgsFields, \
    QgsGeometry, QgsPointXY, QgsLineString, QgsWkbTypes, QgsProject, QgsCoordinateReferenceSystem, \
    QgsFeatureRequest, QgsFeatureIterator, QgsFeatureSource, QgsAbstractFeatureSource, QgsFeatureSink, \
    QgsDataProvider, QgsProviderRegistry, QgsRectangle
from qgis.PyQt.QtCore import QMetaType
import json
import pandas as pd
import pandapower as pp
# import pandapipes as ppi
import os
from . import pandapower_feature_iterator, pandapower_feature_source
from .network_session import NetworkSession, KIND_POWER, KIND_PIPES, DEFAULT_EPSG, add_vn_kv_to_lines
from .pandapower_uri import decode_uri, has_geometry, layer_name_for, LEVELLED_TABLES
from .provider_utils import MessageManager


def convert_dtype_to_qmetatype(dtype):
    """
    Convert pandas data type (dtype) to corresponding Qt data type (QMetatype) for QGIS field definition.
    Note: It does not convert actual values. It just returns the corresponding Qt data type for the given pandas data type.
    Args:
        dtype: Pandas data type to convert
    Returns:
        QMetaType: Corresponding Qt data type, QMetaType.Invalid if not recognized
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
        print(f"Unexpected dtype detected: {dtype}. Add it or check if it is not available.")
        return QMetaType.Invalid


class PandapowerProvider(QgsVectorDataProvider):
    @classmethod
    def createProvider(cls, uri, providerOptions = QgsDataProvider.ProviderOptions(), flags = QgsDataProvider.ReadFlags()):
        """
        Factory methode that create provider instance.
        Args:
            uri: Data source URI containing network information
            providerOptions: Provider-specific options for data access
            flags: Read flags for data provider behavior
        Returns:
            PandapowerProvider: New provider instance
        """
        return PandapowerProvider(uri, providerOptions, flags)


    def __init__(self, uri = "", providerOptions = QgsDataProvider.ProviderOptions(), flags = QgsDataProvider.ReadFlags()):
        """
        Initialize the pandapower data provider from the shared NetworkSession.
        Sets up network type, coordinate system, and joins the session so that every
        layer of the same file operates on one and the same network object.
        Args:
            uri: Data source URI identifying the network and network type
            providerOptions: Provider-specific configuration options
            flags: Read flags controlling provider behavior
        """
        super().__init__(uri)
        # Bring metadata instace from registry
        metadata_provider = QgsProviderRegistry.instance().providerMetadata("PandapowerProvider")
        self.uri = uri
        self.uri_parts = metadata_provider.decodeUri(uri)
        # Normalise to the current URI scheme, accepting the pre-rework keys so
        # that projects saved by an earlier version still open (plan section 3.5).
        parts = decode_uri(self.uri_parts)
        self.parts = parts
        self._provider_options = providerOptions
        self._flags = flags

        # Initialize all attributes with default values (prevents AttributeError while reopen qgis project file)
        self._is_valid = False
        self.session = None
        self.net = None
        self._commit_connected = False
        # 'network_type' is the table this layer exposes. The name is kept for
        # the many internal uses; only the URI key was renamed to 'table'.
        self.network_type = parts['table']
        self.type_layer_name = None
        self.current_crs = None
        self.crs = None
        self.fields_list = None
        self.df = None
        self._extent = None
        self.vn_kv = None
        self.pn_bar = None

        file_path = parts['path']
        if not self.network_type:
            MessageManager.show_error(
                "Network Load Failed",
                "The layer URI names no pandapower table."
            )
            return  # Safe early return - all attributes already initialized

        # Only the two pipe-specific tables imply a pandapipes file. Every other
        # table name (bus, line, trafo, load, ...) exists in a pandapower net,
        # and tables such as 'trafo' exist in both, so the kind cannot be
        # inferred from the table name alone for those.
        kind = KIND_PIPES if self.network_type in ('junction', 'pipe') else KIND_POWER

        epsg = int(parts['epsg'] or DEFAULT_EPSG)

        # Join the session for this file, loading the network only if this is the
        # first layer to open it. Every other layer of the same file reuses the
        # very same net object.
        try:
            self.session = NetworkSession.acquire(
                file_path,
                lambda: self._load_network_from_file(file_path, kind),
                epsg=epsg,
                kind=kind
            )
        except Exception as e:
            MessageManager.show_error("Network Load Failed", str(e))
            return  # Safe early return - all attributes already initialized

        self.net = self.session.net

        # The table must actually exist on the loaded network. Without this an
        # unknown name would surface much later as an obscure AttributeError.
        table_df = getattr(self.net, self.network_type, None)
        if table_df is None or not isinstance(table_df, pd.DataFrame):
            MessageManager.show_error(
                "Network Load Failed",
                f"The network has no table named '{self.network_type}'."
            )
            self.session.release()
            self.session = None
            return  # Safe early return - all attributes already initialized

        self.current_crs = self.session.epsg
        self.crs = self.sourceCrs()

        # Voltage / pressure level this layer is filtered to. Absent for layers
        # that cover a whole table rather than one level. Only bus/line and
        # junction/pipe can be filtered by level; other tables ignore it.
        level = parts['level']
        if level and self.network_type in LEVELLED_TABLES:
            if kind == KIND_POWER:
                self.vn_kv = float(level)
            else:
                self.pn_bar = float(level)

        self.type_layer_name = layer_name_for(file_path, self.network_type, level)

        self._is_valid = True

        # Join the session so sibling layers can be notified of changes.
        self.session.add_provider(self)

        # Write on commit rather than on every change (plan section 3.7). The
        # layer does not exist yet at provider construction time, so the
        # connection is made lazily from _connect_commit_signal().
        self._commit_connected = False


    @property
    def network_data(self):
        """
        Network data dictionary, derived from the session on demand.
        Kept as a property for the call sites that still expect the old dict shape;
        it is a view onto the session rather than a stored copy, so it can never go
        stale the way the previous instance attribute could.
        Returns:
            dict: Network data, or None if the provider is not valid
        """
        if self.session is None:
            return None
        return {
            'net': self.session.net,
            'vn_kv': self.vn_kv,
            'pn_bar': self.pn_bar,
            'type_layer_name': self.type_layer_name,
            'network_type': self.network_type,
            'current_crs': self.session.epsg
        }


    @staticmethod
    def _load_network_from_file(file_path, kind):
        """
        Load a pandapower network from a JSON file.
        Called by NetworkSession only when the file is not already open, so this
        runs once per file rather than once per layer.
        Args:
            file_path: Path of the network JSON file
            kind: KIND_POWER or KIND_PIPES
        Returns:
            The loaded network object
        Raises:
            ValueError: If the path is empty, missing, or the kind is unsupported
        """
        if not file_path:
            raise ValueError("File path is empty")
        if not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")

        if kind == KIND_PIPES:
            # pandapipes support is planned but not integrated yet (plan section 5.4).
            raise ValueError("Pipe networks not yet implemented")

        net = pp.from_json(file_path)
        # Add vn_kv column to lines, so line layers can be filtered by the
        # voltage level of their from_bus.
        add_vn_kv_to_lines(net)
        return net


    def merge_df(self):
        """
        Merge dataframe of network_type(ex. bus, line) with its corresponding result dataframe
        to make a integrated dataframe of a layer.
        Applies filtering based on vn_kv (electrical) or pn_bar (gas) values
        and handles cases where calculation results may be missing.
        """
        try:
            # Get the dataframes for the network type and its result.
            # Not every table has a res_* twin (e.g. 'switch'), and a res_*
            # table is its own source with no second result table behind it.
            df_network_type = getattr(self.net, self.network_type)
            df_res_network_type = getattr(self.net, f'res_{self.network_type}', None)

            if hasattr(self, 'vn_kv') and self.vn_kv is not None:
                if self.network_type == 'bus':
                    filtered_indices = df_network_type[df_network_type['vn_kv'] == self.vn_kv].index
                    df_network_type = df_network_type.loc[filtered_indices]

                elif self.network_type == 'line':
                    # Get only specific vn_kv buses
                    bus_df = getattr(self.net, 'bus')
                    bus_indices = bus_df[bus_df['vn_kv'] == self.vn_kv].index

                    # Use from_bus only - check add_column_from_node_to_elements() of data_modification.py
                    filtered_indices = df_network_type[
                        df_network_type['from_bus'].isin(bus_indices)
                    ].index

                    df_network_type = df_network_type.loc[filtered_indices]

            # elif hasattr(self, 'pn_bar') and self.pn_bar is not None:
            #     if self.network_type == 'junction' and 'pn_bar' in df_network_type.columns:
            #         filtered_indices = df_network_type[df_network_type['pn_bar'] == self.pn_bar].index
            #         df_network_type = df_network_type.loc[filtered_indices]

            # Determine the situation
            has_result_data = (df_res_network_type is not None and
                               not df_res_network_type.empty and
                               len(df_res_network_type) > 0)

            # Process based on the presence or absence of result data
            if has_result_data:
                # Filter the result data to match the indices of the filtered base data
                available_indices = df_network_type.index
                df_res_network_type = df_res_network_type.loc[
                    df_res_network_type.index.intersection(available_indices)
                ]

                # Sort indices (ensure data consistency)
                df_network_type.sort_index(inplace=True)
                df_res_network_type.sort_index(inplace=True)

                # Merge data
                self.df = pd.merge(df_network_type, df_res_network_type, left_index=True,
                    right_index=True, how='left', suffixes=('', '_res'))

            # when res column of json file is empty
            else:
                # Copy only the base data
                self.df = df_network_type.copy()

                # Add empty result columns (only if the result data structure exists)
                if df_res_network_type is not None:
                    res_columns = df_res_network_type.columns.tolist()
                    for col_name in res_columns:
                        self.df[col_name] = None  # Initialize all result columns to None

            if self.df.empty:
                if self.vn_kv is not None:
                    detail = f"for voltage level {self.vn_kv} kV"
                elif self.pn_bar is not None:
                    detail = f"for pressure level {self.pn_bar} bar"
                else:
                    detail = "in this network"
                MessageManager.show_warning(
                    "Empty Layer",
                    f"No {self.network_type} elements found {detail}"
                )
                # Fall through: the meta columns are added below even for an
                # empty table, so the layer still reports a consistent field
                # list instead of no fields at all.

            # Add meta columns
            # pp_type: Network type (bus, line, junction, pipe, ...)
            self.df.insert(0, 'pp_type', self.network_type)
            # pp_index: Index in the original pandapower network
            self.df.insert(1, 'pp_index', self.df.index)

        except Exception as e:
            MessageManager.show_error(
                "Data Processing Error",
                f"Failed to merge dataframe of {self.network_type}: {str(e)}"
            )
            self.df = pd.DataFrame()  # Return an empty DataFrame on error


    def fields(self) -> QgsFields:
        """
        Return field list.
        Using lazy initialization pattern, search database only when it needed.
        Returns:
            QgsFields: Collection of field definitions with appropriate data types
        """
        # if not self.fields_list:
        if not hasattr(self, 'fields_list') or not self.fields_list:
            self.fields_list = QgsFields()

            self.merge_df()

            if self.df is None:
                return QgsFields()

            # generate fields_list dynamically from column of the dataframe.
            # An empty table still yields its columns, so the layer reports a
            # consistent field list rather than none at all.
            for column in self.df.columns:
                dt = self.df[column].dtype
                qm = convert_dtype_to_qmetatype(dt)
                self.fields_list.append(QgsField(column, qm))

        # When fields are ready, set attribute form for addFeatrures dialog
        self._setup_attribute_form()

        return self.fields_list


    def getFeatures(self, request=QgsFeatureRequest()):
        """
        Create and return a feature iterator for accessing network features.
        Args:
            request: Feature request specifying filters and transformations
        Returns:
            QgsFeatureIterator: Iterator for accessing pandapower network features
        """
        return QgsFeatureIterator(
            pandapower_feature_iterator.PandapowerFeatureIterator(
                pandapower_feature_source.PandapowerFeatureSource(self), request
            )
        )

    # =====================================================================================

    def changeGeometryValues(self, geometry_map):
        """
        Update geometries of existing features in the shared network.
        Handles both point geometries (bus/junction) and line geometries (line/pipe).
        Nothing is written to disk here: the file is written once when the user
        commits the layer's edit buffer (see _on_layer_committed).
        Args:
            geometry_map: Map of feature IDs to new QgsGeometry objects
        Returns:
            bool: True if the geometries were updated
        """
        try:
            # Update Geodata of Pandapower Network
            for feature_id, new_geometry in geometry_map.items():
                if self.network_type in ['bus', 'junction']:
                    # If bus or junction, update x, y geometry
                    x = new_geometry.asPoint().x()
                    y = new_geometry.asPoint().y()

                    # Note: net.<table>.geo returns a Series copy, so it is read
                    # from but never written to. The authoritative write is the
                    # one into the table itself, further down.
                    df_network_type = getattr(self.net, self.network_type)
                    if feature_id in df_network_type.index:
                        try:
                            # Load geo data of existing dataframe and convert it into python dict
                            geo_data = json.loads(df_network_type.at[feature_id, 'geo'])

                            # Update coordinates in 'coordinates' key of the dictionary
                            geo_data['coordinates'] = [x, y]
                            updated_geo_str = json.dumps(geo_data)

                            # Update self.net.<table>['geo'] (root data source)
                            df_network_type.at[feature_id, 'geo'] = updated_geo_str

                            # Update self.df['geo'] column (for Attribute Table display)
                            if 'geo' in self.df.columns and feature_id in self.df.index:
                                self.df.at[feature_id, 'geo'] = updated_geo_str

                        except Exception as e:
                            raise ValueError(f"Error updating point geometry for ID {feature_id}: {str(e)}")

                elif self.network_type in ['line', 'pipe']:
                    # If line or pipe, update coord list
                    points = new_geometry.asPolyline()
                    coords = [(point.x(), point.y()) for point in points]

                    # See the note above: the table itself is the only thing
                    # written; net.<table>.geo is a copy.
                    df_network_type = getattr(self.net, self.network_type)
                    if feature_id in df_network_type.index:
                        try:
                            # Load geo data of existing dataframe and convert it into python dict
                            geo_data = json.loads(df_network_type.at[feature_id, 'geo'])

                            # Update coordinates in 'coordinates' key of the dictionary
                            geo_data['coordinates'] = coords
                            updated_geo_str = json.dumps(geo_data)

                            # Update self.net.<table>['geo'] (root data source)
                            df_network_type.at[feature_id, 'geo'] = updated_geo_str

                            # Update self.df['geo'] column (for Attribute Table display)
                            if 'geo' in self.df.columns and feature_id in self.df.index:
                                self.df.at[feature_id, 'geo'] = updated_geo_str

                        except Exception as e:
                            raise ValueError(f"Error updating line geometry for ID {feature_id}: {str(e)}")

            # The network diverges from the file until the edit buffer is
            # committed; the write itself happens in _on_layer_committed.
            self._mark_dirty()
            self.dataChanged.emit()
            return True

        except Exception as e:
            MessageManager.show_error(
                "Geometry Update Failed",
                f"Could not update geometries: {str(e)}"
            )
            return False


    def on_session_changed(self):
        """
        Handle a change made to the shared network by another layer of the same file.
        Since every provider of a file shares one net object, there is nothing to copy:
        the cached dataframe is simply rebuilt from the network that already changed
        underneath us, and the layer is repainted.
        """
        try:
            # Rebuild into a separate variable first, so a failure cannot leave
            # self.df in a half-updated state.
            new_df = self._create_updated_dataframe()

            if new_df is not None and not new_df.empty:
                self.df = new_df
                self._extent = None  # Geometry may have moved; recompute lazily
            else:
                # Keep existing data in case of failure
                MessageManager.show_warning(
                    "Data Update Failed",
                    f"Layer '{self.type_layer_name}' could not update with latest network changes. "
                    f"The layer may show outdated data. Try removing and re-adding the layer."
                )

        except Exception as e:
            print(f"❌ Provider {self.uri}: Update failed - {str(e)}")
            MessageManager.show_error(
                "Update Error",
                f"Failed to update data for layer '{self.type_layer_name}': {str(e)}. "
                f"The layer may show outdated or incorrect data."
            )


    def on_update_changed_network(self, network_data=None):
        """
        Backwards-compatible alias for on_session_changed().
        Deprecated: kept so any remaining caller of the old NetworkContainer listener
        API keeps working. The network_data argument is ignored, because all providers
        of a file now share one network object.
        Args:
            network_data: Ignored, accepted only for signature compatibility
        """
        self.on_session_changed()


    def _create_updated_dataframe(self):
        """
        Safely create new dataframe from updated network data without modifying existing state.
        Replicates merge_df() logic but returns new dataframe instead of modifying self.df.
        Used for on_update_changed_network()
        Returns:
            pandas.DataFrame or None: New dataframe with updated data, None if creation failed
        """
        try:
            # Execute existing merge_df logic in new variable
            df_network_type = getattr(self.net, self.network_type)
            df_res_network_type = getattr(self.net, f'res_{self.network_type}')

            # Check calculation results
            has_result_data = (df_res_network_type is not None and
                               not df_res_network_type.empty and len(df_res_network_type) > 0)

            if has_result_data:
                # vn_kv filtering (existing logic)
                if hasattr(self, 'vn_kv') and self.vn_kv is not None:
                    if self.network_type == 'bus':
                        filtered_indices = df_network_type[df_network_type['vn_kv'] == self.vn_kv].index
                        df_network_type = df_network_type.loc[filtered_indices]
                        # Only filter res for indices that exist
                        available_res_indices = df_res_network_type.index.intersection(filtered_indices)
                        df_res_network_type = df_res_network_type.loc[available_res_indices]

                # Sort and merge
                df_network_type.sort_index(inplace=True)
                df_res_network_type.sort_index(inplace=True)
                new_df = pd.merge(df_network_type, df_res_network_type,
                                  left_index=True, right_index=True, how='left', suffixes=('', '_res'))
            else:
                # No calculation results! Using new method
                new_df = df_network_type.copy()

                # Add empty result columns
                if df_res_network_type is not None:
                    res_columns = df_res_network_type.columns.tolist()
                    for col_name in res_columns:
                        new_df[col_name] = None

            # Add pp_type and pp_index columns
            new_df.insert(0, 'pp_type', self.network_type)
            new_df.insert(1, 'pp_index', new_df.index)
            return new_df

        except Exception as e:
            return None


    def changeAttributeValues(self, attr_map):
        """
        Change attribute values of existing features in the shared network.
        Includes validation for critical fields.
        Nothing is written to disk here: the file is written once when the user
        commits the layer's edit buffer (see _on_layer_committed).
        Args:
            attr_map: Dictionary mapping feature IDs to attribute changes
                      Format: {feature_id: {field_index: new_value, ...}, ...}
        Returns:
            bool: True if any attribute was updated
        """
        try:
            # Track which features were modified
            modified_features = set()
            # Track validation errors
            validation_errors = []

            # Update attributes
            for feature_id, changes in attr_map.items():
                for field_index, new_value in changes.items():
                    # 1. Get field name from index
                    field_name = self.fields()[field_index].name()

                    # 2. Check if field is editable
                    if not self.is_field_editable(field_name):
                        continue    # Skip read-only field

                    # 3. Validate critical fields BEFORE applying changes
                    validation_error = self._validate_field_value(field_name, new_value, feature_id)
                    if validation_error:
                        validation_errors.append(validation_error)
                        continue    # Skip this invalid change

                    # 4. Update self.df (cache for Attribute Table)
                    if feature_id in self.df.index:
                        self.df.at[feature_id, field_name] = new_value

                    # 5. Update self.net (root data source)
                    df_network_type = getattr(self.net, self.network_type)
                    if feature_id in df_network_type.index:
                        df_network_type.at[feature_id, field_name] = new_value

                    # Track modified feature
                    modified_features.add(feature_id)

            # Show validation errors to user
            if validation_errors:
                error_msg = "\n".join(validation_errors[:5])  # Show first 5 errors
                if len(validation_errors) > 5:
                    error_msg += f"\n... and {len(validation_errors) - 5} more errors"
                MessageManager.show_warning("Validation Error", f"Some changes were rejected:\n{error_msg}")

            # If no valid changes were made, return early
            if not modified_features:
                return False

            # The network diverges from the file until the edit buffer is
            # committed; the write itself happens in _on_layer_committed.
            self._mark_dirty()
            self.dataChanged.emit()
            return True

        except Exception as e:
            MessageManager.show_error(
                "Attribute Update Failed", f"Could not update changed attributes: {str(e)}")
            return False


    def _validate_field_value(self, field_name, new_value, feature_id):
        """
        Validate field value before applying changes.
        Checks for NULL in required fields, reference integrity, and physical constraints.
        Args:
            field_name: Name of the field being changed
            new_value: New value to be set
            feature_id: ID of the feature being modified
        Returns:
            str or None: Error message if validation fails, None if valid
        """
        # 1. Check for NULL in required fields (for line/pipe)
        if self.network_type in ['line', 'pipe']:
            required_fields = ['from_bus', 'to_bus', 'length_km'] if self.network_type == 'line' else ['from_junction', 'to_junction']

            if field_name in required_fields:
                # Check for None, NaN, or string "NULL"
                if new_value is None or pd.isna(new_value) or (isinstance(new_value, str) and new_value.upper() == 'NULL'):
                    return f"❌ {field_name} cannot be NULL (feature {feature_id})"

        # 2. Validate bus/junction references of line/pipe (referential integrity)
        if self.network_type == 'line' and field_name in ['from_bus', 'to_bus']:
            bus_df = getattr(self.net, 'bus')
            if new_value not in bus_df.index:
                available_buses = list(bus_df.index[:10])  # Show first 10 available buses
                return f"❌ Bus {new_value} does not exist (feature {feature_id}). Available: {available_buses}..."
        if self.network_type == 'pipe' and field_name in ['from_junction', 'to_junction']:
            junction_df = getattr(self.net, 'junction')
            if new_value not in junction_df.index:
                available_junctions = list(junction_df.index[:10])
                return f"❌ Junction {new_value} does not exist (feature {feature_id}). Available: {available_junctions}..."

        # 3. Physical constraints (prevent negative values)
        if self.network_type in ['line', 'pipe']:
            # Physical parameters that cannot be negative
            non_negative_fields = ['length_km', 'r_ohm_per_km', 'x_ohm_per_km', 'c_nf_per_km',
                                   'max_i_ka', 'diameter_m', 'g_us_per_km']

            if field_name in non_negative_fields:
                if new_value is not None and not pd.isna(new_value) and new_value < 0:
                    return f"❌ {field_name} cannot be negative (feature {feature_id}): {new_value}"

            # Parallel count must be at least 1
            if field_name == 'parallel':
                if new_value is not None and not pd.isna(new_value) and new_value < 1:
                    return f"❌ parallel must be at least 1 (feature {feature_id}): {new_value}"

        # std_type에 대한 더 철저한 validation이 필요할 경우 사용
        # if self.network_type == 'line' and field_name == 'std_type':
        #     if new_value is not None and not pd.isna(new_value) and new_value != '':
        #         if new_value not in self.net.std_types['line']:
        #             available = list(self.net.std_types['line'].keys())[:5]
        #             return f"❌ Invalid std_type '{new_value}'. Available types: {available}..."

        return None


    # currently not used: Cross-field validation for line features
    def _validate_line_feature(self, feature):
        """
        Validate line feature as a whole (cross-field validation).
        Checks constraints that require multiple fields (e.g., from_bus ≠ to_bus).
        Args:
            feature: QgsFeature to validate
        Returns:
            str or None: Error message if validation fails, None if valid
        """
        from_bus = feature.attribute('from_bus')
        to_bus = feature.attribute('to_bus')

        # Self-loop check: from_bus and to_bus must be different
        if from_bus is not None and to_bus is not None:
            if from_bus == to_bus:
                return f"❌ from_bus and to_bus cannot be the same ({from_bus})"

        # Optional: Voltage level warning (경고만 출력, validation error는 아님)
        if from_bus in self.net.bus.index and to_bus in self.net.bus.index:
            from_vn_kv = self.net.bus.loc[from_bus, 'vn_kv']
            to_vn_kv = self.net.bus.loc[to_bus, 'vn_kv']
            if from_vn_kv != to_vn_kv:
                return f"⚠️ Warning: Voltage level mismatch ({from_vn_kv} kV vs {to_vn_kv} kV) for line {from_bus}->{to_bus}"

        return None


    def is_field_editable(self, field_name):
        """
        Check if a field can be edited by the user.
        Args:
            field_name: Name of the field to check
        Returns:
            bool: True if the field is editable, False otherwise
        """
        # Meta columns are absolutely non-editable
        if field_name in ['pp_type', 'pp_index']:
            return False

        # Currently, geo can only be modified via changeGeometryValues()
        if field_name == 'geo':
            return False

        # vn_kv for lines is derived from from_bus.vn_kv, So, the line layer requires additional communication
        # to detect and update changes in the bus layer. Therefore, vn_kv is currently blocked.
        if field_name == 'vn_kv':
            return False

        # Only fields in the original network DataFrame can be modified
        df_network_type = getattr(self.net, self.network_type)
        if field_name in df_network_type.columns:
            return True

        # All other fields (res_* calculation results) - read-only
        return False


    def addFeatures(self, features, flags=None):
        """
        Add new features to the pandapower network.
        Validates feature data, creates corresponding pandapower elements,
        and notifies the shared NetworkSession.
        Note:
            This method follows the PyQGIS convention where C++ reference parameters
            (marked with SIP_INOUT) are returned as part of a tuple in Python.
        Args:
            features: List of QgsFeature objects to add
            flags: Optional flags (currently unused)
        Returns:
            tuple: (success, features) where:
                - success (bool): True if features were successfully added, False otherwise
                - features (list): The list of features with updated IDs and attributes
        """
        # Pre-validation - Check if file can be saved BEFORE processing
        if not self._validate_can_save():
            MessageManager.show_error(
                "Add Features Failed",
                "Cannot add features: File validation failed. The file may be inaccessible or locked."
            )
            return (False, [])      # QGIS will keep features in buffer (no commit)

        try:
            validation_errors = []
            features_to_add = []

            # Validate all features first
            for feature in features:
                # Validate each editable field
                for field in self.fields():
                    field_name = field.name()

                    # Skip non-editable fields
                    if not self.is_field_editable(field_name):
                        continue

                    value = feature.attribute(field_name)

                    # Reuse validation logic from changeAttributeValues
                    error = self._validate_field_value(field_name, value, "new_feature")
                    if error:
                        validation_errors.append(error)

                if not validation_errors:
                    features_to_add.append(feature)

            if validation_errors:
                error_msg = "\n".join(validation_errors[:5])
                if len(validation_errors) > 5:
                    error_msg += f"\n... and {len(validation_errors) - 5} more errors"
                MessageManager.show_error(
                    "Validation Error", f"Cannot add features due to validation errors:\n{error_msg}")
                return (False, [])

            # Add features to pandapower network
            added_indices = []
            added_features = []

            for feature in features_to_add:
                idx = self._add_feature_to_pandapower(feature)
                if idx is not None:
                    added_indices.append(idx)
                    # Update feature ID to match pandapower index
                    feature.setId(idx)
                    # Update read-only field attributes with actual values
                    # This ensures feature attributes match the actual data in self.net
                    self._update_feature_readonly_attributes(feature, idx)
                    added_features.append(feature)

            if not added_indices:
                MessageManager.show_error(
                    "Add Features Failed", "No features were added to the network. Features may have failed validation.")
                return (False, [])

            # Bring the newly added row from net.bus and net.res_bus
            df_network_type = getattr(self.net, self.network_type)
            df_res_network_type = getattr(self.net, f'res_{self.network_type}')

            new_rows = []

            # Append new feature to self.df
            for idx in added_indices:
                bus_row = df_network_type.loc[idx]

                # Merge if res exist
                if idx in df_res_network_type.index:
                    res_row = df_res_network_type.loc[idx]
                    # Concat two Series
                    new_row = pd.concat([bus_row, res_row])
                else:
                    new_row = bus_row
                    # Add res columns as None
                    for col in df_res_network_type.columns:
                        new_row[col] = None

                # Add pp_type, pp_index
                new_row_dict = new_row.to_dict()
                new_row_dict['pp_type'] = self.network_type
                new_row_dict['pp_index'] = idx

                # Append new rows to list
                new_rows.append(new_row_dict)

            # concat at once (O(n*m) → O(n+m))
            if new_rows:
                new_df = pd.DataFrame(new_rows, index=added_indices)
                self.df = pd.concat([self.df, new_df], ignore_index=False)

            # The network diverges from the file until the edit buffer is
            # committed; the write itself happens in _on_layer_committed.
            self._mark_dirty()
            if self.session:
                self.session.notify_changed(source=self)
            self.dataChanged.emit()
            return (True, features)

        except Exception as e:
            MessageManager.show_error("Add Features Failed", f"Failed to add features: {str(e)}")
            return (False, [])


    def _update_feature_readonly_attributes(self, feature, idx):
        """
        Update read-only field attributes with actual values from pandapower network.
        This is called after creating a new element in pandapower to ensure that:
            1. Feature attributes match the actual data in self.net
            2. Dialog DefaultValues (which are just hints) don't overwrite real data
        Args:
            feature: QgsFeature to update
            idx: Index of the element in pandapower network
        """
        try:
            # Get the actual row from pandapower network
            df = getattr(self.net, self.network_type)
            if idx not in df.index:
                return

            row = df.loc[idx]

            # Update read-only fields with actual values
            for field in self.fields():
                field_name = field.name()

                # Only update read-only fields
                if not self.is_field_editable(field_name):
                    # Get actual value from pandapower network
                    if field_name in row.index:
                        value = row[field_name]
                        field_idx = self.fields().indexOf(field_name)

                        # Convert value if needed
                        if pd.isna(value):
                            value = None

                        # Update feature attribute
                        feature.setAttribute(field_idx, value)

        except Exception as e:
            pass


    def _get_layer(self):
        """
        Get the QgsVectorLayer associated with this provider.
        Returns None if layer is not yet created.
        """
        try:
            layers = QgsProject.instance().mapLayersByName(self.type_layer_name)
            if layers:
                return layers[0]
            return None
        except Exception as e:
            return None


    def _mark_dirty(self):
        """
        Record that the in-memory network no longer matches the file on disk.
        Also makes sure the commit signal is connected, so the change actually
        reaches disk when the user saves the layer edits.
        """
        if self.session:
            self.session.mark_dirty()
        self._connect_commit_signal()


    def _connect_commit_signal(self):
        """
        Connect to this layer's afterCommitChanges signal, once.
        The layer does not exist yet while the provider is being constructed,
        so the connection is deferred until the first time it is needed.
        """
        if self._commit_connected:
            return

        layer = self._get_layer()
        if layer is None:
            return  # Layer not registered yet; try again on the next change

        try:
            layer.afterCommitChanges.connect(self._on_layer_committed)
            self._commit_connected = True
        except Exception as error:
            print('Could not connect commit signal: {}'.format(error))


    def _on_layer_committed(self):
        """
        Write the network to disk after the user commits the layer edit buffer.
        This is the single point at which edits reach the file. If several
        layers of one network commit in the same action, only the first write
        does any work: it clears the session's dirty flag, so the rest see a
        clean session and skip.
        """
        session = self.session
        if session is None or not session.dirty:
            return  # Nothing to write, or another layer already wrote it

        # Never silently overwrite a file that changed underneath us (plan 5.3).
        if session.file_changed_externally():
            if not self._confirm_overwrite_external_change():
                return

        success, message, backup_path = session.write()

        if success:
            MessageManager.show_success("Network Saved", message)
            if backup_path:
                MessageManager.show_info(
                    "Backup Created", f"Backup file: {backup_path}")
            # A committed edit can move features between voltage-level layers,
            # so refresh siblings once per commit rather than once per feature.
            session.notify_changed(source=self)
        else:
            MessageManager.show_error(
                "Save Failed",
                f"{message}\n\nThe changes are still in memory. "
                f"Fix the problem and save the layer again."
            )


    def _confirm_overwrite_external_change(self):
        """
        Ask whether to overwrite a file that changed since it was opened.
        Returns:
            bool: True if the user chose to overwrite
        """
        try:
            from qgis.PyQt.QtWidgets import QMessageBox

            answer = QMessageBox.question(
                None,
                "File changed on disk",
                f"{self.session.path}\n\n"
                f"has changed since it was opened. Overwrite it with the "
                f"in-memory network?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return answer == QMessageBox.Yes
        except Exception:
            # Without a GUI, refuse rather than clobber the file.
            return False


    def _setup_attribute_form(self):
        """
        Configure the attribute form for Add Feature functionality.
        Sets up field widgets, constraints, default values, and read-only status.

        Key Feature: Displays actual values for read-only fields in Add Feature dialog
        """
        # Check if already setup
        if hasattr(self, '_form_setup_done') and self._form_setup_done:
            return

        try:
            from qgis.core import QgsEditFormConfig, QgsDefaultValue, QgsFieldConstraints, QgsEditorWidgetSetup, QgsAttributeEditorField

            # Try to get layer from QgsProject
            layer = self._get_layer()
            if layer is None:
                return      # Layer not yet available, will retry later
            
            # Set flag to avoid recursion
            self._form_setup_done = True

            config = layer.editFormConfig()
            field_names = [f.name() for f in self.fields_list]

            # Set Form Layout
            config.setLayout(QgsEditFormConfig.TabLayout)
            root = config.invisibleRootContainer()
            root.clear()  # Clear existing fields
            # Get result DataFrame
            df_res = getattr(self.net, f'res_{self.network_type}', None)

            # Configure each field
            for field_name in field_names:
                field_idx = self.fields_list.indexOf(field_name)
                if field_idx < 0:
                    continue

                # Filter fields to hide (pp_index, result columns)
                if field_name == 'pp_index':
                    continue
                if df_res is not None and field_name in df_res.columns:
                    continue

                # Add fields to Form to display
                element = QgsAttributeEditorField(field_name, field_idx, root)
                root.addChildElement(element)

                # Configure read-only fields with default values
                if not self.is_field_editable(field_name):
                    # Set as read-only
                    config.setReadOnly(field_idx, True)

                    # Get default value for this field
                    default_value = self._get_default_value_for_form(field_name)
                    if default_value is not None:
                        # Create Expression for QgsDefaultValue
                        if isinstance(default_value, (int, float)):
                            # Numeric values don't need quotes
                            default_expr = str(default_value)
                        else:
                            # String values need single quotes in expression
                            default_expr = f"'{default_value}'"

                        # Set default value definition
                        layer.setDefaultValueDefinition(
                            field_idx, QgsDefaultValue(default_expr, applyOnUpdate=False))

                # Configure editable fields (widgets & constraints)
                else:
                    # Configure widget type
                    if field_name == 'in_service':
                        layer.setEditorWidgetSetup(field_idx, QgsEditorWidgetSetup('CheckBox', {}))

                    elif field_name in ['from_bus', 'to_bus', 'from_junction', 'to_junction']:
                        layer.setEditorWidgetSetup(field_idx, QgsEditorWidgetSetup('TextEdit', {}))

                    elif field_name == 'type' and self.network_type == 'bus':
                        # Type field → ValueMap (dropdown)
                        widget_config = {
                            'map': {
                                'b - busbar': 'b',
                                'n - node': 'n',
                                'm - muff': 'm'
                            }
                        }
                        layer.setEditorWidgetSetup(field_idx, QgsEditorWidgetSetup('ValueMap', widget_config))

                    else:
                        # Default: TextEdit for most fields
                        layer.setEditorWidgetSetup(field_idx, QgsEditorWidgetSetup('TextEdit', {}))

                    # Configure constraints
                    # Define required fields for this network type
                    required_map = {
                        'bus': ['name', 'vn_kv'],
                        'line': ['from_bus', 'to_bus', 'length_km', 'std_type'],
                        # junction and pipe excluded as per requirements
                    }
                    required_fields = required_map.get(self.network_type, [])

                    # Set NotNull constraint for required fields
                    if field_name in required_fields:
                        field_constraints = layer.fields()[field_idx].constraints()
                        field_constraints.setConstraint(QgsFieldConstraints.ConstraintNotNull)
                        field_constraints.setConstraintStrength(
                            QgsFieldConstraints.ConstraintNotNull,
                            QgsFieldConstraints.ConstraintStrengthHard
                        )

                    # Expression constraints for physical parameters
                    if field_name in ['length_km', 'r_ohm_per_km', 'x_ohm_per_km', 'c_nf_per_km',
                                      'max_i_ka', 'diameter_m', 'g_us_per_km']:
                        field_constraints = layer.fields()[field_idx].constraints()
                        field_constraints.setConstraintExpression(
                            f'"{field_name}" > 0',
                            f"{field_name} must be positive"
                        )

                    # Parallel count must be at least 1
                    if field_name == 'parallel':
                        field_constraints = layer.fields()[field_idx].constraints()
                        field_constraints.setConstraintExpression(
                            f'"{field_name}" >= 1',
                            "parallel must be at least 1"
                        )

            # Apply configuration
            layer.setEditFormConfig(config)

            # 3. Set Table View as default (not Form View)
            from qgis.core import QgsAttributeTableConfig
            table_config = layer.attributeTableConfig()
            table_config.setActionWidgetStyle(QgsAttributeTableConfig.ButtonList)
            table_config.update(layer.fields())
            layer.setAttributeTableConfig(table_config)

        except Exception as e:
            self._form_setup_done = False
            pass


    def _get_default_value_for_form(self, field_name):
        """
        Get default value to display for read-only fields in the Add Feature form.
        Returns actual values that will be used when creating the feature.
        Args:
            field_name: Name of the field
        Returns:
            Default value to display in the form dialog (string, int, float, or None)
        """
        if field_name == 'pp_type':
            return self.network_type

        elif field_name == 'pp_index':
            # Show next available index (recalculated each time dialog opens)
            next_idx = self._get_next_index()
            return int(next_idx)

        elif field_name == 'vn_kv' and self.network_type in ['bus', 'line']:
            return float(self.vn_kv)

        elif field_name == 'pn_bar' and self.network_type in ['junction', 'pipe']:
            return float(self.pn_bar)

        elif field_name == 'geo':
            # Geometry is auto-generated from click position
            return "(auto-generated)"

        # Other read-only fields - res columns
        return "(needs runpp)"


    def _get_next_index(self):
        """
        Calculate the next available index for a new feature in pandapower network.
        Note: Not actual pp index, only to display user hint
        Returns:
            int: Next available index (max + 1, or 0 if empty)
        """
        df = getattr(self.net, self.network_type)
        if df.empty:
            return 0
        return int(df.index.max() + 1)


    def _add_empty_res_row(self, idx):
        """
        Add empty result row for newly created element.
        Creates a row with NaN values in the corresponding res_* DataFrame
        so that the element can be safely merged even before running power flow.
        Args:
            idx: Index of the newly created element in pandapower network
        Returns:
            bool: True if row was successfully added, False otherwise
        """
        try:
            res_table_name = f'res_{self.network_type}'

            # Check if res table exists
            if not hasattr(self.net, res_table_name):
                return False

            res_df = getattr(self.net, res_table_name)

            # Check if res_df is None (shouldn't happen with pandapower, but defensive)
            if res_df is None:
                return False

            # Check if res_df has columns (structure exists)
            if len(res_df.columns) == 0:
                return False

            # Check if row already exists (safety check)
            if idx in res_df.index:
                return True

            # Create empty row with all columns as NaN
            # dtype=float ensures all values are NaN (float type)
            new_row = pd.Series(index=res_df.columns, name=idx, dtype=float)

            # Add row to res dataframe using concat
            # ignore_index=False preserves the index (idx)
            updated_res = pd.concat([res_df, new_row.to_frame().T], ignore_index=False)

            # Update the network's res dataframe
            setattr(self.net, res_table_name, updated_res)
            return True

        except Exception as e:
            return False


    def _add_feature_to_pandapower(self, feature):
        """
        Add a single feature to the pandapower network.
        Extracts attributes from QgsFeature and creates corresponding pandapower element.
        Args:
            feature: QgsFeature to add
        Returns:
            int or None: Index of created element in pandapower network, or None if failed
        """
        try:
            # Extract geometry
            geometry = feature.geometry()

            # Prepare attributes dictionary (only editable fields)
            attributes = {}
            for field in self.fields():
                field_name = field.name()
                if self.is_field_editable(field_name):
                    value = feature.attribute(field_name)

                    # Convert QVariant to Python value
                    if hasattr(value, 'isNull'):  # If QVariant object
                        if value.isNull():
                            value = None
                        else:
                            value = value.value()  # Convert to Python native type
                    # '' or 'NULL' -> None (QVariant -> python type)
                    if isinstance(value, str):
                        value = value.strip()
                        if value == '' or value.upper() == 'NULL':
                            value = None

                    # Skip None/NULL values - let pandapower use defaults
                    if value is not None and not pd.isna(value):
                        # Check actual dtype of DataFrame
                        df_network_type = getattr(self.net, self.network_type)
                        # Check if field exists in DataFrame and get its dtype
                        if field_name in df_network_type.columns:
                            dtype = df_network_type[field_name].dtype
                            try:
                                # Check pandas dtype
                                if pd.api.types.is_float_dtype(dtype):
                                    value = float(value)    # Convert to float (e.g., '123' → 123.0)
                                elif pd.api.types.is_integer_dtype(dtype):
                                    value = int(value)      # Convert to int (e.g., '123' → 123)
                                elif pd.api.types.is_bool_dtype(dtype):
                                    if isinstance(value, str):  # Convert to bool (e.g., 'True' → True)
                                        value = value.lower() in ['true', '1', 'yes']
                                    else:
                                        value = bool(value)
                            except (ValueError, TypeError) as e:
                                continue
                        attributes[field_name] = value

            # Create element based on network type
            if self.network_type == 'bus':  # Required: name, vn_kv
                name = attributes.pop('name', f'Bus_{self._get_next_index()}')
                type_val = attributes.pop('type', 'b')
                in_service = attributes.pop('in_service', True)
                # In attributes[] remains now kwargs

                # Create bus with required parameters
                idx = pp.create_bus(
                    self.net,
                    name=name,
                    vn_kv=self.vn_kv,  # Use layer's voltage level
                    type=type_val,
                    in_service=in_service,
                    **attributes
                )

                # Add empty res row immediately
                self._add_empty_res_row(idx)

                # Add geometry to geo column
                if not geometry.isNull():
                    point = geometry.asPoint()
                    geo_json = json.dumps({'coordinates': [point.x(), point.y()], 'type': 'Point'})
                    self.net.bus.at[idx, 'geo'] = geo_json
                return idx

            elif self.network_type == 'line':
                # Required: from_bus, to_bus, length_km / Optional: std_type (if NULL, must provide r, x, c parameters)
                from_bus = attributes.pop('from_bus', None)
                to_bus = attributes.pop('to_bus', None)
                length_km = attributes.pop('length_km', None)
                std_type = attributes.pop('std_type', None)

                if from_bus is None or to_bus is None or length_km is None:
                    self.pushError("Missing required fields for line: from_bus, to_bus, length_km")
                    return None

                name = attributes.pop('name', f'Line_{self._get_next_index()}')
                in_service = attributes.pop('in_service', True)
                parallel = attributes.pop('parallel', 1)

                # std_type NULL → use create_line_from_parameters() instead
                if std_type is None or std_type == '' or std_type == 'NULL':
                    required_params = ['r_ohm_per_km', 'x_ohm_per_km', 'c_nf_per_km']
                    missing = [p for p in required_params if p not in attributes or attributes[p] is None]

                    if missing:
                        self.pushError(
                            f"std_type is NULL, but required parameters are missing: {missing}\n"
                            f"Either provide std_type or all of: r_ohm_per_km, x_ohm_per_km, c_nf_per_km"
                        )
                        return None

                    idx = pp.create_line_from_parameters(
                        self.net,
                        from_bus=int(from_bus),
                        to_bus=int(to_bus),
                        length_km=float(length_km),
                        name=name,
                        in_service=in_service,
                        parallel=parallel,
                        **attributes  # r_ohm_per_km, x_ohm_per_km, c_nf_per_km, etc.
                    )
                else:
                    # std_type not null → create_line()
                    idx = pp.create_line(
                        self.net,
                        from_bus=int(from_bus),
                        to_bus=int(to_bus),
                        length_km=float(length_km),
                        std_type=std_type,
                        name=name,
                        in_service=in_service,
                        parallel=parallel,
                        **attributes
                    )

                # Add empty res row immediately
                self._add_empty_res_row(idx)

                # Add geometry to geo column
                if not geometry.isNull():
                    line_geom = geometry.asPolyline()
                    coords = [[point.x(), point.y()] for point in line_geom]
                    geo_json = json.dumps({
                        'coordinates': coords,
                        'type': 'LineString'
                    })
                    self.net.line.at[idx, 'geo'] = geo_json

                # Use vn_kv of from_bus
                if from_bus in self.net.bus.index:
                    from_vn_kv = self.net.bus.loc[from_bus, 'vn_kv']
                    self.net.line.at[idx, 'vn_kv'] = from_vn_kv
                return idx

            else:
                self.pushError(f"Unsupported network type for addFeatures: {self.network_type}")
                return None

        except Exception as e:
            self.pushError(f"Error adding feature to pandapower: {str(e)}")
            return None


    def _validate_can_save(self):
        """
        🛡️ PRE-VALIDATION: Validate that file can be saved before processing features.
        Checks file existence, write permissions, and file lock status.
        Shows user-friendly error messages if validation fails.
        Returns:
            bool: True if safe to proceed with save, False if save will fail
        """
        json_path = self.uri_parts.get('path', '')

        # 🛡️ Check 1: File exists
        if not json_path or not os.path.exists(json_path):
            MessageManager.show_error(
                "Cannot Save",
                f"File not found: {json_path}\n"
                f"The file may have been moved or deleted."
            )
            return False

        # 🛡️ Check 2: Write permission
        if not os.access(json_path, os.W_OK):
            MessageManager.show_error(
                "Cannot Save",
                f"No write permission: {json_path}\n"
                f"Check file properties (read-only?) or contact administrator."
            )
            return False

        # 🛡️ Check 3: File not locked (by other program)
        try:
            # Try to open in read-write mode (doesn't actually modify)
            with open(json_path, 'r+') as f:
                pass
        except PermissionError:
            MessageManager.show_error(
                "Cannot Save",
                f"File is locked: {json_path}\n"
                f"Close any programs using this file (Excel, text editor, etc.)"
            )
            return False

        except Exception as e:
            # Unexpected error during file check
            MessageManager.show_error(
                "Cannot Save",
                f"Cannot access file: {json_path}\n"
                f"Error: {str(e)}"
            )
            return False

        return True

    # =========================================================================

    def deleteFeatures(self, fids):
        """
        Delete features from the pandapower network.
        This method is called by QGIS when user deletes features.
        - For buses: Shows connected elements and asks for confirmation before cascade delete.
        - For lines: Deletes safely using pandapower function.
        Args:
            fids: QgsFeatureIds (set of feature IDs) to delete
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        # Pre-validation: Check if file can be saved
        if not self._validate_can_save():
            return False

        try:
            # Route to appropriate deletion method based on network type
            if self.network_type == 'bus':  # Bus deletion: Check connections and ask for user confirmation
                return self._delete_buses_with_confirmation(fids)
            elif self.network_type == 'line':   # Line deletion: Direct deletion (safe, no dependencies)
                return self._delete_lines(fids)
            elif self.network_type in ['junction', 'pipe']:
                MessageManager.show_info(
                    "Not Implemented", f"Delete feature is not yet implemented for {self.network_type}.")
                return False
            else:
                self.pushError(f"Unsupported network type for deleteFeatures: {self.network_type}")
                return False

        except Exception as e:
            MessageManager.show_error("Delete Features Failed", f"Failed to delete features: {str(e)}")
            return False


    def _get_bus_connected_elements_info(self, bus_ids):
        """
        Get information about all elements connected to given buses.
        Uses pp.element_bus_tuples() for dynamic discovery of element types.
        Args:
            bus_ids: List or set of bus indices to check
        Returns:
            dict: {
                'in_qgis_layers': {
                    'line': [10, 11, 12],  # Elements visible in QGIS layers
                },
                'in_network_only': {
                    'load': [5, 8],        # Elements only in JSON (not visible in QGIS)
                    'trafo': [2],
                    'gen': [3]
                },
                'total_count': 7           # Total number of connected elements
            }
        """
        try:
            # pandapower's element_bus_tuples for dynamic element discovery
            element_tuples = pp.element_bus_tuples(
                bus_elements=True,  # load, gen, sgen, etc.
                branch_elements=True  # line, trafo, etc.
            )

            in_qgis = {}  # Elements visible in QGIS layers
            in_json = {}  # Elements only in JSON file

            # QGIS layer types currently managed by the plugin
            qgis_layer_types = {'line'}     # Currently only 'line' is shown as a layer besides 'bus'

            # Convert bus_ids to set for faster lookup
            bus_id_set = set(bus_ids)

            # Scan all element types for connections
            for element_type, bus_column in element_tuples:
                # Check if this element table exists in the network
                if not hasattr(self.net, element_type):
                    continue

                element_df = getattr(self.net, element_type)
                if element_df is None or element_df.empty:
                    continue

                # Check if the bus reference column exists
                if bus_column not in element_df.columns:
                    continue

                # Find elements that reference any of the buses to be deleted
                connected = element_df[element_df[bus_column].isin(bus_id_set)]

                if not connected.empty:
                    indices = connected.index.tolist()

                    # Classify: QGIS layer vs JSON-only
                    if element_type in qgis_layer_types:
                        if element_type not in in_qgis:
                            in_qgis[element_type] = []
                        in_qgis[element_type].extend(indices)
                    else:
                        if element_type not in in_json:
                            in_json[element_type] = []
                        in_json[element_type].extend(indices)

            # Remove duplicates (in case an element references the same bus multiple times)
            for key in in_qgis:
                in_qgis[key] = sorted(list(set(in_qgis[key])))
            for key in in_json:
                in_json[key] = sorted(list(set(in_json[key])))

            # Calculate total count
            total = sum(len(v) for v in in_qgis.values()) + sum(len(v) for v in in_json.values())

            return {
                'in_qgis_layers': in_qgis,
                'in_network_only': in_json,
                'total_count': total
            }

        except Exception as e:
            # Return empty result on error
            return {
                'in_qgis_layers': {},
                'in_network_only': {},
                'total_count': 0
            }


    def _delete_buses_with_confirmation(self, fids):
        """
        Delete buses with user confirmation after checking connected elements.
        Implements All or Nothing principle - either all buses are deleted or none.
        Args:
            fids: QgsFeatureIds (set of feature IDs) to delete
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            # Convert to list for processing
            bus_ids = list(fids)

            # Validation: Check which buses actually exist
            valid_buses = [bid for bid in bus_ids if bid in self.net.bus.index]
            invalid_buses = [bid for bid in bus_ids if bid not in self.net.bus.index]

            if invalid_buses:
                MessageManager.show_warning(
                    "Some Features Not deleted",
                    f"Could not find {len(invalid_buses)} bus(es) (IDs: {invalid_buses[:5]}) in network.\n"
                    f"Continuing with {len(valid_buses)} valid bus(es)."
                )
            if not valid_buses:
                return False

            # Get information about connected elements of busses
            connected_info = self._get_bus_connected_elements_info(valid_buses)

            # Show confirmation dialog to user (user cancel)
            if not self._show_delete_confirmation_dialog(valid_buses, connected_info):
                return False

            # Use pandapower's drop_buses function (handles connected elements automatically)
            pp.drop_buses(self.net, valid_buses, drop_elements=True)

            # Update self.df - Remove deleted buses from self.df
            self.df.drop(valid_buses, inplace=True, errors='ignore')

            # Save to JSON file and perform post-processing
            return self._save_deletions(valid_buses, 'bus')

        except Exception as e:
            return False


    def _delete_lines(self, fids):
        """
        Delete lines safely using pandapower function.
        Lines can be deleted without confirmation dialog since they typically don't have
        dependent elements (simpler than bus deletion).
        Args:
            fids: QgsFeatureIds (set of feature IDs) to delete
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            # Convert to list for processing
            line_ids = list(fids)

            # Validation: Check which lines actually exist
            valid_lines = [lid for lid in line_ids if lid in self.net.line.index]
            invalid_lines = [lid for lid in line_ids if lid not in self.net.line.index]

            if invalid_lines:
                MessageManager.show_warning(
                    "Some Features Not deleted",
                    f"Could not find {len(invalid_lines)} line(es) (IDs: {invalid_lines[:5]}) in network.\n"
                    f"Continuing with {len(valid_lines)} valid bus(es)."
                )
            if not valid_lines:
                return False

            # Use pandapower's drop_lines function
            # This also removes geodata and connected switches automatically
            pp.drop_lines(self.net, valid_lines)

            # Update self.df
            self.df.drop(valid_lines, inplace=True, errors='ignore')

            # Save to JSON file and perform post-processing
            return self._save_deletions(valid_lines, 'line')

        except Exception as e:
            return False


    def _notify_affected_layers(self):
        """
        Notify sibling layers of the same network file that the data changed.
        This handles cascade deletions where multiple network_types are affected
        (e.g., bus deletion causes line deletion).
        The session knows every provider of this file directly, so there is no need
        to scan the whole project. Note that all network_types are notified, not just
        those of the same voltage level: a bus deletion cascades into lines, which may
        sit in a different layer.
        """
        if not self.session:
            return
        try:
            for provider in self.session.providers():
                if provider is self:
                    continue    # Skip self (notified separately in _save_deletions())
                provider.dataChanged.emit()

            # Repaint the affected layers in the project.
            for layer in QgsProject.instance().mapLayers().values():
                provider = layer.dataProvider()
                if getattr(provider, 'session', None) is self.session and provider is not self:
                    layer.triggerRepaint()

        except Exception as e:
            print(f"Failed to notify affected layers: {str(e)}")


    def _save_deletions(self, deleted_ids, element_type):
        """
        Record deletions and refresh the affected layers.
        Nothing is written to disk here: the file is written once when the user
        commits the layer's edit buffer (see _on_layer_committed).
        Args:
            deleted_ids: List of deleted element indices
            element_type: Type of element ('bus' or 'line')
        Returns:
            bool: True when the deletion was recorded
        """
        try:
            self._mark_dirty()

            if self.session:
                self.session.notify_changed(source=self)

            # Notify self first, then the sibling layers: deleting a bus
            # cascades into the lines attached to it, which live in another
            # layer.
            self.dataChanged.emit()
            if element_type == 'bus':
                self._notify_affected_layers()

            return True

        except Exception as e:
            MessageManager.show_error(
                "Delete Failed", f"Failed to record deletion: {str(e)}")
            return False


    def _show_delete_confirmation_dialog(self, bus_ids, connected_info):
        """
        Show detailed confirmation dialog for bus deletion with connected elements' information.
        This is the second dialog (after QGIS default deletion confirmation).
        Args:
            bus_ids: List of bus indices to delete
            connected_info: Dict from _get_bus_connected_elements_info()
        Returns:
            bool: True if user confirmed deletion, False if cancelled
        """
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
            from qgis.PyQt.QtCore import Qt

            # Get bus names for display
            bus_names = []
            for bid in bus_ids:
                if bid in self.net.bus.index:
                    name = self.net.bus.loc[bid, 'name'] if 'name' in self.net.bus.columns else f"Bus {bid}"
                    bus_names.append(f"{name} (ID: {bid})")

            # Create message box
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Confirm Cascade Delete")

            # Main text: What buses are being deleted
            if len(bus_ids) == 1:
                main_text = f"You are about to delete this bus:\n• {bus_names[0]}"
            else:
                main_text = f"You are about to delete {len(bus_ids)} buses:\n"
                for name in bus_names[:5]:  # Show max 5
                    main_text += f"• {name}\n"
                if len(bus_names) > 5:
                    main_text += f"• ... and {len(bus_names) - 5} more\n"

            msg.setText(main_text)

            # Detailed information: Connected elements
            detail_text = ""

            if connected_info['total_count'] == 0:
                # Safe case: No connected elements
                detail_text += "✅ No connected elements found.\n"
                detail_text += "   Safe to delete.\n\n"
            else:
                # Warning case: Has connected elements
                detail_text += f"⚠️ WARNING: {connected_info['total_count']} connected element(s) will also be deleted!\n\n"

                # Show QGIS layer elements (visible to user)
                if connected_info['in_qgis_layers']:
                    detail_text += "📍 Elements visible in QGIS Layers:\n"
                    for elem_type, indices in connected_info['in_qgis_layers'].items():
                        if len(indices) <= 10:
                            detail_text += f"  • {len(indices)} {elem_type}(s): {indices}\n\n"
                        else:
                            detail_text += f"  • {len(indices)} {elem_type}(s): {indices[:10]} ... and {len(indices) - 10} more\n\n"

                # Show JSON-only elements (not visible in QGIS)
                if connected_info['in_network_only']:
                    detail_text += "📄 Elements in JSON File Only (not visible in layer):\n"
                    for elem_type, indices in connected_info['in_network_only'].items():
                        if len(indices) <= 10:
                            detail_text += f"  • {len(indices)} {elem_type}(s): {indices}\n\n"
                        else:
                            detail_text += f"  • {len(indices)} {elem_type}(s): {indices[:10]} ... and {len(indices) - 10} more\n\n"

                # Total summary
                total_elements = len(bus_ids) + connected_info['total_count']
                detail_text += f"💡 Total: {total_elements} elements will be deleted ({len(bus_ids)} bus(es) + {connected_info['total_count']} connected)\n\n"

            # Warning about undo
            detail_text += "⚠️ This action cannot be undone!\n      (A backup file will be created automatically)\n"

            msg.setInformativeText(detail_text)

            # Configure buttons
            msg.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
            msg.setDefaultButton(QMessageBox.Cancel)  # Default to Cancel for safety

            yes_button = msg.button(QMessageBox.Yes)
            if connected_info['total_count'] == 0:
                yes_button.setText("Delete Bus")
            else:
                total_elements = len(bus_ids) + connected_info['total_count']
                yes_button.setText(f"Delete All ({total_elements})")

            cancel_button = msg.button(QMessageBox.Cancel)
            cancel_button.setText("Cancel")

            # Show dialog and get result
            result = msg.exec_()

            if result == QMessageBox.Yes:
                return True
            else:
                return False

        except Exception as e:
            return False    # On error, default to cancel (safe choice)

    # =========================================================================

    def capabilities(self) -> QgsVectorDataProvider.Capabilities:
        """
        Return the capabilities supported by this data provider.
        Capabilities depend on the table: attribute-only tables have no geometry
        to change and no spatial index, and adding or deleting rows is only
        implemented for bus and line. Advertising more than is implemented would
        let QGIS offer edits that are then rejected.
        Returns:
            QgsVectorDataProvider.Capabilities
        """
        caps = (
            QgsVectorDataProvider.SelectAtId |
            QgsVectorDataProvider.ChangeAttributeValues
        )

        if self.has_geometry():
            caps |= (
                QgsVectorDataProvider.CreateSpatialIndex |
                QgsVectorDataProvider.ChangeGeometries
            )

        # addFeatures()/deleteFeatures() are implemented for bus and line only.
        if self.network_type in ('bus', 'line'):
            caps |= (
                QgsVectorDataProvider.AddFeatures |
                QgsVectorDataProvider.DeleteFeatures
            )

        return caps


    def crs(self) -> QgsCoordinateReferenceSystem:
        """
        Get the coordinate reference system for this provider.
        Returns:
            QgsCoordinateReferenceSystem: Provider's coordinate reference system
        """
        return self.sourceCrs()


    def sourceCrs(self) -> QgsCoordinateReferenceSystem:
        """
        Get the source coordinate reference system from current_crs setting.
        Returns:
            QgsCoordinateReferenceSystem: Source CRS based on EPSG code
        Raises:
            ValueError: If the CRS ID is not valid
        """
        crs = QgsCoordinateReferenceSystem.fromEpsgId(int(self.current_crs))
        if not crs.isValid():
            raise ValueError(f"CRS ID {self.current_crs} is not valid.")
        return crs


    @classmethod
    def name(cls) -> str:
        """
        Get the provider name identifier.
        Returns:
            str: Provider name
        """
        return "PandapowerProvider"


    @classmethod
    def description(cls) -> str:
        """
        Get the provider description text.
        Returns:
            str: Provider description
        """
        return "PandapowerProvider"


    def extent(self) -> QgsRectangle:
        """
        Calculates the extent of the band and returns a QgsRectangle.
        Returns:
            QgsRectangle: Bounding rectangle containing all features, empty if no valid coordinates
        """
        # An attribute-only table has no spatial extent at all.
        if not self.has_geometry():
            return QgsRectangle()

        if not self._extent:
            try:
                min_x = float('inf')
                max_x = float('-inf')
                min_y = float('inf')
                max_y = float('-inf')

                df_geodata = getattr(self.net, self.network_type).geo
                if df_geodata is None or df_geodata.empty:
                    return QgsRectangle()

                # Point geometry (bus/junction)
                if self.network_type in ['bus', 'junction']:
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
                                    return QgsRectangle()   # Return empty rectangle on incorrect coordinate format
                        except Exception as e:
                            continue    # Skip invalid geometry, continue with others

                # Line geometry (line/pipe)
                elif self.network_type in ['line', 'pipe']:
                    # Iterate through the coordinates of each line
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
                                            return QgsRectangle()   # Return empty rectangle on incorrect coordinate format
                        except Exception as e:
                            continue  # Skip invalid geometry, continue with others

                # Check if the valid range has been calculated
                if min_x == float('inf') or max_x == float('-inf'):
                    return QgsRectangle()

                return QgsRectangle(min_x, min_y, max_x, max_y)

            except Exception as e:
                self.pushError(f"Error calculating extent: {str(e)}")
                return QgsRectangle()


    def featureCount(self):
        """
        Get the total number of features in the dataframe.
        Returns:
            int: Number of features, 0 if error occurred
        """
        try:
            if self.df is not None:
                return len(self.df)
            return 0
        except Exception as e:
            self.pushError(f"Failed to count features: {str(e)}")
            return 0


    def featureSource(self):
        """
        Create and return a feature source for this provider.
        Returns:
            PandapowerFeatureSource: Feature source wrapping this provider
        """
        return pandapower_feature_source.PandapowerFeatureSource(self)


    def isValid(self):
        """
        Check if the data provider is in a valid state.
        Returns:
            bool: True if provider is valid and ready for use
        """
        return self._is_valid


    def storageType(self):
        """
        Get a description of the permanent storage type for this layer.
        Returns:
            str: Human-readable description of storage format
        """
        return f"{self.network_type} layer is Pandapower Network in json format"


    def wkbType(self):
        """
        Get the Well-Known Binary geometry type for features in this provider.
        Returns:
            QgsWkbTypes: Point for bus/junction, LineString for line/pipe,
                NoGeometry for attribute-only tables such as trafo or load
        """
        if self.network_type in ('bus', 'junction'):
            return QgsWkbTypes.Point
        elif self.network_type in ('line', 'pipe'):
            return QgsWkbTypes.LineString
        # Attribute-only table: opens as a plain table, like a non-spatial
        # table in a database (plan section 3.6).
        return QgsWkbTypes.NoGeometry


    def has_geometry(self):
        """
        Whether the table this provider exposes carries geometry.
        Returns:
            bool: True for bus/junction/line/pipe, False for attribute-only tables
        """
        return has_geometry(self.network_type)


    def unload(self):
        """
        Clean up resources of THIS provider instance when it is destroyed.
        Removes the network update listener and waits for background save operations
        to complete.
        Note: this must not touch the provider registry. The registry entry is owned by
        the plugin (registered in __init__.classFactory) and shared by every pandapower
        layer in the project. Deregistering it here would invalidate all other open
        pandapower layers as soon as a single layer is closed.
        """
        # Leave the shared session. The network is dropped from memory once the
        # last layer using this file has been closed.
        if self.session:
            self.session.remove_provider(self)
            self.session.release()
            self.session = None
