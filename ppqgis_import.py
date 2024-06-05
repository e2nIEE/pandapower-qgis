# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ppqgis_import

 module for importing pandapower or pandapipes networks to qgis

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
import os.path

from qgis.PyQt.QtGui import QColor
from qgis.core import QgsProject, QgsVectorLayer, QgsApplication, \
    QgsGraduatedSymbolRenderer, QgsSingleSymbolRenderer, QgsRendererRange, QgsClassificationRange, \
    QgsMarkerSymbol, QgsLineSymbol, QgsGradientColorRamp


# constants for color ramps
BUS_LOW_COLOR = "#ccff00"  # lime
BUS_HIGH_COLOR = "#00cc44"  # green
LINE_LOW_COLOR = "#0000ff"  # blue
LINE_HIGH_COLOR = "#ff0022"  # red


# TODO: verify this does not export nodes or branches twice!
def filter_by_voltage(net, vn_kv, tol=10):
    buses = set(net.bus.loc[abs(net.bus.vn_kv - vn_kv) <= tol].index)
    lines = set(net.line.loc[net.line.from_bus.isin(buses) | net.line.to_bus.isin(buses)].index)
    return buses, lines

def filter_by_pressure(net, bar, tol=10):
    junctions = set(net.junction.loc[abs(net.junction.pn_bar - bar) <= tol].index)
    pipes = set(net.pipe.loc[net.pipe.from_junction.isin(junctions) | net.pipe.to_junction.isin(junctions)].index)
    return junctions, pipes


def power_network(parent, file) -> None:
    # get crs of QGIS project
    current_crs = int(QgsProject.instance().crs().authid().split(':')[1])

    parent.installer_func()
    import pandapower as pp
    import pandapower.plotting.geo as geo
    import geojson
    net = pp.from_json(file)

    # add voltage levels to all lines
    pp.add_column_from_node_to_elements(net, 'vn_kv', True, 'line')

    parent.dlg_import.convert_to_power()

    parent.dlg_import.BusLabel.setText(parent.tr(u'#Bus: ') + str(len(net.bus)))
    parent.dlg_import.LineLabel.setText(parent.tr('#Lines: ') + str(len(net.line)))
    # attempt to set the layer name to the filename and set project crs as default
    parent.dlg_import.layerNameEdit.setText(os.path.basename(file).split('.')[0])
    parent.dlg_import.projectionSelect.setCrs(QgsProject.instance().crs())
    # show the dialog
    parent.dlg_import.show()
    # Run the dialog event loop
    result = parent.dlg_import.exec_()
    # See if OK was pressed
    if result:
        folder_name = parent.dlg_import.folderSelect.filePath()
        as_file = True
        if not folder_name:
            as_file = False
        layer_name = parent.dlg_import.layerNameEdit.text()
        run_pandapower = parent.dlg_import.runpp.isChecked()
        render = parent.dlg_import.gradRender.isChecked()
        try:
            crs = int(parent.dlg_import.projectionSelect.crs().authid().split(':')[1])
        except ValueError:
            crs = current_crs

        # run pandapower if selected
        if run_pandapower:
            pp.runpp(net)

        root = QgsProject.instance().layerTreeRoot()
        # check if group exists
        group = root.findGroup(layer_name)
        # create group if it does not exist
        if not group:
            group = root.addGroup(layer_name)

        voltage_levels = net.bus.vn_kv.unique()
        geo.convert_crs(net, epsg_in=crs, epsg_out=current_crs)

        # generate color ramp
        bus_color_ramp = QgsGradientColorRamp(QColor(BUS_LOW_COLOR), QColor(BUS_HIGH_COLOR))
        line_color_ramp = QgsGradientColorRamp(QColor(LINE_LOW_COLOR), QColor(LINE_HIGH_COLOR))

        # Color lines by load/ buses by voltage
        if render:
            classification_methode = QgsApplication.classificationMethodRegistry().method("EqualInterval")

            # generate symbology for bus layer
            bus_target = "vm_pu"
            min_target = "min_vm_pu"
            max_target = "max_vm_pu"
            # map value from its possible min/max to 0/100
            classification_str = f'scale_linear("{bus_target}", 0.9, 1.1, 0, 100)'

            bus_renderer = QgsGraduatedSymbolRenderer()
            bus_renderer.setClassificationMethod(classification_methode)
            bus_renderer.setClassAttribute(classification_str)
            # add categories (10 categories, 10% increments)
            for x in range(10):
                low_bound = x * 10
                high_bound = (x + 1) * 10 - .0001
                if x == 9:  # fix for not including 100%
                    high_bound = 100
                bus_renderer.addClassRange(
                    QgsRendererRange(
                        QgsClassificationRange(f'class {low_bound}-{high_bound}', low_bound, high_bound),
                        QgsMarkerSymbol()
                    )
                )
            bus_renderer.updateColorRamp(bus_color_ramp)

            # generate symbology for line layer
            line_target = "loading_percent"

            line_renderer = QgsGraduatedSymbolRenderer()
            line_renderer.setClassificationMethod(classification_methode)
            line_renderer.setClassAttribute(line_target)

            # add categories (10 categories, 10% increments)
            for x in range(10):
                low_bound = x * 10
                high_bound = (x + 1) * 10 - .0001
                if x == 9:  # fix for not including 100%
                    high_bound = 100
                line_symbol = QgsLineSymbol()
                line_symbol.setWidth(.6)
                line_renderer.addClassRange(
                    QgsRendererRange(
                        QgsClassificationRange(f'class {low_bound}-{high_bound}', low_bound, high_bound),
                        line_symbol
                    )
                )
            line_renderer.updateColorRamp(line_color_ramp)

        # find min and max voltage. Used for finding color of symbols.
        max_kv = max(voltage_levels)
        min_kv = min(voltage_levels)
        for vn_kv in voltage_levels:
            buses, lines = filter_by_voltage(net, vn_kv)

            # Color layers by voltage level
            if not render:
                def map_to_range(x: float, xmin: float, xmax: float, min: float = 0.0, max: float = 1.0):
                    return (x - xmin) / (xmax - xmin) * (max - min) + min

                bus_symbol = QgsMarkerSymbol()
                bus_renderer = QgsSingleSymbolRenderer(bus_symbol)

                line_symbol = QgsLineSymbol()
                line_symbol.setWidth(.6)
                line_renderer = QgsSingleSymbolRenderer(line_symbol)
                # set color of symbol based on vn_kv
                bus_symbol.setColor(bus_color_ramp.color(map_to_range(vn_kv, min_kv, max_kv)))
                line_symbol.setColor(line_color_ramp.color(map_to_range(vn_kv, min_kv, max_kv)))

            bus = {
                'object': buses,
                'suffix': 'bus',
                'renderer': bus_renderer,
            }
            line = {
                'object': lines,
                'suffix': 'line',
                'renderer': line_renderer,
            }

            # create bus and line layers if they contain features
            for obj in [bus, line]:
                # avoid adding empty layer
                if not obj['object']:
                    continue
                type_layer_name = f'{layer_name}_{str(vn_kv)}_{obj["suffix"]}'
                file_path = f'{folder_name}\\{type_layer_name}.geojson'
                gj = geo.dump_to_geojson(net,
                                         nodes=list(obj['object']) if obj['suffix'] == 'bus' else False,
                                         branches=list(obj['object']) if obj['suffix'] == 'line' else False)
                if as_file:
                    with open(file_path, 'w') as file:
                        file.write(geojson.dumps(gj))
                        file.close()
                    layer = QgsVectorLayer(file_path, type_layer_name, "ogr")
                else:
                    layer = QgsVectorLayer(geojson.dumps(gj), type_layer_name, "ogr")
                layer.setRenderer(obj['renderer'])
                # add layer to group
                QgsProject.instance().addMapLayer(layer, False)
                group.addLayer(layer)

            if buses or lines:
                # Move layers above TileLayer
                root.setHasCustomLayerOrder(True)
                order = root.customLayerOrder()
                order.insert(0, order.pop())
                if buses and lines:
                    order.insert(0, order.pop())
                root.setCustomLayerOrder(order)

def pipes_network(parent, file):
    # get crs of QGIS project
    current_crs = int(QgsProject.instance().crs().authid().split(':')[1])

    import pandapipes as pp
    import pandapower.plotting.geo as geo
    import geojson
    net = pp.from_json(file)

    parent.dlg_import.convert_to_pipes()

    parent.dlg_import.BusLabel.setText(parent.tr(u'#Junctions: ') + str(len(net.junction)))
    parent.dlg_import.LineLabel.setText(parent.tr('#Pipes: ') + str(len(net.pipe)))
    # attempt to set the layer name to the filename and set project crs as default
    parent.dlg_import.layerNameEdit.setText(os.path.basename(file).split('.')[0])
    parent.dlg_import.projectionSelect.setCrs(QgsProject.instance().crs())
    # show the dialog
    parent.dlg_import.show()
    # Run the dialog event loop
    result = parent.dlg_import.exec_()
    # See if OK was pressed
    if result:
        folder_name = parent.dlg_import.folderSelect.filePath()
        as_file = True
        if not folder_name:
            as_file = False
        layer_name = parent.dlg_import.layerNameEdit.text()
        run_pandapipes = parent.dlg_import.runpp.isChecked()
        render = parent.dlg_import.gradRender.isChecked()
        try:
            crs = int(parent.dlg_import.projectionSelect.crs().authid().split(':')[1])
        except ValueError:
            crs = current_crs

        # run pandapipes if selected
        if run_pandapipes:
            pp.runpp(net)

        root = QgsProject.instance().layerTreeRoot()
        # check if group exists
        group = root.findGroup(layer_name)
        # create group if it does not exist
        if not group:
            group = root.addGroup(layer_name)

        pressure_levels = net.junction.pn_bar.unique()
        geo.convert_crs(net, epsg_in=crs, epsg_out=current_crs)

        # generate color ramp
        junction_color_ramp = QgsGradientColorRamp(QColor(BUS_LOW_COLOR), QColor(BUS_HIGH_COLOR))
        pipe_color_ramp = QgsGradientColorRamp(QColor(LINE_LOW_COLOR), QColor(LINE_HIGH_COLOR))

        # Color lines by load/ buses by voltage
        if render:
            classification_methode = QgsApplication.classificationMethodRegistry().method("EqualInterval")

            # generate symbology for bus layer
            junction_target = "pn_bar"
            min_target = 0.0
            max_target = 110
            # map value from its possible min/max to 0/100
            classification_str = f'scale_linear("{junction_target}", 0, 110, 0, 100)'

            junction_renderer = QgsGraduatedSymbolRenderer()
            junction_renderer.setClassificationMethod(classification_methode)
            junction_renderer.setClassAttribute(classification_str)
            # add categories (10 categories, 10% increments)
            for x in range(10):
                low_bound = x * 10
                high_bound = (x + 1) * 10 - .0001
                if x == 9:  # fix for not including 100%
                    high_bound = 100
                junction_renderer.addClassRange(
                    QgsRendererRange(
                        QgsClassificationRange(f'class {low_bound}-{high_bound}', low_bound, high_bound),
                        QgsMarkerSymbol()
                    )
                )
            junction_renderer.updateColorRamp(junction_color_ramp)

            # generate symbology for line layer
            pipe_target = "diameter_m"

            # map value from its possible min/max to 0/100
            classification_str = f'scale_linear("{pipe_target}", 0, 20, 0, 100)'

            pipe_renderer = QgsGraduatedSymbolRenderer()
            pipe_renderer.setClassificationMethod(classification_methode)
            pipe_renderer.setClassAttribute(classification_str)

            # add categories (10 categories, 10% increments)
            for x in range(10):
                low_bound = x * 10
                high_bound = (x + 1) * 10 - .0001
                if x == 9:  # fix for not including 100%
                    high_bound = 100
                pipe_symbol = QgsLineSymbol()
                pipe_symbol.setWidth(.6)
                pipe_renderer.addClassRange(
                    QgsRendererRange(
                        QgsClassificationRange(f'class {low_bound}-{high_bound}', low_bound, high_bound),
                        pipe_symbol
                    )
                )
            pipe_renderer.updateColorRamp(pipe_color_ramp)

        # find min and max voltage. Used for finding color of symbols.
        max_pressure = max(pressure_levels)
        min_pressure = min(pressure_levels)
        for pn_bar in pressure_levels:
            junctions, pipes = filter_by_pressure(net, pn_bar)

            # Color layers by pressure level
            if not render:
                def map_to_range(x: float, xmin: float, xmax: float, min: float = 0.0, max: float = 1.0):
                    return (x - xmin) / (xmax - xmin) * (max - min) + min

                junction_symbol = QgsMarkerSymbol()
                junction_renderer = QgsSingleSymbolRenderer(junction_symbol)

                pipe_symbol = QgsLineSymbol()
                pipe_symbol.setWidth(.6)
                pipe_renderer = QgsSingleSymbolRenderer(pipe_symbol)
                # set color of symbol based on vn_kv
                junction_symbol.setColor(junction_color_ramp.color(map_to_range(pn_bar, min_pressure, max_pressure)))
                pipe_symbol.setColor(pipe_color_ramp.color(map_to_range(pn_bar, min_pressure, max_pressure)))

            junction = {
                'object': junctions,
                'suffix': 'junction',
                'renderer': junction_renderer,
            }
            pipe = {
                'object': pipes,
                'suffix': 'pipe',
                'renderer': pipe_renderer,
            }

            # create junction and pipe layers if they contain features
            for obj in [junction, pipe]:
                # avoid adding empty layer
                if not obj['object']:
                    continue
                type_layer_name = f'{layer_name}_{str(pn_bar)}_{obj["suffix"]}'
                file_path = f'{folder_name}\\{type_layer_name}.geojson'
                gj = geo.dump_to_geojson(net,
                                         nodes=obj['object'] if obj['suffix'] == 'junction' else False,
                                         branches=obj['object'] if obj['suffix'] == 'pipe' else False)
                if as_file:
                    with open(file_path, 'w') as file:
                        file.write(geojson.dumps(gj))
                        file.close()
                    layer = QgsVectorLayer(file_path, type_layer_name, "ogr")
                else:
                    layer = QgsVectorLayer(geojson.dumps(gj), type_layer_name, "ogr")
                layer.setRenderer(obj['renderer'])
                # add layer to group
                QgsProject.instance().addMapLayer(layer, False)
                group.addLayer(layer)

            if junctions or pipes:
                # Move layers above TileLayer
                root.setHasCustomLayerOrder(True)
                order = root.customLayerOrder()
                order.insert(0, order.pop())
                if junctions and pipes:
                    order.insert(0, order.pop())
                root.setCustomLayerOrder(order)
