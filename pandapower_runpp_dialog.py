import os

from pandapower import runpm_tnep
from qgis.PyQt import QtWidgets, QtCore
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                                 QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
                                 QCheckBox, QDialogButtonBox, QGroupBox,
                                 QProgressBar, QTextEdit, QPushButton, QFrame, QComboBox)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.core import QgsProviderRegistry
from .network_container import NetworkContainer


class ppRunDialog(QDialog):
    def __init__(self, parent=None):
        """Constructor - initialize the RunPP dialog."""
        super(ppRunDialog, self).__init__(parent)

        # Dialog default settings
        self.setWindowTitle(self.tr("Run Pandapower Network"))
        self.setMinimumWidth(450)
        self.setMinimumHeight(600)

        # Save network information
        self.uri = None
        self.network_data = None
        self.network_type = None

        self.setup_ui()


    def setup_ui(self):
        """Configure the UI layout."""
        # Main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # 1. Network info group
        self.create_network_info_group()
        main_layout.addWidget(self.network_info_group)

        # 2. RunPP option group
        self.create_runpp_options_group()
        main_layout.addWidget(self.runpp_options_group)

        # 3. Advanced option group
        self.create_advanced_options_group()
        main_layout.addWidget(self.advanced_options_group)

        # 4. Progress group
        self.create_progress_group()
        main_layout.addWidget(self.progress_group)

        # 5. Button
        self.create_buttons()
        main_layout.addWidget(self.button_box)


    def create_network_info_group(self):
        """Create groupbox to display network information."""
        self.network_info_group = QGroupBox(self.tr("Network Information"))
        layout = QGridLayout()

        # Network type label
        self.network_type_label = QLabel(self.tr("Network Type: "))
        self.network_type_value = QLabel(self.tr("Not loaded"))
        layout.addWidget(self.network_type_label, 0, 0)
        layout.addWidget(self.network_type_value, 0, 1)

        # Bus/Junction count label
        self.bus_label = QLabel(self.tr("Buses/Junctions: "))
        self.bus_count = QLabel("0")
        layout.addWidget(self.bus_label, 1, 0)
        layout.addWidget(self.bus_count, 1, 1)

        # Line/Pipe count label
        self.line_label = QLabel(self.tr("Lines/Pipes: "))
        self.line_count = QLabel("0")
        layout.addWidget(self.line_label, 2, 0)
        layout.addWidget(self.line_count, 2, 1)

        # File path label
        self.file_path_label = QLabel(self.tr("File: "))
        self.file_path_value = QLabel(self.tr("Not loaded"))
        self.file_path_value.setWordWrap(True)
        layout.addWidget(self.file_path_label, 3, 0)
        layout.addWidget(self.file_path_value, 3, 1)

        self.network_info_group.setLayout(layout)


    def create_runpp_options_group(self):
        """Create a group box to configure RunPP options."""
        self.runpp_options_group = QGroupBox(self.tr("RunPP Options"))
        layout = QGridLayout()

        # Choose run function
        layout.addWidget(QLabel(self.tr("Function:")), 0, 0)
        self.run_function = QComboBox()
        self.run_function.addItems(['run', 'rundcopp', 'rundcpp', 'runopp', 'runpm', 'runpm_ac_opf', 'runpm_dc_opf',
                                    'runpm_loading', 'runpm_multi_qflex', 'runpm_multi_vstab', 'runpm_ots', 'runpm_pf',
                                    'runpm_ploss', 'runpm_qflex', 'runpm_storage_opf', 'runpm_tnep', 'runpm_vstab',
                                    'runpp', 'runpp_3ph', 'runpp_pgm'])
        self.run_function.setCurrentText('run')  # Default
        layout.addWidget(self.run_function, 0, 1)

        # Choose parameter
        layout.addWidget(QLabel(self.tr("Parameter(**kwargs):")), 1, 0)
        self.parameter_dict = QLineEdit()
        #self.parameter_dict.addItems(['nr', 'iwamoto_nr', 'bfsw', 'gs', 'fdpf'])
        #self.parameter_dict.setCurrentText('nr')  # Default
        layout.addWidget(self.parameter_dict, 1, 1)

        """
        # Maximum iterations
        layout.addWidget(QLabel(self.tr("Max Iteration:")), 2, 0)
        self.max_iteration_spin = QSpinBox()
        self.max_iteration_spin.setRange(1, 1000)
        self.max_iteration_spin.setValue(10)  # Default
        layout.addWidget(self.max_iteration_spin, 2, 1)

        # Tolerance (MVA)
        layout.addWidget(QLabel(self.tr("Tolerance (MVA):")), 3, 0)
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(0.0001, 1.0)
        self.tolerance_spin.setDecimals(6)
        self.tolerance_spin.setSingleStep(0.0001)
        self.tolerance_spin.setValue(0.01)  # Default
        layout.addWidget(self.tolerance_spin, 3, 1)
        """

        # Initialization method
        layout.addWidget(QLabel(self.tr("Initialization:")), 4, 0)
        self.init_combo = QComboBox()
        self.init_combo.addItems(['auto', 'flat', 'results'])
        self.init_combo.setCurrentText('auto')  # Default
        layout.addWidget(self.init_combo, 4, 1)

        self.runpp_options_group.setLayout(layout)


    def create_advanced_options_group(self):
        """Create a group box to configure advanced options."""
        self.advanced_options_group = QGroupBox(self.tr("Advanced Options"))
        layout = QVBoxLayout()

        '''
        # Checkbox options
        self.calc_voltage_angles_cb = QCheckBox(self.tr("Calculate voltage angles"))
        self.calc_voltage_angles_cb.setChecked(True)  # Default
        layout.addWidget(self.calc_voltage_angles_cb)

        self.voltage_dependent_loads_cb = QCheckBox(self.tr("Voltage dependent loads"))
        self.voltage_dependent_loads_cb.setChecked(True)  # Default
        layout.addWidget(self.voltage_dependent_loads_cb)

        self.consider_line_temp_cb = QCheckBox(self.tr("Consider line temperature"))
        self.consider_line_temp_cb.setChecked(False)  # Default
        layout.addWidget(self.consider_line_temp_cb)

        self.distributed_slack_cb = QCheckBox(self.tr("Distributed slack"))
        self.distributed_slack_cb.setChecked(False)  # Default
        layout.addWidget(self.distributed_slack_cb)
        '''

        #separator = QFrame()
        #separator.setFrameStyle(QFrame.HLine | QFrame.Sunken)
        #layout.addWidget(separator)

        # Result visualization options
        layout.addWidget(QLabel(self.tr("Visualization Options:")))
        self.update_renderer_cb = QCheckBox(self.tr("Update layer colors after calculation"))
        self.update_renderer_cb.setChecked(True)  # Default
        layout.addWidget(self.update_renderer_cb)

        self.show_results_cb = QCheckBox(self.tr("Show detailed results in dialog"))
        self.show_results_cb.setChecked(False)  # Default
        layout.addWidget(self.show_results_cb)

        self.advanced_options_group.setLayout(layout)


    def create_progress_group(self):
        """Create a groupbox to display progress."""
        self.progress_group = QGroupBox(self.tr("Progress"))
        layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.result_text = QTextEdit()
        self.result_text.setMaximumHeight(100)
        self.result_text.setVisible(False)
        layout.addWidget(self.result_text)

        self.progress_group.setLayout(layout)


    def create_buttons(self):
        self.button_box = QDialogButtonBox()

        self.run_button = QPushButton(self.tr("Run Calculation"))
        self.run_button.setDefault(True)
        self.button_box.addButton(self.run_button, QDialogButtonBox.AcceptRole)

        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.button_box.addButton(self.cancel_button, QDialogButtonBox.RejectRole)

        # Connect signals
        #self.button_box.accepted.connect(self.accept)
        self.button_box.accepted.connect(self.start_calculation)
        self.button_box.rejected.connect(self.reject)


    def setup_network(self, uri):
        """
        Set Network informations.
        Args:
            uri (str): Network URI
        """
        self.uri = uri

        try:
            provider_metadata = QgsProviderRegistry.instance().providerMetadata("PandapowerProvider")
            uri_parts = provider_metadata.decodeUri(uri)

            self.network_data = NetworkContainer.get_network(uri)

            if not self.network_data:
                self.show_error("Failed to load network data from container")
                return

            network_type = uri_parts.get('network_type', '')
            if network_type in ['bus', 'line']:
                self.network_type = 'power'
                self.update_power_network_info()
            elif network_type in ['junction', 'pipe']:
                self.network_type = 'pipes'
                self.update_pipes_network_info()
            else:
                self.show_error(f"Unknown network type: {network_type}")
                return

            file_path = uri_parts.get('path', 'Unknown')
            self.file_path_value.setText(os.path.basename(file_path))
            self.file_path_value.setToolTip(file_path)  # Show full path as a tooltip
        except Exception as e:
            self.show_error(f"Failed to setup network: {str(e)}")


    def update_power_network_info(self):
        """Update power network information."""
        net = self.network_data['net']

        self.network_type_value.setText("Pandapower Network")
        self.bus_label.setText(self.tr("Buses: "))
        self.line_label.setText(self.tr("Lines: "))

        try:
            bus_count = len(net.bus) if hasattr(net, 'bus') else 0
            line_count = len(net.line) if hasattr(net, 'line') else 0

            self.bus_count.setText(str(bus_count))
            self.line_count.setText(str(line_count))

        except Exception as e:
            print(f"[ERROR] Error reading power network info: {str(e)}")
            self.bus_count.setText("Error")
            self.line_count.setText("Error")


    def update_pipes_network_info(self):
        """Update pipes network information."""
        net = self.network_data['net']

        self.network_type_value.setText("Pandapipes Network")
        self.bus_label.setText(self.tr("Junctions: "))
        self.line_label.setText(self.tr("Pipes: "))

        try:
            junction_count = len(net.junction) if hasattr(net, 'junction') else 0
            pipe_count = len(net.pipe) if hasattr(net, 'pipe') else 0

            self.bus_count.setText(str(junction_count))
            self.line_count.setText(str(pipe_count))
        except Exception as e:
            print(f"[ERROR] Error reading pipes network info: {str(e)}")
            self.bus_count.setText("Error")
            self.line_count.setText("Error")


    def get_parameters(self):
        """
        Return the RunPP parameters set by the user.
        Returns:
            dict: RunPP parameter dictionary
        """
        parameters = {
            'kwargs_string': self.parameter_dict.text(),
            # Default RunPP parameters
            #'algorithm': self.algorithm_combo.text(),
            #'max_iteration': self.max_iteration_spin.value(),
            #'tolerance_mva': self.tolerance_spin.value(),
            'init': self.init_combo.currentText(),
            #'calculate_voltage_angles': self.calc_voltage_angles_cb.isChecked(),
            #'voltage_dependent_loads': self.voltage_dependent_loads_cb.isChecked(),
            #'consider_line_temperature': self.consider_line_temp_cb.isChecked(),
            #'distributed_slack': self.distributed_slack_cb.isChecked(),

            # Visual options
            'update_renderer': self.update_renderer_cb.isChecked(),
            'show_results': self.show_results_cb.isChecked(),

            # Network infos
            'network_type': self.network_type
        }
        return parameters


    def start_calculation(self):
        try:
            if not self.uri:
                self.show_error("Select a network first!")
                return

            parameters = self.get_parameters()
            self.enter_calculation_mode()

            self.add_progress_message("⚡ Starting calculation...")
            QtCore.QCoreApplication.processEvents()

            import time
            time.sleep(0.5)

            self.add_progress_message("⚡ Executing power grid calculation...")
            QtCore.QCoreApplication.processEvents()

            from .ppqgis_runpp import run_network
            success, error_message = run_network(None, self.uri, parameters)

            if success:
                self.add_progress_message("✅ Calculation completed!")
                if parameters.get('update_renderer', False):
                    self.add_progress_message("🎨 Displaying results on the map...")
                    self.add_progress_message("🎨 Map color update completed!")
                time.sleep(2)
                self.calculation_success()
            else:
                self.add_progress_message("❌ Calculation failed!")
                if error_message:
                    self.add_progress_message(f"Error details: {error_message}")
                self.add_progress_message("Please check the parameters and try again.")
                self.show_error("Calculation failed: Please check the progress.")
                self.calculation_failed()

        except Exception as e:
            error_msg = f"Calculation error: {str(e)}"
            print(f"❌ {error_msg}")
            self.add_progress_message(f"❌ {error_msg}")
            self.show_error(error_msg)
            self.calculation_failed()

    def enter_calculation_mode(self):
        """Prepare the UI when starting the calculation."""
        try:
            # Change button to "calculating..." state
            self.run_button.setEnabled(False)  # Disable button
            self.run_button.setText("Calculating...")  # Change button text

            # Start progress bar
            self.progress_bar.setVisible(True)  # Make progress bar visible
            self.progress_bar.setRange(0, 0)  # Set to infinite progress bar

            # Prepare result text area
            if hasattr(self, 'result_text'):
                self.result_text.setVisible(True)  # Make text area visible
                self.result_text.clear()  # Clear previous content

        except Exception as e:
            print(f"⚠️ Calculation mode entry error: {str(e)}")

    def add_progress_message(self, message):
        """Function to notify user of progress status"""
        try:
            # Add message to text area on screen
            if hasattr(self, 'result_text'):
                # Get existing text
                current_text = self.result_text.toPlainText()

                # Add new message to existing text
                if current_text:
                    new_text = current_text + f"\n{message}"  # Add after line break
                else:
                    new_text = message  # If first message, just add

                # Display on screen
                self.result_text.setText(new_text)

                # Automatically scroll to bottom (so new message is visible)
                scrollbar = self.result_text.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(scrollbar.maximum())

        except Exception as e:
            print(f"⚠️ Message addition error: {str(e)}")


    # Check if it is actually needed
    def update_map_colors(self):
        """Function to display calculation results as colors on the map"""
        try:
            # Refresh only the entire map canvas (do not set renderer)
            from qgis.utils import iface
            if iface:
                iface.mapCanvas().refresh()
        except Exception as e:
            print(f"⚠️ Map refresh error: {str(e)}")


    def calculation_success(self):
        """Finalization process when calculation succeeds"""
        try:
            # Reset all UI to original state
            self.reset_ui()

            # Automatically close dialog after 3 seconds
            QtCore.QTimer.singleShot(3000, self.accept)

        except Exception as e:
            print(f"⚠️ Success handling error: {str(e)}")


    def calculation_failed(self):
        """Finalization process when calculation fails"""
        try:
            # Reset all UI to original state
            self.reset_ui()
        except Exception as e:
            print(f"⚠️ Failure handling error: {str(e)}")

    def reset_ui(self):
        """Function to completely reset UI to original state."""
        try:
            # Reset button to original state
            if hasattr(self, 'run_button'):
                self.run_button.setEnabled(True)
                self.run_button.setText(self.tr("Run Calculation"))

            # Clean up progress bar
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setVisible(False)
                self.progress_bar.setRange(0, 100)

            # Leave result text as is (so user can check results)
            # self.result_text.setVisible(False)  # This line is commented out!
        except Exception as e:
            print(f"⚠️ UI restoration error: {str(e)}")


    def closeEvent(self, event):
        """Function that automatically cleans up when dialog closes"""
        try:
            self.reset_ui()
            event.accept()  # Allow closing
        except Exception as e:
            print(f"⚠️ Dialog closing error: {str(e)}")
            event.accept()  # Close anyway even if error occurs

    def showEvent(self, event):
        """Function that automatically prepares when dialog opens"""
        try:
            self.reset_ui()

            if hasattr(self, 'result_text'):
                self.result_text.clear()
                self.result_text.setVisible(False)

            event.accept()  # Allow opening
        except Exception as e:
            print(f"⚠️ Dialog opening error: {str(e)}")
            event.accept()


    def show_error(self, message):
        """Display error message."""
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.critical(self, self.tr("Error"), message)


    def show_progress(self, visible=True):
        """Display or hide progress bar."""
        self.progress_bar.setVisible(visible)
        if visible:
            self.progress_bar.setRange(0, 0)  # Indeterminate progress bar


    def show_results(self, results_text):
        """Display the results as text."""
        if self.show_results_cb.isChecked():
            self.result_text.setVisible(True)
            self.result_text.setText(results_text)


    def tr(self, message):
        """Helper method for translation."""
        return QtCore.QCoreApplication.translate('ppRunDialog', message)