# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ppqgis_export

 module for exporting pandapower or pandapipes networks to qgis

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

from qgis.PyQt.QtWidgets import QAction, QFileDialog, QListWidgetItem, QTreeWidgetItem, QPushButton, QDockWidget
from qgis.core import QgsProject, QgsWkbTypes, QgsMessageLog, Qgis, NULL
from .network_container import NetworkContainer

from typing import List
import copy


def get_original_network_from_container(selected_layers):
    """
    Retrieve the original pandapower/pandapipes network from NetworkContainer.
    Args:
        selected_layers: List of selected layer names
    Returns:
        The original network object if found, None otherwise
    """
    layers = QgsProject.instance().mapLayers()

    for layer_name in selected_layers:
        if layer_name not in layers:
            continue
        layer = layers[layer_name]

        # Check if layer has a data provider
        if not hasattr(layer, 'dataProvider'):
            continue
        provider = layer.dataProvider()

        # Check if this is a PandapowerProvider layer
        if provider.name() == "PandapowerProvider":
            uri = provider.dataSourceUri()
            network_data = NetworkContainer.get_network(uri)

            if network_data and 'net' in network_data:
                QgsMessageLog.logMessage(
                    f"Found original network from layer: {layer_name}",
                    level=Qgis.Info
                )
                return network_data['net']

    return None


def power_network(parent, selected_layers) -> None:
    """
    Export pandapower network to JSON file.

    This function now uses a lossless export approach:
    1. Retrieves the original complete network from NetworkContainer
    2. Preserves all components (ext_grid, load, gen, trafo, etc.)
    3. Saves the complete network to JSON

    Args:
        parent: Parent plugin object
        selected_layers: List of selected layer names to export
    """
    # Try to get the original network from NetworkContainer
    original_net = get_original_network_from_container(selected_layers)

    if original_net is None:
        QgsMessageLog.logMessage(
            "Could not find original network. "
            "Export only works for networks that were imported using the import function.",
            level=Qgis.Warning
        )
        parent.iface.messageBar().pushMessage(
            "Export Error",
            "Could not find original network. Only imported networks can be exported. "
            "Please import a network first.",
            level=Qgis.Warning,
            duration=10
        )
        return

    import pandapower as pp

    # Show file save dialog
    filters = "pandapower networks (*.json)"
    selected = "pandapower networks (*.json)"
    file = QFileDialog.getSaveFileName(None, "Save Network", parent.dir, filters, selected)[0]

    if not file:
        QgsMessageLog.logMessage("Export cancelled by user", level=Qgis.Info)
        return

    try:
        # Create a deep copy of the original network to avoid modifying it
        # QgsMessageLog.logMessage("Creating deep copy of network...", level=Qgis.Info)
        net = copy.deepcopy(original_net)

        # Save the complete network to JSON
        # QgsMessageLog.logMessage(f"Saving network to: {file}", level=Qgis.Info)
        pp.to_json(net, file)

        # Prepare export summary
        bus_count = len(net.bus) if hasattr(net, 'bus') else 0
        line_count = len(net.line) if hasattr(net, 'line') else 0
        ext_grid_count = len(net.ext_grid) if hasattr(net, 'ext_grid') else 0
        load_count = len(net.load) if hasattr(net, 'load') else 0
        gen_count = len(net.gen) if hasattr(net, 'gen') else 0
        trafo_count = len(net.trafo) if hasattr(net, 'trafo') else 0

        # Collect standard types
        exported_std_types = []
        if hasattr(net, 'std_types') and 'line' in net.std_types:
            exported_std_types = list(net.std_types['line'].keys())

        # Display export summary
        parent.dlg_export_summary.exportedBus.setText(f'Buses exported: {bus_count}')
        parent.dlg_export_summary.exportedLines.setText(f'Lines exported: {line_count}')
        parent.dlg_export_summary.erroredLines.setText(
            f'Additional components: ext_grid({ext_grid_count}), '
            f'load({load_count}), gen({gen_count}), trafo({trafo_count})'
        )
        parent.dlg_export_summary.stdTypeList.clear()
        parent.dlg_export_summary.stdTypeList.addItems(exported_std_types)
        parent.dlg_export_summary.show()

        QgsMessageLog.logMessage(
            f"Export successful! Total components preserved: "
            f"bus({bus_count}), line({line_count}), ext_grid({ext_grid_count}), "
            f"load({load_count}), gen({gen_count}), trafo({trafo_count})",
            level=Qgis.Success
        )

        parent.iface.messageBar().pushMessage(
            "Export Successful",
            f"Network exported to {file} with all components preserved.",
            level=Qgis.Success,
            duration=5
        )

    except Exception as e:
        error_msg = f"Error during export: {str(e)}"
        QgsMessageLog.logMessage(error_msg, level=Qgis.Critical)
        parent.iface.messageBar().pushMessage(
            "Export Failed",
            error_msg,
            level=Qgis.Critical,
            duration=10
        )
        import traceback
        traceback.print_exc()


def pipes_network(parent, selected_layers) -> None:
    """
    Export pandapipes network to JSON file.

    Note: Currently unchanged - keeping original implementation.
    TODO: Apply the same lossless export approach as power_network.
    """
    # get all layers
    layers = QgsProject.instance().mapLayers()

    # variables for summary:
    junction_count: int = 0
    pipe_count: int = 0
    pipe_len_count: int = 0
    pipe_error_count: int = 0

    # variables required for new network
    name = parent.dlg_export.nameEdit.text()
    fluid_name = parent.dlg_export.fluidLineEdit.text()
    add_stdtypes = parent.dlg_export.addStdTypes.isChecked()

    import pandapipes as pp

    filters = "pandapipes networks (*.json)"
    selected = "pandapipes networks (*.json)"
    file = QFileDialog.getSaveFileName(None, "File Dialog", parent.dir, filters, selected)[0]
    if not file:
        return

    try:
        # create empty network
        net = pp.create_empty_network(name, fluid_name, add_stdtypes)
    except AttributeError:
        net = pp.create_empty_network(name, None, add_stdtypes)

    # create a bus_lookup table
    junction_id_lookup = dict()
    pipe_layers = list()
    for layer_name in selected_layers:
        selectIds = list()
        layer = layers[layer_name]
        if not hasattr(layer, "getFeatures"):
            continue
        # get all fields of layer
        field_names = layer.fields().names()

        features = layer.getFeatures()
        for feature in features:
            if 'pp_type' not in field_names:
                selectIds.append(feature.id())
                continue
            pp_type = feature['pp_type']
            if pp_type not in ['junction', 'pipe']:
                selectIds.append(feature.id())
                continue
            if pp_type == 'junction':
                """
                Required properties:
                    net: pandapipesNet
                    pn_bar: float
                    tfluid_k: float
                Optional properties:
                    height_m: float
                    name: str
                    pp_index: int
                    in_service: bool
                """
                required = {
                    "pn_bar": None,
                    "tfluid_k": None,
                }
                props = {
                    "height_m": 0,
                    "name": None,
                    "pp_index": None,
                    "in_service": True,
                    "type": "junction",
                    "geodata": None,
                }
                # Get optional properties if they exist
                for key in props:
                    if key in field_names and feature[key] is not NULL:
                        props[key] = feature[key]

                geom = feature.geometry()
                if geom.type() == QgsWkbTypes.GeometryType.PointGeometry:
                    assert QgsWkbTypes.isSingleType(geom.wkbType())
                    geometry = geom.asPoint()
                    # QgsMessageLog.logMessage("Point: X: " + str(geometry.x()) + ", Y: " + str(geometry.y()),
                    #                         level=Qgis.MessageLevel.Info)
                    props['geodata'] = (geometry.x(), geometry.y())
                elif geom.type() == QgsWkbTypes.GeometryType.LineGeometry:
                    assert QgsWkbTypes.isSingleType(geom.wkbType())
                    geometry = geom.asPolyline()
                    if len(geometry) > 2:
                        # bus does not support full LineStrings only start and end points
                        selectIds.append(feature.id())
                        continue
                    props['coords'] = [(geometry[0].x(), geometry[0].y()), (geometry[1].x(), geometry[1].y())]
                else:
                    selectIds.append(feature.id())
                    continue
                try:
                    bid = pp.create_junction(net,
                                             pn_bar=required['pn_bar'],
                                             tfluid_k=required['tfluid_k'],
                                             height_m=props['height_m'],
                                             name=props['name'],
                                             index=props['pp_index'],
                                             in_service=props['in_service'],
                                             type=props['type'],
                                             geodata=props['geodata'])
                except UserWarning:
                    bid = pp.create_junction(net,
                                             pn_bar=props['pn_bar'],
                                             tfluid_k=props['tfluid_k'],
                                             height_m=props['height_m'],
                                             name=props['name'],
                                             index=None,
                                             in_service=props['in_service'],
                                             type=props['type'],
                                             geodata=props['geodata'])
                junction_count += 1
                if props['pp_index'] not in junction_id_lookup:
                    junction_id_lookup[props['pp_index']] = bid
                else:
                    QgsMessageLog.logMessage(
                        f'pp_index "{props["pp_index"]}" double assigned! FeatureID: {feature.id()}',
                        level=Qgis.MessageLevel.Warning)

            if pp_type == 'pipe' and layer_name not in pipe_layers:
                pipe_layers.append(layer_name)
    for layer_name in pipe_layers:
        selectIds = list()
        layer = layers[layer_name]
        if not hasattr(layer, "getFeatures"):
            continue
        # get all fields of layer
        field_names = layer.fields().names()

        features = layer.getFeatures()
        for feature in features:
            if 'pp_type' not in field_names:
                selectIds.append(feature.id())
                continue
            pp_type = feature['pp_type']
            if pp_type != 'pipe':
                selectIds.append(feature.id())
                continue
            """
            Required properties:
                from_junction
                to_junction
                length_km (if not set derivable from geometry)
                diameter_m
            Optional properties:
                k_mm: float
                loss_coefficient: float
                sections: int
                alpha_w_per_m2k: float
                qext_w: float
                text_k: float
                name: str
                index: int
                geodata: [tuple]
                in_service: bool
                type: str
                std_type: str
            """
            required = {
                "from_junction": None,
                "to_junction": None,
                "diameter_m": None,
            }
            optional = {
                "length_km": None,  # is required, will be fetched from geometry, thus moved to optional
                "k_mm": 1.,
                "loss_coefficient": .0,
                "sections": 1,
                "alpha_w_per_m2k": .0,
                "qext_w": .0,
                "text_k": 293,
                "name": None,
                "pp_index": None,
                "geodata": None,
                "in_service": True,
                "type": "pipe",
                "std_type": None
            }
            uses_derived_length = False
            # Get optional properties if they exist
            for key in required:
                if key not in field_names or feature[key] == NULL:
                    selectIds.append(feature.id())
                    pipe_error_count += 1
                    continue
                assert key in field_names
                assert feature[key] != NULL
                required[key] = feature[key]

            for key in optional:
                if key in field_names and feature[key] != NULL:
                    optional[key] = feature[key]
                # assert optional[key] != NULL  # This assertion fails for None
            geom = feature.geometry()
            # set length_km if it hadn't been provided
            if optional['length_km'] is None:
                optional['length_km'] = geom.length()
                uses_derived_length = True
            if geom.type() == QgsWkbTypes.GeometryType.LineGeometry:
                assert QgsWkbTypes.isSingleType(geom.wkbType())
                c = geom.asPolyline()  # c = list[QgsPointXY]
                # QgsMessageLog.logMessage("Line: " + str(x), level=Qgis.MessageLevel.Info)

                # lookup from_bus/to_bus
                from_junction = None
                to_junction = None
                if required['from_junction'] in junction_id_lookup:
                    from_junction = junction_id_lookup[required['from_junction']]
                if required['to_junction'] in junction_id_lookup:
                    to_junction = junction_id_lookup[required['to_junction']]

                if from_junction is None or to_junction is None:
                    QgsMessageLog.logMessage(
                        f'Could not find from_junction {required["from_junction"]} or to_junction {required["to_junction"]} for {feature.id()}',
                        level=Qgis.MessageLevel.Warning)
                    selectIds.append(feature.id())
                    pipe_error_count += 1
                    continue
                geo = []
                for point in c:
                    geo.append((point.x(), point.y()))
                if len(geo) > 0:
                    optional['geodata'] = geo
                if optional["std_type"] is None or optional["std_type"] == "None":
                    try:
                        pp.create_pipe_from_parameters(
                            net,
                            from_junction=from_junction,
                            to_junction=to_junction,
                            length_km=optional['length_km'],
                            diameter_m=required['diameter_m'],
                            k_mm=optional['k_mm'],
                            loss_coefficient=optional['loss_coefficient'],
                            sections=optional['sections'],
                            alpha_w_per_m2k=optional['alpha_w_per_m2k'],
                            qext_w=optional['qext_w'],
                            text_k=optional['text_k'],
                            name=optional['name'],
                            index=optional['pp_index'],
                            geodata=optional['geodata'],
                            in_service=optional['in_service'],
                            type=optional['type'])
                    except UserWarning:
                        pp.create_pipe_from_parameters(
                            net,
                            from_junction=from_junction,
                            to_junction=to_junction,
                            length_km=optional['length_km'],
                            diameter_m=required['diameter_m'],
                            k_mm=optional['k_mm'],
                            loss_coefficient=optional['loss_coefficient'],
                            sections=optional['sections'],
                            alpha_w_per_m2k=optional['alpha_w_per_m2k'],
                            qext_w=optional['qext_w'],
                            text_k=optional['text_k'],
                            name=optional['name'],
                            index=None,
                            geodata=optional['geodata'],
                            in_service=optional['in_service'],
                            type=optional['type'])
                else:
                    try:
                        pp.create_pipe(
                            net,
                            from_junction=from_junction,
                            to_junction=to_junction,
                            std_type=optional['std_type'],
                            length_km=optional['length_km'],
                            k_mm=optional['k_mm'],
                            loss_coefficient=optional['loss_coefficient'],
                            sections=optional['sections'],
                            alpha_w_per_m2k=optional['alpha_w_per_m2k'],
                            text_k=optional['text_k'],
                            qext_w=optional['qext_w'],
                            name=optional['name'],
                            index=optional['pp_index'],
                            geodata=optional['geodata'],
                            in_service=optional['in_service'],
                            type=optional['type'])
                    except UserWarning:
                        pp.create_pipe(
                            net,
                            from_junction=from_junction,
                            to_junction=to_junction,
                            std_type=optional['std_type'],
                            length_km=optional['length_km'],
                            k_mm=optional['k_mm'],
                            loss_coefficient=optional['loss_coefficient'],
                            sections=optional['sections'],
                            alpha_w_per_m2k=optional['alpha_w_per_m2k'],
                            text_k=optional['text_k'],
                            qext_w=optional['qext_w'],
                            name=optional['name'],
                            index=None,
                            geodata=optional['geodata'],
                            in_service=optional['in_service'],
                            type=optional['type'])

                pipe_count += 1
                if uses_derived_length:
                    pipe_len_count += 1
                # QgsMessageLog.logMessage("Line from {0} to {1}".format(bus_found_first, bus_found_last),
                #                         level=Qgis.MessageLevel.Info)

            layer.selectByIds(selectIds, Qgis.SelectBehavior.AddToSelection)

    if file:
        pp.to_json(net, file)

    # Display export summary
    parent.dlg_export_summary.exportedBus.setText(parent.tr(f'Buses exported: {junction_count}'))
    parent.dlg_export_summary.exportedLines.setText(parent.tr(f'Pipes exported: {pipe_count} ({pipe_len_count})'))
    parent.dlg_export_summary.erroredLines.setText(parent.tr(f'Pipes containing errors: {pipe_error_count}'))
    parent.dlg_export_summary.stdTypeLabel.setVisible(False)
    parent.dlg_export_summary.stdTypeList.setVisible(False)
    parent.dlg_export_summary.show()
