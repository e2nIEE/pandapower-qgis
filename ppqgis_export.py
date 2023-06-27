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

from qgis.PyQt.QtWidgets import QAction, QFileDialog, QListWidgetItem, QTreeWidgetItem
from qgis.core import QgsProject, QgsWkbTypes, QgsMessageLog, Qgis, NULL

from typing import List

def power_network(parent, selected_layers) -> None:

    # get all layers
    layers = QgsProject.instance().mapLayers()

    # variables for summary:
    bus_count: int = 0
    line_count: int = 0
    line_len_count: int = 0
    line_error_count: int = 0
    exported_std_types: List[str] = list()

    # variables required for new network
    name = parent.dlg_export.nameEdit.text()
    try:
        f_hz = float(parent.dlg_export.frequencyEdit.text())
    except ValueError:
        f_hz = 50
    try:
        sn_mva = float(parent.dlg_export.refApparentPowerEdit.text())
    except ValueError:
        sn_mva = 1
    add_stdtypes = parent.dlg_export.addStdTypes.isChecked()

    import pandapower as pp

    filters = "pandapower networks (*.json)"
    selected = "pandapower networks (*.json)"
    file = QFileDialog.getSaveFileName(None, "File Dialog", parent.dir, filters, selected)[0]
    if not file:
        return

    # create empty network
    net = pp.create_empty_network(name, f_hz, sn_mva, add_stdtypes)

    # create a bus_lookup table
    bus_id_lookup = dict()
    line_layers = list()
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
            if pp_type not in ['bus', 'line']:
                selectIds.append(feature.id())
                continue
            if pp_type == 'bus':
                """
                Optional properties:
                    name: str
                    pp_index: int
                    vn_kv: float
                    type: str "b", "n", "m"
                    zone: str, None
                    in_service: bool
                    max_vm_pu: float, NAN
                    min_vm_pu: float, NAN
                """
                props = {
                    "name": None,
                    "pp_index": None,
                    # "vn_kv": ?  # no default given.
                    "geodata": None,
                    "type": "b",
                    "zone": None,
                    "in_service": True,
                    "max_vm_pu": float("NaN"),
                    "min_vm_pu": float("NaN"),
                    "coords": None,
                }
                # Get optional properties if they exist
                for key in props:
                    if key in field_names and feature[key] is not NULL:
                        props[key] = feature[key]
                if 'vn_kv' in field_names and feature['vn_kv'] is not NULL:
                    props['vn_kv'] = feature['vn_kv']
                else:  # not sure if this is the way to handle missing vn_kv
                    selectIds.append(feature.id())
                    continue

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
                    bid = pp.create_bus(net,
                                        name=props['name'],
                                        index=props['pp_index'],
                                        vn_kv=props['vn_kv'],
                                        geodata=props['geodata'],
                                        type=props['type'],
                                        zone=props['zone'],
                                        in_service=props['in_service'],
                                        max_vm_pu=props['max_vm_pu'],
                                        min_vm_pu=props['min_vm_pu'],
                                        coords=props['coords'])
                except UserWarning:
                    bid = pp.create_bus(net,
                                        name=props['name'],
                                        index=None,
                                        vn_kv=props['vn_kv'],
                                        geodata=props['geodata'],
                                        type=props['type'],
                                        zone=props['zone'],
                                        in_service=props['in_service'],
                                        max_vm_pu=props['max_vm_pu'],
                                        min_vm_pu=props['min_vm_pu'],
                                        coords=props['coords'])
                bus_count += 1
                if props['pp_index'] not in bus_id_lookup:
                    bus_id_lookup[props['pp_index']] = bid
                else:
                    QgsMessageLog.logMessage(
                        f'pp_index "{props["pp_index"]}" double assigned! FeatureID: {feature.id()}',
                        level=Qgis.MessageLevel.Warning)

            if pp_type == 'line' and layer_name not in line_layers:
                line_layers.append(layer_name)
    for layer_name in line_layers:
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
            if pp_type != 'line':
                selectIds.append(feature.id())
                continue
            """
            Required properties:
                from_bus
                to_bus
                length_km (if not set derivable from geometry)
                std_type (if not a std_type in pp create it: net.create_std_type())
            Optional properties:
                name: str
                index: int
                geodata: [tuple]
                in_service: bool
                df: float (derating factor)
                parallel: int
                max_loading_percent: float
            """
            required = {
                "from_bus": None,
                "to_bus": None,
                "std_type": None,
            }
            optional = {
                "length_km": None,  # is required, will be fetched from geometry, thus moved to optional
                "name": None,
                "pp_index": None,
                "geodata": None,
                "in_service": True,
                "df": 1.0,
                "parallel": 1,
                "max_loading_percent": float("NaN"),
            }
            uses_derived_length = False
            # Get optional properties if they exist
            for key in required:
                if key not in field_names or feature[key] == NULL:
                    selectIds.append(feature.id())
                    line_error_count += 1
                    continue
                assert key in field_names
                assert feature[key] != NULL
                required[key] = feature[key]

            # check if std_type exists in pp
            if not pp.std_type_exists(net, required["std_type"]):
                # TODO: fill std_type data somehow
                #  This data object is only an example and needs replacing!
                data = {
                    "r_ohm_per_km": 0.2,
                    "x_ohm_per_km": 0.07,
                    "c_nf_per_km": 1160.0,
                    "max_i_ka": 0.4,
                    "endtemp_degree": 70.0,
                    "r0_ohm_per_km": 0.8,
                    "x0_ohm_per_km": 0.3,
                    "c0_nf_per_km": 500.0
                }
                pp.create_std_type(net, data=data, name=required['std_type'])
            # track exported std types
            if required['std_type'] not in exported_std_types:
                exported_std_types.append(required['std_type'])

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
                # assert QgsWkbTypes.isSingleType(geom.wkbType())
                try:
                    c = geom.asPolyline()  # c = list[QgsPointXY]
                except TypeError:
                    c = geom.asMultiPolyline()[0]
                # QgsMessageLog.logMessage("Line: " + str(x), level=Qgis.MessageLevel.Info)

                # lookup from_bus/to_bus
                from_bus = None
                to_bus = None
                if required['from_bus'] in bus_id_lookup:
                    from_bus = bus_id_lookup[required['from_bus']]
                if required['to_bus'] in bus_id_lookup:
                    to_bus = bus_id_lookup[required['to_bus']]

                if from_bus is None or to_bus is None:
                    QgsMessageLog.logMessage(
                        f'Could not find from_bus {required["from_bus"]} or to_bus {required["to_bus"]} for {feature.id()}',
                        level=Qgis.MessageLevel.Warning)
                    selectIds.append(feature.id())
                    line_error_count += 1
                    continue
                geo = []
                for point in c:
                    geo.append((point.x(), point.y()))
                if len(geo) > 0:
                    optional['geodata'] = geo
                try:
                    pp.create_line(net,
                                   from_bus=from_bus,
                                   to_bus=to_bus,
                                   length_km=optional['length_km'],
                                   std_type=required['std_type'],
                                   name=optional['name'],
                                   index=optional['pp_index'],
                                   geodata=optional['geodata'],
                                   in_service=optional['in_service'],
                                   df=optional['df'],
                                   parallel=optional['parallel'],
                                   max_loading_percent=optional['max_loading_percent'])
                except UserWarning:
                    pp.create_line(net,
                                   from_bus=from_bus,
                                   to_bus=to_bus,
                                   length_km=optional['length_km'],
                                   std_type=required['std_type'],
                                   name=optional['name'],
                                   index=None,
                                   geodata=optional['geodata'],
                                   in_service=optional['in_service'],
                                   df=optional['df'],
                                   parallel=optional['parallel'],
                                   max_loading_percent=optional['max_loading_percent'])

                line_count += 1
                if uses_derived_length:
                    line_len_count += 1
                # QgsMessageLog.logMessage("Line from {0} to {1}".format(bus_found_first, bus_found_last),
                #                         level=Qgis.MessageLevel.Info)

            layer.selectByIds(selectIds, Qgis.SelectBehavior.AddToSelection)

    if file:
        pp.to_json(net, file)

    # Display export summary
    parent.dlg_export_summary.exportedBus.setText(f'Buses exported: {bus_count}')
    parent.dlg_export_summary.exportedLines.setText(f'Lines exported: {line_count} ({line_len_count})')
    parent.dlg_export_summary.erroredLines.setText(f'Lines containing errors: {line_error_count}')
    parent.dlg_export_summary.stdTypeList.addItems(exported_std_types)
    parent.dlg_export_summary.show()

def pipes_network(parent, selected_layers) -> None:

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