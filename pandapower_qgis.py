# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ppqgis
                                 A QGIS plugin
 Plugin to work with pandapower networks
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2022-09-23
        git sha              : $Format:%H$
        copyright            : (C) 2022 by Fraunhofer IEE
        email                : mike.vogt@iee.fraunhofer.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import numpy

"""
    For Windows Users:
        this plugin requires geopandas, please make sure you have its dependencies (fiona) installed
        
"""
# TODO: Write a try for geopandas import and error out without crashing

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QListWidgetItem, QTreeWidgetItem
from qgis.core import QgsProject, QgsWkbTypes, QgsMessageLog, Qgis, NULL
from qgis.gui import QgsMessageBar

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .pandapower_import_dialog import ppImportDialog
from .pandapower_export_dialog import ppExportDialog
from .pandapower_export_summary_dialog import ppExportSummaryDialog

# install requirements
import re
import sys
import pathlib
import os.path

from typing import List

# suppress a warning from the pyproj4 package
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

class ppqgis:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'pandapower_qgis_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&pandapower QGIS Plugin')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start_import = None
        self.first_start_export = None
        self.dlg_import = None
        self.dlg_export = None
        self.dlg_export_summary = None
        self.dir = None
        self.layer_id_dict = None

    def installer_func(self):
        plugin_dir = os.path.dirname(os.path.realpath(__file__))

        try:
            import pip
        except ImportError:
            QgsMessageLog.logMessage("pip missing, trying to install/update pip.",
                                     level=Qgis.MessageLevel.Info)
            exec(open(str(pathlib.Path(plugin_dir, 'scripts', 'get_pip.py'))).read())
            import pip
            import subprocess
            # just in case the included version is old
            # pip.main(['install', '--upgrade', 'pip'])
            subprocess.check_call(["pip", "install", "--upgrade", "pip"])

        sys.path.append(plugin_dir)

        with open(os.path.join(plugin_dir, 'requirements.txt'), "r") as requirements:
            for dep in requirements.readlines():
                # part string at any ==, ~=, <=, >=
                dep = re.split("[~=<>]=", dep.strip(), 1)[0]
                try:
                    __import__(dep)
                    QgsMessageLog.logMessage("Trying to load {}".format(dep), level=Qgis.MessageLevel.Info)
                except ImportError as e:
                    import subprocess
                    QgsMessageLog.logMessage("{} not available, installing".format(dep),
                                             level=Qgis.MessageLevel.Warning)
                    subprocess.check_call(["pip", "install", dep])

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('pandapower_qgis', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/pandapower_qgis/pp.svg'
        import_icon_path = ':/plugins/pandapower_qgis/pp_import.svg'
        export_icon_path = ':/plugins/pandapower_qgis/pp_export.svg'

        self.add_action(
            icon_path=export_icon_path,
            text=self.tr(u'export to pandapower'),
            callback=self.exprt,
            parent=self.iface.mainWindow())

        self.add_action(
            icon_path=import_icon_path,
            text=self.tr(u'import from pandapower'),
            callback=self.imprt,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start_import = True
        self.first_start_export = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&pandapower QGIS Plugin'),
                action)
            self.iface.removeToolBarIcon(action)

    def exprt(self):
        """Run method that performs all the real work"""
        """
        Information collected and displayed after export:
            amount bus
            amount lines
            amount lines using derived length
            amount lines containing errors
            used std_type's
        """

        from .ppqgis_export import power_network, pipes_network
        initial_run = False

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start_export:
            self.first_start_export = False
            self.dlg_export = ppExportDialog()
            self.dlg_export_summary = ppExportSummaryDialog()

        # get all layers
        layers = QgsProject.instance().mapLayers()

        tree_widget = self.dlg_export.layerTreeWidget

        # clear tree of all items
        tree_widget.clear()

        # Generate Tristate Group item for layers
        layer_item = QTreeWidgetItem(tree_widget)
        layer_item.setText(0, self.tr("layers"))
        layer_item.setFlags(layer_item.flags() | QtCore.Qt.ItemIsTristate | QtCore.Qt.ItemIsUserCheckable)
        layer_item.setExpanded(True)
        tree_widget.addTopLevelItem(layer_item)

        layer_lookup = {}

        for layer in layers:
            name = layers[layer].name()
            # add layer item with checkbox to treeWidget
            tree_item = QTreeWidgetItem(layer_item)
            tree_item.setText(0, name)
            tree_item.setFlags(tree_item.flags() | QtCore.Qt.ItemIsUserCheckable)
            tree_item.setCheckState(0, QtCore.Qt.CheckState.Checked)
            layer_item.addChild(tree_item)
            item_index = layer_item.indexOfChild(tree_item)

            # Make item name clickable. (as opposed to checkbox only)
            # If using itemClicked checkbox becomes unresponsive
            tree_widget.itemPressed.connect(
                lambda item: item.setCheckState(0,
                    QtCore.Qt.CheckState.Checked
                    if item.checkState(0) == QtCore.Qt.CheckState.Unchecked
                    else QtCore.Qt.CheckState.Unchecked
                )
            )

            layer_lookup[item_index] = layer

        # show the dialog
        self.dlg_export.show()
        # Run the dialog event loop
        result = self.dlg_export.exec_()
        # See if OK was pressed
        if result:
            # get selected layers
            selected_layers = list()
            for ind in range(layer_item.childCount()):
                if layer_item.child(ind).checkState(0) == QtCore.Qt.CheckState.Checked:
                    selected_layers.append(layer_lookup[ind])

            self.installer_func()

            if self.dlg_export.power:
                power_network(self, selected_layers)
            else:
                pipes_network(self, selected_layers)


    def imprt(self):
        """Run method that performs all the real work"""
        from .ppqgis_import import power_network, pipes_network

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start_import:
            self.first_start_import = False
            self.dlg_import = ppImportDialog()

        # Open file dialog showing json files and directories
        filters = "all files ();;json files (*.json)"
        selected = "json files (*.json)"
        filename = QFileDialog.getOpenFileName(
            None,
            self.tr("Import pandapower or pandapipes network - Open File"),
            self.dir,
            filters,
            selected)[0]

        if filename:
            self.installer_func()

            with open(filename, 'r') as file:
                content = file.read()
                if '"pandapowerNet"' in content:
                    power_network(self, filename)
                elif '"pandapipesNet"' in content:
                    pipes_network(self, filename)
                else:
                    self.iface.messageBar().pushMessage(
                        'The selected json file could not be loaded. Could not find "pandapowerNet" or "pandapipesNet"',
                        level=Qgis.Critical
                    )
