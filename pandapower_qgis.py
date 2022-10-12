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
import pydevd_pycharm

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QProgressBar
from qgis.core import QgsProject, QgsWkbTypes, QgsMessageLog, Qgis, QgsDistanceArea, QgsPointXY, QgsVectorLayer, \
    QgsFields, QgsField, edit, QgsFeatureRequest

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .pandapower_import_dialog import ppImportDialog
from .pandapower_export_dialog import ppExportDialog

# install requirements
import re
import sys
import pathlib
import os.path

from typing import Dict


def _add_pp_fields_(fields: QgsFields):
    strings = (QVariant.String, 'String')
    reals = (QVariant.Double, 'Real')
    types = {
        'name': strings,
        'vn_kv': reals,
        'type': strings,
        'zone': strings,
        'in_service': strings,
        'vm_pu': reals,
        'va_degree': reals,
        'p_mw': reals,
        'q_mvar': reals,
    }
    for k in types:
        if k not in fields.names():
            fields.append(QgsField(name=k, type=types[k][0], typeName=types[k][1]))
    pass


def _generate_attributes_(net) -> Dict[str, Dict[str, str or float]]:
    attr = {}
    for k in net.bus.keys():
        for ident in net.bus[k].keys():
            if ident not in attr:
                attr[str(ident)] = {'id': ident}
            attr[str(ident)][k] = net.bus[k][ident]
    for k in net.res_bus.keys():
        for ident in net.res_bus[k].keys():
            if ident not in attr:
                attr[str(ident)] = {'id': ident}
            attr[str(ident)][k] = net.res_bus[k][ident]
    return attr


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
            'ppqgis_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&pandapower QGis Plugin')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start_import = None
        self.first_start_export = None
        self.dlg_import = None
        self.dlg_export = None
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
        return QCoreApplication.translate('ppqgis', message)

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

        icon_path = ':/plugins/pandapower_qgis/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'export to pandapower'),
            callback=self.exprt,
            parent=self.iface.mainWindow())

        self.add_action(
            icon_path,
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
                self.tr(u'&pandapower QGis Plugin'),
                action)
            self.iface.removeToolBarIcon(action)

    def exprt(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start_export:
            self.first_start_export = False
            self.dlg_export = ppExportDialog()

        # get all layers
        layers = QgsProject.instance().mapLayers()
        current_crs = QgsProject.instance().crs().authid()

        # clear both comboboxes
        self.dlg_export.busComboBox.clear()
        self.dlg_export.lineComboBox.clear()

        # iterate through all layers and set up a reverse lookup table
        self.layer_id_dict = {"-": None}
        self.dlg_export.busComboBox.addItem("-")
        self.dlg_export.lineComboBox.addItem("-")

        for layer_id, layer in layers.items():
            self.dlg_export.busComboBox.addItem(layer.name())
            self.dlg_export.lineComboBox.addItem(layer.name())
            self.layer_id_dict[layer.name()] = layer_id

        # show the dialog
        self.dlg_export.show()
        # Run the dialog event loop
        result = self.dlg_export.exec_()
        # See if OK was pressed
        if result:
            self.installer_func()

            import pandapower as pp

            net = pp.create_empty_network()

            bus_layer_id = self.layer_id_dict[self.dlg_export.busComboBox.currentText()]
            line_layer_id = self.layer_id_dict[self.dlg_export.lineComboBox.currentText()]
            vn_kv = float(self.dlg_export.vnKvTextEdit.toPlainText())
            stdType = self.dlg_export.stdTypeTextEdit.toPlainText()

            bus_lookup = dict()

            if bus_layer_id:
                layer = layers[bus_layer_id]
                features = layer.getFeatures()
                for feature in features:
                    geom = feature.geometry()
                    geomSingleType = QgsWkbTypes.isSingleType(geom.wkbType())
                    if geom.type() == QgsWkbTypes.GeometryType.PointGeometry:
                        if geomSingleType:
                            x = geom.asPoint()
                            # QgsMessageLog.logMessage("Point: X: " + str(x.x()) + ", Y: " + str(x.y()),
                            #                         level=Qgis.MessageLevel.Info)
                            id = pp.create_bus(net, geodata=(x.x(), x.y()), vn_kv=vn_kv)
                            bus_lookup[x] = id

            if line_layer_id:
                layer = layers[line_layer_id]
                features = layer.getFeatures()
                for feature in features:
                    geom = feature.geometry()
                    geomSingleType = QgsWkbTypes.isSingleType(geom.wkbType())
                    if geom.type() == QgsWkbTypes.GeometryType.LineGeometry:
                        if geomSingleType:
                            x = geom.asPolyline()
                            QgsMessageLog.logMessage("Line: " + str(x), level=Qgis.MessageLevel.Info)
                        else:
                            # x = geom.asMultiPolyline()
                            # x = geom.asPolyline()

                            d = QgsDistanceArea()
                            d.setEllipsoid(current_crs)
                            for part in geom.parts():
                                # for point in part.points():
                                #     res += "[" + str(point.x()) + ", " + str(point.y()) + "]"
                                frst = part.points()[0]
                                last = part.points()[-1]
                                distance_first = sys.float_info.max
                                distance_last = sys.float_info.max
                                bus_found_first = -1
                                bus_found_last = -1
                                for bus in bus_lookup.keys():
                                    m = d.measureLine([QgsPointXY(frst), bus])
                                    if m < distance_first:
                                        distance_first = m
                                        bus_found_first = bus_lookup[bus]

                                    m = d.measureLine([QgsPointXY(last), bus])

                                    if m < distance_last:
                                        distance_last = m
                                        bus_found_last = bus_lookup[bus]

                                if bus_found_first != 1 and bus_found_last != 1:
                                    # length = d.measureLine(QgsPointXY(part.points()))
                                    geo = []
                                    for point in part.points():
                                        geo.append([point.x(), point.y()])
                                    pp.create_line(net,
                                                   from_bus=bus_found_first,
                                                   to_bus=bus_found_last,
                                                   std_type=stdType,
                                                   length_km=part.length() / 1000.,
                                                   geodata=geo)
                                    # QgsMessageLog.logMessage("Line from {0} to {1}".format(bus_found_first, bus_found_last),
                                    #                         level=Qgis.MessageLevel.Info)

            filters = "pandapower networks (*.json)"
            selected = "pandapower networks (*.json)"
            file = QFileDialog.getSaveFileName(None, "File Dialog", self.dir, filters, selected)[0]
            if file:
                pp.to_json(net, file)

    def imprt(self):
        """Run method that performs all the real work"""
        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start_import:
            self.first_start_import = False
            self.dlg_import = ppImportDialog()

        dlg = QFileDialog()
        # dlg.setFileMode(QFileDialog.AnyFile)
        dlg.setNameFilter("pandapower networks (*.json)")
        dlg.selectNameFilter("pandapower networks (*.json)")

        filters = "pandapower networks (*.json)"
        selected = "pandapower networks (*.json)"
        file = QFileDialog.getOpenFileName(None, "File Dialog", self.dir, filters, selected)[0]

        pydevd_pycharm.settrace('localhost', port=34117, stdoutToServer=True, stderrToServer=True)

        if file:
            self.installer_func()
            import pandapower as pp
            # import pandapower.networks as networks
            import pandapower.plotting.geo as geo
            net = pp.from_json(file)
            # net = networks.mv_oberrhein()
            # pp.plotting.plotly.geo_data_to_latlong(net, "epsg:31467")  # convert to wgs84
            geo.convert_geodata_to_gis(net)  # for valid geojson, net needs geo info in wgs84

            self.dlg_import.BusLabel.setText("#Bus: " + str(len(net.bus)))
            self.dlg_import.LineLabel.setText("#Lines: " + str(len(net.line)))
            # show the dialog
            self.dlg_import.show()
            # Run the dialog event loop
            result = self.dlg_import.exec_()
            # See if OK was pressed
            if result:
                layer_name = self.dlg_import.layerNameEdit.toPlainText()
                # Do something useful here - delete the line containing pass and
                # substitute with your code.
                root = QgsProject.instance().layerTreeRoot()
                group = root.findGroup(layer_name)
                if group is None:
                    group = root.addGroup(layer_name)
                bus_geodata = net["bus_geodata"]
                line_geodata = net["line_geodata"]
                bus_layer = QgsVectorLayer(bus_geodata.to_json(na='drop'), layer_name + "_bus", "ogr")
                line_layer = QgsVectorLayer(line_geodata.to_json(na='drop'), layer_name + "_line", "ogr")
                QgsProject.instance().addMapLayer(bus_layer, False)
                QgsProject.instance().addMapLayer(line_layer, False)
                group.addLayer(bus_layer)
                group.addLayer(line_layer)
                # Move layers above TileLayer
                root.setHasCustomLayerOrder(True)
                order = root.customLayerOrder()
                order.insert(0, order.pop())
                order.insert(0, order.pop())
                root.setCustomLayerOrder(order)

                # create fields for bus attributes
                fields = bus_layer.fields()
                _add_pp_fields_(fields=fields)

                # get new attributes from pp network
                attr = _generate_attributes_(net)
                features = bus_layer.getFeatures()
                changes = {}
                for f in features:
                    ind = f.attribute('id')
                    if int(ind) in attr:
                        changes[f.id] = attr[int(ind)]
                    f.setFields(fields)
                bus_layer.startEditing()
                bus_layer.dataProvider().changeAttributeValues(changes)
                bus_layer.commitChanges()

                """
                bus_values = net.bus.keys()
                for name in bus_values:
                    ids = net.bus[name].keys()
                    for ind in ids:
                        if ind not in changes:
                            changes[ind] = {}
                        changes[ind][name] = net.bus[name][ind]
                res_bus_values = net.res_bus.keys()
                for name in res_bus_values:
                    ids = net.res_bus[name].keys()
                    for ind in ids:
                        if ind not in changes:
                            changes[ind] = {}
                        changes[ind][name] = net.res_bus[name][ind]
                bus_layer.startEditing()
                bus_layer.changeAttributeValues(changes)
                bus_layer.commitChanges(stopEditing=True)
                """
                """
                # FIXME: Max rec depth exceeded in this for
                # Add info to all bus features
                features = bus_layer.getFeatures()
                for feature in features:
                    ppid = int(feature.attribute("id"))
                    feature.setFields(fields)
                    feature['name'] = net.bus.name.get(ppid)
                    feature['vn_kv'] = net.bus.vn_kv.get(ppid)
                    feature['type'] = net.bus.type.get(ppid)
                    feature['zone'] = net.bus.zone.get(ppid)
                    feature['in_service'] = net.bus.in_service.get(ppid)
                    feature['vm_pu'] = net.res_bus.vm_pu.get(ppid)
                    feature['va_degree'] = net.res_bus.va_degree.get(ppid)
                    feature['p_mw'] = net.res_bus.p_mw.get(ppid)
                    feature['q_mvar'] = net.res_bus.q_mvar.get(ppid)

                """
                """
                # create fields for line attributes
                fields = line_layer.fields()
                for k in net.line.keys():
                    fields.append(QgsField(name=k))
                for k in net.res_line.keys():
                    fields.append(QgsField(name=k))

                # Add info to all line features
                features = line_layer.getFeatures()
                for feature in features:
                    ppid = int(feature.attribute("id"))
                    feature.setFields(fields)
                    for k in net.line.keys():
                        feature[k] = net.line[k].get(ppid)
                    for k in net.res_line.keys():
                        feature[k] = net.res_line[k].get(ppid)"""
