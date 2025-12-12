from qgis.core import QgsVectorDataProvider, QgsVectorLayer, QgsFeature, QgsField, QgsFields, \
    QgsGeometry, QgsPointXY, QgsLineString, QgsWkbTypes, QgsProject, QgsCoordinateReferenceSystem, \
    QgsFeatureRequest, QgsFeatureIterator, QgsFeatureSource, QgsAbstractFeatureSource, QgsFeatureSink, \
    QgsDataProvider, QgsProviderRegistry, QgsRectangle
from qgis.PyQt.QtCore import QMetaType
import json
import pandas as pd
import pandapower as pp
import pandapipes as ppi
import os
from . import pandapower_feature_iterator, pandapower_feature_source
from .network_container import NetworkContainer
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
        Initialize the pandapower data provider with network data from NetworkContainer.
        Sets up network type, coordinate system, and registers as a network update listener.
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
        self._provider_options = providerOptions
        self._flags = flags

        # Initialize all attributes with default values (prevents AttributeError while reopen qgis project file)
        self._is_valid = False
        self.net = None
        self.network_type = self.uri_parts.get('network_type', None)
        self.type_layer_name = None
        self.current_crs = None
        self.crs = None
        self.fields_list = None
        self.df = None
        self._extent = None
        self.vn_kv = None
        self.pn_bar = None
        self._save_in_progress = False
        self._save_thread = None
        self.network_data = None

        # Bring network data from container
        network_data = NetworkContainer.get_network(uri)

        # If container is empty (e.g., after project reload), load from file
        if network_data is None:
            network_data, error = self._load_network_from_file()
            if network_data is None:
                file_path = self.uri_parts.get('path', 'unknown')
                MessageManager.show_error(
                    "Network Load Failed",
                    error or "Unknown error occurred"
                )
                return  # Safe early return - all attributes already initialized
            # Successfully loaded from file - register to container
            NetworkContainer.register_network(uri, network_data)

        # Setting network data
        self.net = network_data['net']
        if self.uri_parts['network_type'] in ['bus', 'line']:
            self.vn_kv = network_data['vn_kv']
        elif self.uri_parts['network_type'] in ['junction', 'pipe']:
            self.pn_bar = network_data['pn_bar']
        else:
            raise ValueError("Invalid network_type. Expected 'bus', 'line', 'junction', 'pipe'.")  # necessary?
        self.network_type = self.uri_parts['network_type']
        self.type_layer_name = network_data['type_layer_name']
        self.current_crs = int(network_data['current_crs']) if network_data['current_crs'] else 4326
        self.crs = self.sourceCrs()
        self.fields_list = None
        self.df = None
        self._extent = None

        # Store network_data as instance variable for reuse
        # This eliminates the need to recreate network_data dict in addFeatures, deleteFeatures, etc.
        # Reference semantics ensure self.net modifications are automatically reflected
        self.network_data = {
            'net': self.net,
            'vn_kv': self.vn_kv if self.vn_kv is not None else None,
            'pn_bar': self.pn_bar if self.pn_bar is not None else None,
            'type_layer_name': self.type_layer_name,
            'network_type': self.network_type,
            'current_crs': self.current_crs
        }

        provider_list = QgsProviderRegistry.instance().providerList()
        self._is_valid = True

        # State tracking variables for asynchronous save operation of the changeGeometryValues method
        self._save_in_progress = False  # Indicates whether a save operation is in progress
        self._save_thread = None  # QThread instance performing the save operation

        # Register a notification subscription with NetworkContainer.
        NetworkContainer.add_listener(self.uri, self)


    def _load_network_from_file(self):
        """
        Load network data from JSON file when NetworkContainer is empty (e.g., after project reload).
        This restores the network state from the original file.
        Returns:
            dict or None: Network data dictionary if successful, None if failed
        """
        try:
            file_path = self.uri_parts.get('path', '')
            if not file_path:
                return None, "File path is empty"
            if not os.path.exists(file_path):
                return None, f"File not found: {file_path}"

            # Determine network type and load accordingly
            if self.network_type in ['bus', 'line']:
                # Load electrical network (pandapower)
                net = pp.from_json(file_path)

                # Add vn_kv column to lines (same as in ppqgis_import.py)
                pp.add_column_from_node_to_elements(net, 'vn_kv', True, 'line')

                vn_kv = float(self.uri_parts.get('voltage_level', 0))
                epsg = int(self.uri_parts.get('epsg', 4326))

                # Reconstruct type_layer_name from URI parts
                layer_base_name = os.path.basename(file_path).split('.')[0]
                type_layer_name = f'{layer_base_name}_{vn_kv}_{self.network_type}'

                return {
                    'net': net,
                    'vn_kv': vn_kv,
                    'type_layer_name': type_layer_name,
                    'network_type': self.network_type,
                    'current_crs': epsg
                }, None

            elif self.network_type in ['junction', 'pipe']:
                return None, "Pipe networks not yet implemented"
            else:
                return None, f"Invalid network_type: {self.network_type}"

        except Exception as e:
            return None, f"Failed to load network: {str(e)}"


    def merge_df(self):
        """
        Merge dataframe of network_type(ex. bus, line) with its corresponding result dataframe
        to make a integrated dataframe of a layer.
        Applies filtering based on vn_kv (electrical) or pn_bar (gas) values
        and handles cases where calculation results may be missing.
        """
        try:
            # Get the dataframes for the network type and its result
            df_network_type = getattr(self.net, self.network_type)
            df_res_network_type = getattr(self.net, f'res_{self.network_type}')

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
                MessageManager.show_warning(
                    "Empty Layer",
                    f"No {self.network_type} elements found for voltage level {getattr(self, 'vn_kv', 'N/A')} kV"
                )
                return

            # Add meta columns
            # pp_type: Network type (bus, line, junction, pipe)
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

            print("length is 0, called merge df")
            self.merge_df()

            if self.df.empty:
                return QgsFields()

            # generate fields_list dynamically from column of the dataframe
            for column in self.df.columns:
                dt = self.df[column].dtype
                qm = convert_dtype_to_qmetatype(dt)
                self.fields_list.append(QgsField(column, qm))

            # Determine geometry type based on network type
            geometry_type = "Point" if self.network_type in ['bus', 'junction'] else "LineString"

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
        Update geometries of existing features and save changes asynchronously to JSON file.
        Handles both point geometries(bus/junction) and line geometries(line/pipe) with
        concurrent save operation protection.
        Args:
            geometry_map: Map of feature IDs to new QgsGeometry objects
        Returns:
            bool: True if update initiated successfully, False if operation denied or failed
        """
        if self._save_in_progress:
            MessageManager.show_warning(
                "Notification",
                "Previous save operation is still running. Please try again after it is completed."
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

                            # Store as variable for reuse
                            updated_geo_str = json.dumps(geo_data)

                            # Update self.df['geo'] column (for Attribute Table display)
                            if 'geo' in self.df.columns and feature_id in self.df.index:
                                self.df.at[feature_id, 'geo'] = updated_geo_str

                            # Update self.net.bus['geo'] column (root data source)
                            df_network_type = getattr(self.net, self.network_type)
                            if 'geo' in df_network_type.columns and feature_id in df_network_type.index:
                                df_network_type.at[feature_id, 'geo'] = updated_geo_str

                        except Exception as e:
                            raise ValueError(f"Error updating point geometry for ID {feature_id}: {str(e)}")

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

                            # Store changed geodata to update df and net
                            updated_geo_str = json.dumps(geo_data)

                            # Update self.df['geo'] column (for Attribute Table display)
                            if 'geo' in self.df.columns and feature_id in self.df.index:
                                self.df.at[feature_id, 'geo'] = updated_geo_str

                            # Update self.net.line['geo'] column (root data source)
                            df_network_type = getattr(self.net, self.network_type)
                            if 'geo' in df_network_type.columns and feature_id in df_network_type.index:
                                df_network_type.at[feature_id, 'geo'] = updated_geo_str

                        except Exception as e:
                            raise ValueError(f"Error updating line geometry for ID {feature_id}: {str(e)}")

            # Asynchronous file saving tasks (Synchronous file saving tasks deleted)
            # Define a callback function to be executed after saving
            def on_save_complete(success, message, backup_path=None):
                self._save_in_progress = False

                # UI Feedback for success or failure
                if success:
                    MessageManager.show_success(
                        "Saved Successfully",
                        message
                    )
                    # Display backup file information
                    if backup_path:
                        MessageManager.show_info(
                            "Backup Created",
                            f"Backup file: {backup_path}"
                        )

                    # Change Notification Triggered
                    self.dataChanged.emit()

                    # Explicit Layer Update (Maybe not necessary)
                    try:
                        layers = QgsProject.instance().mapLayersByName(self.type_layer_name)
                        if layers:
                            layers[0].triggerRepaint()
                    except Exception as e2:
                        MessageManager.show_warning(
                            "Display Update Failed",
                            f"Could not refresh layer display: {str(e2)}"
                        )
                else:
                    MessageManager.show_error(
                        "Save Failed",
                        message
                    )

            # Start asynchronous save
            self.update_geodata_in_json_async(on_save_complete)
            return True     # Notify that the save operation has started

        except Exception as e:
            MessageManager.show_error(
                "Geometry Update Failed",
                f"Could not update geometries: {str(e)}"
            )
            return False


    def on_update_changed_network(self, network_data):
        """
        Handle network data updates from NetworkContainer notifications.
        Safely updates internal network object and recreates dataframe while preserving
        existing data in case of failure.
        Args:
            network_data: Updated network data dictionary containing 'net' key
        """
        old_net = self.net
        try:
            # Update network object (safe)
            self.net = network_data['net']

            # Create new dataframe in separate variable (prevent Race Condition)
            new_df = self._create_updated_dataframe()

            # Replace at once after validation (Atomic Operation)
            if new_df is not None and not new_df.empty:
                self.df = new_df  # Replace with new dataframe
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
            if 'old_net' in locals():
                self.net = old_net      # Attempt to restore original state when error occurs


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


    def update_geodata_in_json_async(self, callback=None):
        """
        Asynchronously update geodata changes in the original JSON file using background thread.
        Creates backup file before modification and provides UI feedback through callback.
        Note: It is method for asynchronous update.
            For synchronous update, see update_geodata_in_json()
        Args:
            callback: Function to be called after saving is complete.
                on_save_complete(success, message, backup_path)
        """
        if self._save_in_progress:
            MessageManager.show_info(
                "Notify",
                "A save operation is already in progress. Please try again later."
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
                    except Exception as e:
                        # if backup creation failure non-critical and want to proceed
                        #backup_path = ""
                        self.saveCompleted.emit(False, f"Failed to create backup file: {str(e)}", "")
                        return

                    # Load original network from json file
                    try:
                        original_net = pp.from_json(original_path)
                    except Exception as e:
                        self.saveCompleted.emit(False, f"Fail to load original network: {str(e)}", backup_path)
                        return

                    # Modified geodata currently in memory
                    current_geodata = getattr(self.provider.net, f"{self.provider.network_type}").geo

                    # Update the original network’s geodata with the modified coordinates
                    # Only filtered data is considered
                    original_geodata = getattr(original_net, f"{self.provider.network_type}").geo

                    for idx in current_geodata.index:
                        if idx in original_geodata.index:
                            # Copy the current JSON string to the original
                            original_geodata.loc[idx] = current_geodata.loc[idx]

                    # Save the updated network to JSON
                    try:
                        pp.to_json(original_net, original_path)
                        success_msg = f"Coordinate changes have been saved: {original_path}"
                        self.saveCompleted.emit(True, success_msg, backup_path)
                    except PermissionError:
                        error_msg = f"Cannot access the file. It may be open in another program or you don't have write permissions: {original_path}"
                        self.saveCompleted.emit(False, error_msg, backup_path)
                    except Exception as e:
                        error_msg = f"An error occurred while saving file: {str(e)}"
                        self.saveCompleted.emit(False, error_msg, backup_path)

                except Exception as e:
                    self.saveCompleted.emit(False, f"An error occurred while updating geodata: {str(e)}", "")

        # Create a thread for saving
        self._save_thread = SaveThread(self)

        # Connect callback
        if callback:
            self._save_thread.saveCompleted.connect(callback)

        # Starting thread
        self._save_thread.start()


    def update_geodata_in_json(self, auto_save=True):
        """
        Currently not used.
        Synchronously update geodata changes in the original JSON file.
        Creates backup before modification and updates original file with current geometry data.
        Note: It is for synchronous update. For asynchronous update, see update_geodata_in_json_async()
        Args:
            auto_save: If True, saves to file; if False, keeps changes in memory only
            Currently support auto save only.
        Returns:
            bool: True if update successful, False otherwise
        """
        if not auto_save:
            print("Keep changes in memory without saving.")
            return True

        try:
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
                return True
            except PermissionError:
                self.pushError(f"Cannot reach to {original_path}. The file may opened in another program or required permissions.")
                return False
            except Exception as e:
                self.pushError(f"An Error occurred while saving: {str(e)}")
                return False

        except Exception as e:
            self.pushError(f"Error occurred while updating geodata: {str(e)}")
            return False

    # =============================================================================================

    def changeAttributeValues(self, attr_map):
        """
        Change attribute values of existing features and save changes asynchronously to JSON file.
        Includes validation for critical fields and automatic vn_kv update when from_bus changes.
        Args:
            attr_map: Dictionary mapping feature IDs to attribute changes
                      Format: {feature_id: {field_index: new_value, ...}, ...}
        Returns:
            bool: True if update initiated successfully, False if operation denied or failed
        """
        # Check if an existing save operation is in progress
        if self._save_in_progress:
            MessageManager.show_warning(
                "Notification", "Previous save operation is still running. Please try again after it is completed.")
            return False

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

            # Callback function to be executed after saving
            def on_save_complete(success, message, backup_path=None):
                self._save_in_progress = False

                if success:
                    # Display success message
                    MessageManager.show_success("Saved Successfully", message)
                    if backup_path:
                        MessageManager.show_info("Backup Created", f"Backup file: {backup_path}")

                    # Notify QGIS that data changed
                    self.dataChanged.emit()

                    # Trigger layer repaint
                    try:
                        layers = QgsProject.instance().mapLayersByName(self.type_layer_name)
                        if layers:
                            layers[0].triggerRepaint()
                    except Exception as e2:
                        MessageManager.show_warning(
                            "Display Update Failed", f"Could not refresh layer display: {str(e2)}")
                else:
                    MessageManager.show_error(
                        "Save Failed",
                        message
                    )

            # Start asynchronous save
            self.update_attributes_in_json_async(on_save_complete)
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


    def update_attributes_in_json_async(self, callback=None):
        """
        Asynchronously update attribute changes in the original JSON file using background thread.
        Creates backup file before modification and provides UI feedback through callback.
        Args:
            callback: Function to be called after saving is complete.
                      Signature: on_save_complete(success, message, backup_path)
        """
        if self._save_in_progress:
            MessageManager.show_warning(
                "Notification", "A save operation is already in progress. Please try again later.")
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
                    except Exception as e:
                        self.saveCompleted.emit(False, f"Failed to create backup: {str(e)}", "")
                        return

                    # Load original network from json file
                    try:
                        original_net = pp.from_json(original_path)
                    except Exception as e:
                        self.saveCompleted.emit(False, f"Failed to load original network: {str(e)}", backup_path)
                        return

                    # Modified data currently in memory
                    current_df = getattr(self.provider.net, self.provider.network_type)

                    # Update the original network's data with modified attributes
                    original_df = getattr(original_net, self.provider.network_type)

                    new_rows = []

                    # Copy modified rows to original network
                    # Only update rows that exist in current_df (filtered by vn_kv)
                    for idx in current_df.index:
                        if idx in original_df.index:
                            # Copy all columns from current to original
                            for col in current_df.columns:
                                if col in original_df.columns:
                                    original_df.at[idx, col] = current_df.at[idx, col]
                        # Append newly added rows
                        else:
                            new_rows.append(current_df.loc[idx])

                    # Run concat at once after for loop
                    if new_rows:
                        new_df = pd.DataFrame(new_rows)
                        updated_df = pd.concat([original_df, new_df], ignore_index=False)
                        setattr(original_net, self.provider.network_type, updated_df)
                        # Update local variable too
                        original_df = getattr(original_net, self.provider.network_type)

                    # Save the updated network to JSON
                    try:
                        pp.to_json(original_net, original_path)
                        self.saveCompleted.emit(True, f"Attribute changes have been saved: {original_path}", backup_path)
                    except PermissionError:
                        self.saveCompleted.emit(False, f"Cannot access the file. It may be open in another program or you don't have write permissions: {original_path}", backup_path)
                    except Exception as e:
                        self.saveCompleted.emit(False, f"An error occurred while saving file: {str(e)}", backup_path)

                except Exception as e:
                    self.saveCompleted.emit(False, f"An error occurred while updating attributes: {str(e)}", "")

        # Create a thread for saving
        self._save_thread = SaveThread(self)

        # Connect callback
        if callback:
            self._save_thread.saveCompleted.connect(callback)

        # Starting thread
        self._save_thread.start()


    def update_entire_network_in_json_async(self, callback=None):
        """
        Save the ENTIRE network to JSON file asynchronously.
        This method saves the complete network state without merge logic.
        Use this for operations that modify multiple element types simultaneously,
        such as cascade deletions (deleting a bus also deletes connected lines, loads, etc.).
        - Differences from update_attributes_in_json_async():
            - update_attributes_in_json_async(): Smart merge for single layer (bus OR line)
            - update_entire_network_in_json_async(): Direct save of entire network
        Args:
            callback: Optional callback function(success: bool, message: str, backup_path: str)
                     to be called after save completes
        """
        # Check if another save operation is in progress
        if self._save_in_progress:
            MessageManager.show_warning(
                "Notification", "Another save operation is in progress. Please try again later.")
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
                    except Exception as e:
                        self.saveCompleted.emit(False, f"Failed to create backup: {str(e)}", "")
                        return

                    # Save the entire network directly
                    # Note: self.provider.net contains the ENTIRE network (not filtered)
                    # Any modifications (like cascade deletions) are already applied to it
                    try:
                        pp.to_json(self.provider.net, original_path)
                        self.saveCompleted.emit(True, f"Entire network saved: {original_path}", backup_path)
                    except PermissionError:
                        self.saveCompleted.emit(False, f"Cannot access the file. It may be open in another program: {original_path}", backup_path)
                    except Exception as e:
                        self.saveCompleted.emit(False, f"Error saving file: {str(e)}", backup_path)

                except Exception as e:
                    self.saveCompleted.emit(False, f"Error saving entire network: {str(e)}", "")

        # Create a thread for saving
        self._save_thread = SaveThread(self)

        # Connect callback
        if callback:
            self._save_thread.saveCompleted.connect(callback)

        # Start thread
        self._save_thread.start()

    # ===============================================================================

    def addFeatures(self, features, flags=None):
        """
        Add new features to the pandapower network.
        Validates feature data, creates corresponding pandapower elements,
        and updates the NetworkContainer.
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
        # Check if save operation is in progress
        if self._save_in_progress:
            MessageManager.show_warning("Notification", "A save operation is in progress. Please try again later.")
            return (False, [])

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

            # Save to JSON file asynchronously
            def on_save_complete(success, message, backup_path=None):
                self._save_in_progress = False

                if success:
                    MessageManager.show_success(
                        "Features Added", f"Added {len(added_indices)} feature(s) and saved to file.")
                    NetworkContainer.register_network(self.uri, self.network_data)

                    # Trigger data change notification
                    self.dataChanged.emit()

                else:
                    MessageManager.show_error(
                        "⚠️ Save Failed - Features added to memory but NOT Saved to File",
                        f"Features: {added_indices} Reason: {message}\n"
                    )

            # Async run
            self.update_attributes_in_json_async(on_save_complete)
            return (True, features)

        except Exception as e:
            MessageManager.show_error("Add Features Failed", f"Failed to add features: {str(e)}")
            self._save_in_progress = False  # Reset flag on error
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
        # Check if another save operation is in progress
        if self._save_in_progress:
            MessageManager.show_warning(
                "Notification", "Another save operation is in progress. Please try again later.")
            return False

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
        Layer notification without NetworkContainer - call dataChanged.emit() directly on their providers
        Notify all layers that share the same network file and voltage level.
        This handles cascade deletions where multiple network_types are affected
        (e.g., bus deletion causes line deletion).
        """
        try:
            my_path = self.uri_parts.get('path')
            my_vn_kv = self.vn_kv if hasattr(self, 'vn_kv') else None

            # Iterate through all layers in QGIS project
            for layer in QgsProject.instance().mapLayers().values():
                provider = layer.dataProvider()

                if not hasattr(provider, 'uri_parts'):
                    continue    # skip if not PandapowerProvider
                layer_path = provider.uri_parts.get('path')
                if layer_path != my_path:
                    continue    # skip different network file
                layer_vn_kv = provider.vn_kv if hasattr(provider, 'vn_kv') else None
                if layer_vn_kv != my_vn_kv:
                    continue    # skip different voltage level
                if provider.uri == self.uri:
                    continue    # Skip self (will be notified separately in _save_deletions())

                # Notify affected layer
                provider.dataChanged.emit()
                layer.triggerRepaint()

        except Exception as e:
            pass


    def _save_deletions(self, deleted_ids, element_type):
        """
        Save deletions to JSON file asynchronously and update NetworkContainer.
        Added direct layer notification for cascade deletions.
        Args:
            deleted_ids: List of deleted element indices
            element_type: Type of element ('bus' or 'line')
        Returns:
            bool: True (async operation started successfully)
        """
        try:
            # Define callback for after save completes
            def on_save_complete(success, message, backup_path=None):
                self._save_in_progress = False

                if success:
                    MessageManager.show_success(
                        "Features Deleted",
                        f"Deleted {len(deleted_ids)} {element_type}(s) and saved to file"
                    )

                    NetworkContainer.register_network(self.uri, self.network_data)

                    # Direct layer notification - Trigger data change notification (refreshes QGIS display)
                    # Notify self first
                    self.dataChanged.emit()
                    # For cascade deletions (bus deletion), notify affected layers
                    if element_type == 'bus':
                        self._notify_affected_layers()
                else:
                    MessageManager.show_error(
                        "Save Failed",
                        f"Elements deleted from memory but NOT saved to file!\n"
                        f"Deleted {element_type}(s): {deleted_ids}\n"
                        f"Reason: {message}\n\n"
                        f"You can restore from backup file if needed."
                    )

            # Start async save operation
            # This will update both the element table and res_ table in JSON
            self.update_entire_network_in_json_async(on_save_complete)
            return True

        except Exception as e:
            MessageManager.show_error("Save Failed", f"Failed to initiate save operation: {str(e)}")
            self._save_in_progress = False  # Reset flag on error
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
        Returns:
            QgsVectorDataProvider.Capabilities
        """
        return (
            QgsVectorDataProvider.CreateSpatialIndex |
            QgsVectorDataProvider.SelectAtId |
            QgsVectorDataProvider.ChangeGeometries |
            QgsVectorDataProvider.ChangeAttributeValues |
            QgsVectorDataProvider.AddFeatures |
            QgsVectorDataProvider.DeleteFeatures
        )


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
            QgsWkbTypes: Point for bus/junction, LineString for line/pipe
        """
        if self.network_type == 'bus' or self.network_type == 'junction':
            return QgsWkbTypes.Point
        elif self.network_type == 'line' or self.network_type == 'pipe':
            return QgsWkbTypes.LineString


    def unload(self):
        """
        Clean up provider resources when being destroyed.
        Removes network update listener, waits for background save operations to complete,
        and unregisters the provider from the registry.
        """
        # Remove from listener
        NetworkContainer.remove_listener(self.uri, self)
        # Wait until the running save thread completes
        if self._save_thread and self._save_thread.isRunning():
            self._save_thread.wait()
        # Remove custom data provider when it is deleted
        QgsProviderRegistry.instance().removeProvider('PandapowerProvider')
