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

        # Bring network data from container
        network_data = NetworkContainer.get_network(uri)
        # if network_data is None:
        #     self._is_valid = False
        #     return

        # If container is empty (e.g., after project reload), load from file
        if network_data is None:
            print(f"⚠️ NetworkContainer is empty for URI: {uri}")
            print(f"🔄 Attempting to load network from file...")
            network_data = self._load_network_from_file()

            if network_data is None:
                print(f"❌ Failed to load network from file: {self.uri_parts.get('path')}")
                return  # Safe early return - all attributes already initialized

            # Successfully loaded - register to container
            print(f"✅ Network loaded from file, registering to container...")
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

        provider_list = QgsProviderRegistry.instance().providerList()
        print("provider list by init ppprovider", provider_list)
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
            if not file_path or not os.path.exists(file_path):
                print(f"⚠️ File not found: {file_path}")
                return None

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

                print(f"✅ Loaded pandapower network: vn_kv={vn_kv}")

                return {
                    'net': net,
                    'vn_kv': vn_kv,
                    'type_layer_name': type_layer_name,
                    'network_type': self.network_type,
                    'current_crs': epsg
                }
            elif self.network_type in ['junction', 'pipe']:
                pass
            else:
                print(f"❌ Unknown network_type: {self.network_type}")
                return None

        except Exception as e:
            print(f"❌ Error loading network from file: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


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

            if df_network_type is None:
                print(f"Error: No dataframe found for {self.network_type}.")
                self.df = pd.DataFrame()  # Set to empty DataFrame
                return

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
                print(f"Warning: The final DataFrame is empty. {self.network_type}, vn_kv: {getattr(self, 'vn_kv', 'N/A')}")
                from qgis.utils import iface
                from qgis.core import Qgis
                if iface:
                    iface.messageBar().pushMessage(
                        "Warning",
                        f"Layer '{self.type_layer_name}' is empty. No {self.network_type} found for this voltage level.",
                        level=Qgis.Warning,
                        duration=5
                    )
                return QgsFields()

            # Add meta columns
            # pp_type: Network type (bus, line, junction, pipe)
            self.df.insert(0, 'pp_type', self.network_type)
            # pp_index: Index in the original pandapower network
            self.df.insert(1, 'pp_index', self.df.index)

        except Exception as e:
            print(f"❌ An error occurred in merge_df ({self.network_type}): {str(e)}")
            import traceback
            traceback.print_exc()
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

            # Check if dataframe is empty
            if self.df.empty:
                print(f"No data available for network type: {self.network_type}, called in fields method while initializing")  # Debugging
                return
            else:
                print("print df.columns: ", self.df.columns)

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
                            print(f"Error updating line geometry for ID {feature_id}: {str(e)}")
                    else:
                        print(f"Warning: {self.network_type} with ID {feature_id} not found in geodata")

            # Synchronous file saving tasks deleted
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
            if new_df is None:  # In this case renderer might receive empty data
                print("⚠️ DataFrame creation failed!")

            # Replace at once after validation (Atomic Operation)
            if new_df is not None and not new_df.empty:
                # Replace only when successfully created
                # self.fields_list = None  # Initialize field cache
                self.df = new_df  # Replace with new dataframe
            else:
                # Keep existing data in case of failure
                print(f"⚠️ Provider {self.uri}: New data creation failed, keeping existing data")

        except Exception as e:
            print(f"❌ Provider {self.uri}: Update failed - {str(e)}")
            # Attempt to restore original state when error occurs
            if 'old_net' in locals():
                self.net = old_net


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

            if df_network_type is None:
                print(f"⚠️ {self.network_type} data not found")
                return None

            # Check calculation results
            has_result_data = (df_res_network_type is not None and
                               not df_res_network_type.empty and
                               len(df_res_network_type) > 0)

            if has_result_data:
                print("✅ Calculation results available! Using existing method")

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
                print("⚠️ No calculation results! Using new method")
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
            import traceback
            traceback.print_exc()
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
                        # if backup creation failure non-critical and want to proceed
                        #backup_path = ""
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
            from qgis.utils import iface
            from qgis.core import Qgis
            iface.messageBar().pushMessage(
                "Notification",
                "The previous save operation is still in progress. Please try again after it is completed.",
                level=Qgis.Warning,
                duration=5
            )
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
                        print(f"⚠️ Field '{field_name}' is read-only, skipping")
                        continue

                    # 3. Validate critical fields BEFORE applying changes
                    validation_error = self._validate_field_value(field_name, new_value, feature_id)
                    if validation_error:
                        validation_errors.append(validation_error)
                        continue  # Skip this invalid change

                    # 4. Update self.df (cache for Attribute Table)
                    if feature_id in self.df.index:
                        self.df.at[feature_id, field_name] = new_value
                        print(f"✅ Updated self.df[{feature_id}]['{field_name}'] = {new_value}")

                    # 5. Update self.net (root data source)
                    df_network_type = getattr(self.net, self.network_type)
                    if feature_id in df_network_type.index:
                        df_network_type.at[feature_id, field_name] = new_value
                        print(f"✅ Updated net.{self.network_type}[{feature_id}]['{field_name}'] = {new_value}")

                    # Track modified feature
                    modified_features.add(feature_id)

            # Show validation errors to user
            if validation_errors:
                from qgis.utils import iface
                from qgis.core import Qgis
                error_msg = "\n".join(validation_errors[:5])  # Show first 5 errors
                if len(validation_errors) > 5:
                    error_msg += f"\n... and {len(validation_errors) - 5} more errors"

                iface.messageBar().pushMessage(
                    "⚠️ Validation Error",
                    f"Some changes were rejected:\n{error_msg}",
                    level=Qgis.Warning,
                    duration=10
                )

            # If no valid changes were made, return early
            if not modified_features:
                print("⚠️ No valid attribute changes to save")
                return False

            # Callback function to be executed after saving
            def on_save_complete(success, message, backup_path=None):
                self._save_in_progress = False

                from qgis.core import Qgis
                from qgis.utils import iface

                if success:
                    # Display success message
                    iface.messageBar().pushMessage(
                        "✅ Saved Successfully",
                        message,
                        level=Qgis.Success,
                        duration=5
                    )

                    # Display backup file information
                    if backup_path:
                        iface.messageBar().pushMessage(
                            "💾 Backup file created",
                            f"path: {backup_path}",
                            level=Qgis.Info,
                            duration=8
                        )

                    # Notify QGIS that data changed
                    self.dataChanged.emit()

                    # Trigger layer repaint
                    try:
                        layers = QgsProject.instance().mapLayersByName(self.type_layer_name)
                        if layers:
                            layers[0].triggerRepaint()
                            print(f"🔄 Triggered repaint for layer: {self.type_layer_name}")
                    except Exception as e:
                        print(f"⚠️ Warning: Could not trigger layer repaint: {str(e)}")
                else:
                    # Display failure message
                    iface.messageBar().pushMessage(
                        "❌ Save failed",
                        message,
                        level=Qgis.Critical,
                        duration=10
                    )

            # Start asynchronous save
            self.update_attributes_in_json_async(on_save_complete)
            return True

        except Exception as e:
            self.pushError(f"❌ Failed to change attributes: {str(e)}")
            import traceback
            traceback.print_exc()
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
            required_fields = ['from_bus', 'to_bus'] if self.network_type == 'line' else ['from_junction', 'to_junction']

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

        return None  # ✅ Valid


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

                    print("=" * 80)
                    print("🔍 DEBUG: SaveThread START")
                    print(f"self.provider.network_type: {self.provider.network_type}")
                    print(f"current_df.shape: {current_df.shape}")
                    print(f"current_df.index (first 10): {current_df.index[:10].tolist()}")
                    print(f"current_df.index (last 5): {current_df.index[-5:].tolist()}")
                    print(f"current_df.columns: {current_df.columns.tolist()}")
                    print("=" * 80)

                    # Update the original network's data with modified attributes
                    original_df = getattr(original_net, self.provider.network_type)

                    print("=" * 80)
                    print("🔍 DEBUG: Original network loaded")
                    print(f"original_df.shape: {original_df.shape}")
                    print(f"original_df.index (first 10): {original_df.index[:10].tolist()}")
                    print(f"original_df.index (last 5): {original_df.index[-5:].tolist()}")
                    print("=" * 80)
                    updated_count = 0 #debug
                    new_count = 0 #debug

                    # ✨✨✨ 추가: 새로운 rows를 모을 리스트 초기화
                    new_rows = []

                    # Copy modified rows to original network
                    # Only update rows that exist in current_df (filtered by vn_kv)
                    for idx in current_df.index:
                        if idx in original_df.index:
                            # Copy all columns from current to original
                            for col in current_df.columns:
                                if col in original_df.columns:
                                    original_df.at[idx, col] = current_df.at[idx, col]
                            updated_count += 1 # debug
                        # else:
                        #     # For newly added feature, add new row to original network
                        #     new_row = current_df.loc[idx].to_frame().T
                        #     # Concatenate new row to original dataframe
                        #     updated_df = pd.concat([original_df, new_row], ignore_index=False)
                        #
                        #     # Update the network object
                        #     setattr(original_net, self.provider.network_type, updated_df)
                        #
                        #     # Update local reference for next iteration
                        #     original_df = getattr(original_net, self.provider.network_type)
                        #     print(f"✅ Row {idx} added successfully")
                        #     new_count += 1 # debug
                        # ✨✨✨ 추가: 새 row를 리스트에 수집만 함
                        else:
                            new_rows.append(current_df.loc[idx])
                            new_count += 1  # debug

                    # ✨✨✨ 추가: for 루프 종료 후, 한번에 concat 수행
                    if new_rows:
                        new_df = pd.DataFrame(new_rows)
                        updated_df = pd.concat([original_df, new_df], ignore_index=False)
                        setattr(original_net, self.provider.network_type, updated_df)
                        # 로컬 변수도 업데이트 (라인 1111-1113에서 사용하기 때문)
                        original_df = getattr(original_net, self.provider.network_type)
                        print(f"✅ Added {len(new_rows)} new rows in single operation")


                    print("=" * 80)
                    print("🔍 DEBUG: SaveThread processing complete")
                    print(f"Updated {updated_count} existing rows")
                    print(f"Added {new_count} new rows")
                    print(f"original_df.shape after processing: {original_df.shape}")
                    print(f"original_df.index (first 10): {original_df.index[:10].tolist()}")
                    print(f"original_df.index (last 5): {original_df.index[-5:].tolist()}")
                    print("=" * 80)

                    # Save the updated network to JSON
                    try:
                        pp.to_json(original_net, original_path)
                        success_msg = f"Attribute changes have been saved: {original_path}"
                        self.saveCompleted.emit(True, success_msg, backup_path)
                    except PermissionError:
                        error_msg = f"Cannot access the file. It may be open in another program or you don't have write permissions: {original_path}"
                        self.saveCompleted.emit(False, error_msg, backup_path)
                    except Exception as e:
                        error_msg = f"An error occurred while saving file: {str(e)}"
                        self.saveCompleted.emit(False, error_msg, backup_path)

                except Exception as e:
                    import traceback
                    error_msg = f"An error occurred while updating attributes: {str(e)}"
                    traceback.print_exc()
                    self.saveCompleted.emit(False, error_msg, "")

        # Create a thread for saving
        self._save_thread = SaveThread(self)

        # Connect callback
        if callback:
            self._save_thread.saveCompleted.connect(callback)

        # Starting thread
        self._save_thread.start()


    def addFeatures(self, features, flags=None):
        """
        Add new features to the pandapower network.
        Validates feature data, creates corresponding pandapower elements,
        and updates the NetworkContainer.

        Note: This method follows the PyQGIS convention where C++ reference parameters
            (marked with SIP_INOUT) are returned as part of a tuple in Python.
        Args:
            features: List of QgsFeature objects to add
            flags: Optional flags (currently unused)
        Returns:
            tuple: (success, features) where:
                - success (bool): True if features were successfully added, False otherwise
                - features (list): The list of features with updated IDs and attributes
        """
        import traceback
        print("=" * 80)
        print(f"🔥 addFeatures() CALLED for {self.network_type}")
        print(f"   _save_in_progress = {self._save_in_progress}")
        print(f"   features count = {len(features)}")
        print("   Call stack:")
        for line in traceback.format_stack()[-5:-1]:
            print(f"     {line.strip()}")
        print("=" * 80)

        # Setup attribute form if not done yet
        #self._setup_attribute_form()

        # Check if save operation is in progress
        if self._save_in_progress:
            from qgis.utils import iface
            from qgis.core import Qgis
            iface.messageBar().pushMessage(
                "Notification",
                "A save operation is in progress. Please try again later.",
                level=Qgis.Warning,
                duration=5
            )
            return (False, [])

        # 🛡️ NEW: Pre-validation - Check if file can be saved BEFORE processing
        if not self._validate_can_save():
            print("❌ addFeatures aborted: Pre-validation failed")
            return (False, [])  # QGIS will keep features in buffer (no commit)

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

            # Show validation errors if any
            if validation_errors:
                from qgis.utils import iface
                from qgis.core import Qgis
                error_msg = "\n".join(validation_errors[:5])
                if len(validation_errors) > 5:
                    error_msg += f"\n... and {len(validation_errors) - 5} more errors"

                iface.messageBar().pushMessage(
                    "Validation Error",
                    f"Cannot add features due to validation errors:\n{error_msg}",
                    level=Qgis.Critical,
                    duration=10
                )
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
                print("No features were added to pandapower network")
                return (False, [])

            # 🔥🔥🔥 수정: 새 row만 self.df에 추가
            print("=" * 80)
            print("🔄 Adding new rows to self.df...")
            print(f"BEFORE: self.df.shape = {self.df.shape}, index = {self.df.index.tolist()}")

            # net.bus와 net.res_bus에서 해당 row 가져오기
            df_network_type = getattr(self.net, self.network_type)
            df_res_network_type = getattr(self.net, f'res_{self.network_type}')
            # 🎯 NEW: 새 rows를 리스트에 모으기
            new_rows = []

            # 각 새 feature를 self.df에 추가
            for idx in added_indices:
                # 새 row 구성
                bus_row = df_network_type.loc[idx]

                # res가 있으면 merge
                if idx in df_res_network_type.index:
                    res_row = df_res_network_type.loc[idx]
                    # 두 Series를 합치기
                    new_row = pd.concat([bus_row, res_row])
                else:
                    new_row = bus_row
                    # res 컬럼들을 None으로 추가
                    for col in df_res_network_type.columns:
                        new_row[col] = None

                # pp_type, pp_index 추가
                new_row_dict = new_row.to_dict()
                new_row_dict['pp_type'] = self.network_type
                new_row_dict['pp_index'] = idx

                # 🎯 NEW: 리스트에 append (DataFrame 생성은 나중에)
                new_rows.append(new_row_dict)
                # # DataFrame에 추가
                # new_row_df = pd.DataFrame([new_row_dict], index=[idx])
                # self.df = pd.concat([self.df, new_row_df], ignore_index=False)

                print(f"✅ Prepared row {idx} for adding to self.df")

            # 🎯🔥 NEW: 한번에 concat (O(n*m) → O(n+m) 성능 개선)
            if new_rows:
                new_df = pd.DataFrame(new_rows, index=added_indices)
                self.df = pd.concat([self.df, new_df], ignore_index=False)
                print(f"✅ Added {len(new_rows)} rows to self.df in single concat operation")

            print(f"AFTER: self.df.shape = {self.df.shape}")
            print(f"self.df.index: {self.df.index.tolist()}")
            print("=" * 80)

            # # Update NetworkContainer to notify all listeners
            # NetworkContainer.register_network(self.uri, {'net': self.net, 'vn_kv': self.vn_kv,
            #                                              'type_layer_name': self.type_layer_name,
            #                                              'network_type': self.network_type,
            #                                              'current_crs': self.current_crs})

            # Save to JSON file asynchronously
            def on_save_complete(success, message, backup_path=None):
                print("=" * 80)
                print("🔍 DEBUG: on_save_complete() START")
                print(f"success: {success}")
                print(f"message: {message}")
                print(f"self.net.bus.shape: {self.net.bus.shape}")
                print(f"self.net.bus.index (first 10): {self.net.bus.index[:10].tolist()}")
                print(f"self.net.bus.index (last 5): {self.net.bus.index[-5:].tolist()}")
                print(f"self.df.shape: {self.df.shape}")
                print(
                    f"self.df.index (first 10): {self.df.index[:10].tolist() if len(self.df) >= 10 else self.df.index.tolist()}")
                print(
                    f"self.df.index (last 5): {self.df.index[-5:].tolist() if len(self.df) >= 5 else self.df.index.tolist()}")
                print("=" * 80)

                self._save_in_progress = False

                from qgis.core import Qgis
                from qgis.utils import iface

                if success:
                    iface.messageBar().pushMessage(
                        "Features Added",
                        f"Added {len(added_indices)} feature(s) and saved to file",
                        level=Qgis.Success,
                        duration=5
                    )

                    print("=" * 80)
                    print("🔍 DEBUG: BEFORE dataChanged.emit()")
                    print(f"self.net.bus.shape: {self.net.bus.shape}")
                    print(f"self.net.bus.index[:10]: {self.net.bus.index[:10].tolist()}")
                    print(f"self.net.bus.index[-5:]: {self.net.bus.index[-5:].tolist()}")
                    print(f"self.df.shape: {self.df.shape}")
                    print(
                        f"self.df.index[:10]: {self.df.index[:10].tolist() if len(self.df) >= 10 else self.df.index.tolist()}")
                    print(
                        f"self.df.index[-5:]: {self.df.index[-5:].tolist() if len(self.df) >= 5 else self.df.index.tolist()}")
                    print("=" * 80)

                    # 💾✅ NEW: 저장 성공 후 NetworkContainer 업데이트 (changeGeometry/AttributeValues 패턴)
                    network_data = {
                        'net': self.net,
                        'vn_kv': self.vn_kv,
                        'type_layer_name': self.type_layer_name,
                        'network_type': self.network_type,
                        'current_crs': self.current_crs
                    }
                    NetworkContainer.register_network(self.uri, network_data)
                    print("✅ NetworkContainer updated after successful save")

                    # Trigger data change notification
                    self.dataChanged.emit()

                    print("=" * 80)
                    print("🔍 DEBUG: AFTER dataChanged.emit()")
                    print(f"self.net.bus.shape: {self.net.bus.shape}")
                    print(f"self.net.bus.index[:10]: {self.net.bus.index[:10].tolist()}")
                    print(f"self.net.bus.index[-5:]: {self.net.bus.index[-5:].tolist()}")
                    print(f"self.df.shape: {self.df.shape}")
                    print(
                        f"self.df.index[:10]: {self.df.index[:10].tolist() if len(self.df) >= 10 else self.df.index.tolist()}")
                    print(
                        f"self.df.index[-5:]: {self.df.index[-5:].tolist() if len(self.df) >= 5 else self.df.index.tolist()}")
                    print("=" * 80)
                else:
                    iface.messageBar().pushMessage(
                        "⚠️ Save Failed - Features added to memory but NOT Saved to File",
                        f"Features: {added_indices} Reason: {message}\n",
                        level=Qgis.Critical,
                        duration=0
                    )

                    # 📋 Detailed log for debugging
                    print("=" * 80)
                    print("❌ SAVE FAILED - FEATURES NOT IN FILE")
                    print(f"Features in memory only: {added_indices}")
                    print(f"Reason: {message}")
                    print(f"File: {self.uri_parts.get('path', 'unknown')}")
                    print("=" * 80)
                    print("⚠️ USER ACTION REQUIRED:")
                    print("  1. Fix the issue (close programs, check permissions)")
                    print("  2. Save again (Ctrl+S)")
                    print("  3. Or Undo (Ctrl+Z) to remove features")
                    print("⚠️ Features will disappear on QGIS restart if not saved!")
                    print("=" * 80)
                    # 💾❌ NEW: 저장 실패 시 NetworkContainer 업데이트 안 함 (디버깅 로그)

                    print("⚠️ NetworkContainer NOT updated due to save failure")
                    print(f"⚠️ Feature {added_indices} exists in memory but not in file or NetworkContainer")

            # Direct after NetworkContainer update
            print(f"=" * 80)
            print(f"🔍 BEFORE SAVE:")
            print(f"self.net.bus.index.tolist()[-5:] = {self.net.bus.index.tolist()[-5:]}")
            print(f"Bus 320 in self.net.bus? {320 in self.net.bus.index}")
            print(f"self.net is ? {id(self.net)}")
            print(f"=" * 80)

            # Async run
            print(f"Calling update_attributes_in_json_async()...")
            self.update_attributes_in_json_async(on_save_complete)
            print(f"update_attributes_in_json_async() returned")

            print(f"Added {len(added_indices)} features: {added_indices}")
            print(f"Returning (True, features)")
            return (True, features)

        except Exception as e:
            self.pushError(f"Failed to add features: {str(e)}")
            self._save_in_progress = False  # Reset flag on error
            import traceback
            traceback.print_exc()
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
                print(f"⚠️ Index {idx} not found in {self.network_type} dataframe")
                return

            row = df.loc[idx]

            # Update read-only fields with actual values
            updated_fields = []
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
                        updated_fields.append(f"{field_name}={value}")

            print(f"✅ Updated read-only attributes for feature {idx}: {', '.join(updated_fields)}")

        except Exception as e:
            print(f"⚠️ Error updating feature attributes for {idx}: {str(e)}")
            import traceback
            traceback.print_exc()


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
            print(f"Error getting layer: {str(e)}")
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
            from qgis.core import QgsEditFormConfig, QgsDefaultValue, QgsFieldConstraints, QgsEditorWidgetSetup

            # Try to get layer from QgsProject
            layer = self._get_layer()
            if layer is None:
                # Layer not yet available, will retry later
                return
            
            # Set flag to avoid recursion
            self._form_setup_done = True

            config = layer.editFormConfig()
            #field_names = [f.name() for f in self.fields()]
            field_names = [f.name() for f in self.fields_list]

            # Configure each field
            for field_name in field_names:
                #field_idx = self.fields().indexOf(field_name)
                field_idx = self.fields_list.indexOf(field_name)
                if field_idx < 0:
                    continue

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
                            field_idx,
                            QgsDefaultValue(default_expr, applyOnUpdate=False)
                        )
                        print(f"✅ Set default value for '{field_name}': {default_expr}")

                # Configure editable fields (widgets & constraints)
                else:
                    # Configure widget type
                    if field_name == 'in_service':
                        # Boolean fields → CheckBox
                        layer.setEditorWidgetSetup(field_idx, QgsEditorWidgetSetup('CheckBox', {}))

                    elif field_name in ['from_bus', 'to_bus', 'from_junction', 'to_junction']:
                        # Bus/Junction references → TextEdit (numeric input)
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

            # 🔷 3. Set Table View as default (not Form View)
            from qgis.core import QgsAttributeTableConfig
            table_config = layer.attributeTableConfig()
            table_config.setActionWidgetStyle(QgsAttributeTableConfig.ButtonList)
            table_config.update(layer.fields())
            layer.setAttributeTableConfig(table_config)

            print(f"✅ Attribute form configured for {self.network_type}")

        except Exception as e:
            self._form_setup_done = False
            print(f"Error setting up attribute form: {str(e)}")
            import traceback
            traceback.print_exc()


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
            # Return actual network type
            return self.network_type

        elif field_name == 'pp_index':
            # Show next available index (recalculated each time dialog opens)
            next_idx = self._get_next_index()
            return int(next_idx)

        elif field_name == 'vn_kv' and self.network_type in ['bus', 'line']:
            # Return actual voltage level from layer
            return float(self.vn_kv)

        elif field_name == 'pn_bar' and self.network_type in ['junction', 'pipe']:
            # Return actual pressure level from layer
            return float(self.pn_bar)

        elif field_name == 'geo':
            # Geometry is auto-generated from click position
            return "(auto-generated)"

        # Other read-only fields - res columns
        #return None
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
                print(f"Warning: {res_table_name} does not exist in network")
                return False

            res_df = getattr(self.net, res_table_name)

            # Check if res_df is None (shouldn't happen with pandapower, but defensive)
            if res_df is None:
                print(f"Warning: {res_table_name} is None (unexpected)")
                return False

            # Check if res_df has columns (structure exists)
            if len(res_df.columns) == 0:
                print(f"Warning: {res_table_name} has no columns")
                return False

            # Check if row already exists (safety check)
            if idx in res_df.index:
                print(f"Info: {res_table_name}[{idx}] already exists, skipping")
                return True

            # Create empty row with all columns as NaN
            # dtype=float ensures all values are NaN (float type)
            new_row = pd.Series(index=res_df.columns, name=idx, dtype=float)

            # Add row to res dataframe using concat
            # ignore_index=False preserves the index (idx)
            updated_res = pd.concat([res_df, new_row.to_frame().T], ignore_index=False)

            # Update the network's res dataframe
            setattr(self.net, res_table_name, updated_res)

            print(f"✅ Added empty {res_table_name} row for index {idx}")
            return True

        except Exception as e:
            print(f"❌ Error adding empty res row for {self.network_type}[{idx}]: {str(e)}")
            import traceback
            traceback.print_exc()
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
            import pandapower as pp

            # Extract geometry
            geometry = feature.geometry()

            # Prepare attributes dictionary (only editable fields)
            attributes = {}
            for field in self.fields():
                field_name = field.name()
                if self.is_field_editable(field_name):
                    value = feature.attribute(field_name)
                    # Skip None/NULL values - let pandapower use defaults
                    if value is not None and not pd.isna(value):
                        attributes[field_name] = value

            # Create element based on network type
            if self.network_type == 'bus':
                # Create bus
                # Required: name, vn_kv
                # Get vn_kv from layer (not from user input)
                # name = attributes.get('name', f'Bus_{self._get_next_index()}')
                name = attributes.pop('name', f'Bus_{self._get_next_index()}')
                type_val = attributes.pop('type', 'b')
                in_service = attributes.pop('in_service', True)
                # In attributes remains now kwargs


                # 🔍 디버깅: create_bus 호출 전
                print("=" * 80)
                print("🔍 DEBUG: BEFORE pp.create_bus()")
                print(f"self.net.bus.shape: {self.net.bus.shape}")
                print(f"self.net.bus.columns: {self.net.bus.columns.tolist()}")
                print(f"self.net.bus.index (first 10): {self.net.bus.index[:10].tolist()}")
                print(f"self.net.bus.index (last 5): {self.net.bus.index[-5:].tolist()}")
                print(f"self.net.bus DataFrame id: {id(self.net.bus)}")
                print(f"kwargs to pass: {attributes}")
                print("=" * 80)


                # Create bus with required parameters
                idx = pp.create_bus(
                    self.net,
                    name=name,
                    vn_kv=self.vn_kv,  # Use layer's voltage level
                    type=type_val,
                    in_service=in_service,
                    **attributes    # oder *?
                )

                # 🔍 디버깅: create_bus 호출 후
                print("=" * 80)
                print("🔍 DEBUG: AFTER pp.create_bus()")
                print(f"Created bus index: {idx}")
                print(f"self.net.bus.shape: {self.net.bus.shape}")
                print(f"self.net.bus.columns: {self.net.bus.columns.tolist()}")
                print(f"self.net.bus.index (first 10): {self.net.bus.index[:10].tolist()}")
                print(f"self.net.bus.index (last 5): {self.net.bus.index[-5:].tolist()}")
                print(f"self.net.bus DataFrame id: {id(self.net.bus)}")
                print(f"Bus {idx} data:")
                print(self.net.bus.loc[idx])
                print("=" * 80)

                # Add empty res row immediately
                self._add_empty_res_row(idx)

                # Add geometry to geo column
                if not geometry.isNull():
                    point = geometry.asPoint()
                    geo_json = json.dumps({
                        'type': 'Point',
                        'coordinates': [point.x(), point.y()]
                    })
                    self.net.bus.at[idx, 'geo'] = geo_json

                print(f"Created bus {idx}: {name} at {self.vn_kv} kV")
                return idx

            elif self.network_type == 'line':
                # Create line
                # Required: from_bus, to_bus, length_km, std_type
                # from_bus = attributes.get('from_bus')
                # to_bus = attributes.get('to_bus')
                # length_km = attributes.get('length_km')
                # std_type = attributes.get('std_type')
                from_bus = attributes.pop('from_bus', None)
                to_bus = attributes.pop('to_bus', None)
                length_km = attributes.pop('length_km', None)
                std_type = attributes.pop('std_type', None)

                if from_bus is None or to_bus is None or length_km is None or std_type is None:
                    self.pushError("Missing required fields for line: from_bus, to_bus, length_km, std_type")
                    return None

                name = attributes.pop('name', f'Line_{self._get_next_index()}')
                in_service = attributes.pop('in_service', True)
                parallel = attributes.pop('parallel', 1)

                # Create line with required parameters
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
                        'type': 'LineString',
                        'coordinates': coords
                    })
                    self.net.line.at[idx, 'geo'] = geo_json

                print(f"Created line {idx}: {from_bus} -> {to_bus}, {length_km} km")
                return idx

            else:
                self.pushError(f"Unsupported network type for addFeatures: {self.network_type}")
                return None

        except Exception as e:
            self.pushError(f"Error adding feature to pandapower: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


    def _validate_can_save(self):
        """
        🛡️ PRE-VALIDATION: Validate that file can be saved before processing features.
        Checks file existence, write permissions, and file lock status.
        Shows user-friendly error messages if validation fails.

        Returns:
            bool: True if safe to proceed with save, False if save will fail
        """
        from qgis.core import Qgis
        from qgis.utils import iface
        import os

        json_path = self.uri_parts.get('path', '')

        # 🛡️ Check 1: File exists
        if not json_path or not os.path.exists(json_path):
            iface.messageBar().pushMessage(
                "❌ Cannot Save",
                f"File not found: {json_path}\n"
                f"The file may have been moved or deleted.",
                level=Qgis.Critical,
                duration=0
            )
            print(f"❌ Pre-validation failed: File not found - {json_path}")
            return False

        # 🛡️ Check 2: Write permission
        if not os.access(json_path, os.W_OK):
            iface.messageBar().pushMessage(
                "❌ Cannot Save",
                f"No write permission: {json_path}\n"
                f"Check file properties (read-only?) or contact administrator.",
                level=Qgis.Critical,
                duration=0
            )
            print(f"❌ Pre-validation failed: No write permission - {json_path}")
            return False

        # 🛡️ Check 3: File not locked (by other program)
        try:
            # Try to open in read-write mode (doesn't actually modify)
            with open(json_path, 'r+') as f:
                pass
        except PermissionError:
            iface.messageBar().pushMessage(
                "❌ Cannot Save",
                f"File is locked: {json_path}\n"
                f"Close any programs using this file (Excel, text editor, etc.)",
                level=Qgis.Critical,
                duration=0
            )
            print(f"❌ Pre-validation failed: File is locked - {json_path}")
            return False
        except Exception as e:
            # Unexpected error during file check
            iface.messageBar().pushMessage(
                "❌ Cannot Save",
                f"Cannot access file: {json_path}\n"
                f"Error: {str(e)}",
                level=Qgis.Critical,
                duration=0
            )
            print(f"❌ Pre-validation failed: Unexpected error - {str(e)}")
            return False

        # ✅ All checks passed
        print(f"✅ Pre-validation passed: {json_path}")
        return True


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
            QgsVectorDataProvider.AddFeatures
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
        print(f"CRS is valid: {crs.authid()}") # Debugging
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
                                    print(f"Incorrect coordinate format for {self.network_type}.")
                                    return
                        except Exception as e:
                            print(f"Warning: Bus/Junction data of index {idx} failed to produce: {str(e)}")

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
