# -*- coding: utf-8 -*-
"""
Renderer utility: use the standard ppqgis_import method.
"""

from qgis.PyQt.QtGui import QColor
from qgis.core import QgsProject, QgsVectorLayer, QgsApplication, \
    QgsGraduatedSymbolRenderer, QgsSingleSymbolRenderer, QgsRendererRange, QgsClassificationRange, \
    QgsMarkerSymbol, QgsLineSymbol, QgsGradientColorRamp, QgsProviderRegistry, QgsProviderMetadata

BUS_LOW_COLOR = "#ccff00"  # lime
BUS_HIGH_COLOR = "#00cc44"  # green
LINE_LOW_COLOR = "#0000ff"  # blue
LINE_HIGH_COLOR = "#ff0022"  # red


def create_power_renderer():
    """
    Returns:
        QgsRenderer: Created renderer (includes color_ramp when single color)
    """
    bus_color_ramp = QgsGradientColorRamp(QColor(BUS_LOW_COLOR), QColor(BUS_HIGH_COLOR))
    line_color_ramp = QgsGradientColorRamp(QColor(LINE_LOW_COLOR), QColor(LINE_HIGH_COLOR))

    classification_method = QgsApplication.classificationMethodRegistry().method("EqualInterval")

    # generate symbology for bus layer
    bus_target = "vm_pu"
    min_target = "min_vm_pu"
    max_target = "max_vm_pu"
    # map value from its possible min/max to 0/100
    classification_str = f'scale_linear("{bus_target}", 0.9, 1.1, 0, 100)'

    bus_renderer = QgsGraduatedSymbolRenderer()
    bus_renderer.setClassificationMethod(classification_method)
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
    line_renderer.setClassificationMethod(classification_method)
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

    return bus_renderer, line_renderer


def create_pipe_renderer():
    pass