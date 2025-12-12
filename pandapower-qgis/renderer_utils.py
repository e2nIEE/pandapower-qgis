from qgis.PyQt.QtGui import QColor
from qgis.core import QgsProject, QgsVectorLayer, QgsApplication, \
    QgsRuleBasedRenderer, QgsSingleSymbolRenderer, QgsRendererRange, QgsClassificationRange, \
    QgsMarkerSymbol, QgsLineSymbol, QgsGradientColorRamp, QgsProviderRegistry, QgsProviderMetadata

RED_COLOR = "#ff0000"
GREEN_COLOR = "#00cc44"
BLUE_COLOR = "#0000ff"
GRAY_COLOR = "#999999"


def create_power_renderer():
    """
    Returns:
        QgsRenderer: Created bus and line renderer (rule-based)
    """
    # Create a rule-based renderer for the bus layer
    bus_renderer = QgsRuleBasedRenderer(QgsMarkerSymbol())
    bus_root_rule = bus_renderer.rootRule()

    # Bus rule 0: vm_pu IS NULL (gray) - for newly added features
    bus_rule_gray = QgsRuleBasedRenderer.Rule(QgsMarkerSymbol())
    bus_rule_gray.setFilterExpression('"vm_pu" IS NULL')
    bus_rule_gray.setLabel('Not calculated')
    bus_symbol_gray = QgsMarkerSymbol()
    bus_symbol_gray.setColor(QColor(GRAY_COLOR))
    bus_rule_gray.setSymbol(bus_symbol_gray)
    bus_root_rule.appendChild(bus_rule_gray)

    # Bus rule 1: vm_pu > 1.1 (red)
    bus_rule_red = bus_root_rule.children()[0].clone()\
        if bus_root_rule.children() else QgsRuleBasedRenderer.Rule(QgsMarkerSymbol())
    bus_rule_red.setFilterExpression('"vm_pu" > 1.1')
    bus_rule_red.setLabel('vm_pu > 1.1')
    bus_symbol_red = QgsMarkerSymbol()
    bus_symbol_red.setColor(QColor(RED_COLOR))
    bus_rule_red.setSymbol(bus_symbol_red)
    bus_root_rule.appendChild(bus_rule_red)

    # Bus rule 2: 0.9 <= vm_pu <= 1.1 (green)
    bus_rule_green = QgsRuleBasedRenderer.Rule(QgsMarkerSymbol())
    bus_rule_green.setFilterExpression('"vm_pu" >= 0.9 AND "vm_pu" <= 1.1')
    bus_rule_green.setLabel('0.9 <= vm_pu <= 1.1')
    bus_symbol_green = QgsMarkerSymbol()
    bus_symbol_green.setColor(QColor(GREEN_COLOR))
    bus_rule_green.setSymbol(bus_symbol_green)
    bus_root_rule.appendChild(bus_rule_green)

    # Bus rule 3: vm_pu < 0.9 (blue)
    bus_rule_blue = QgsRuleBasedRenderer.Rule(QgsMarkerSymbol())
    bus_rule_blue.setFilterExpression('"vm_pu" < 0.9')
    bus_rule_blue.setLabel('vm_pu < 0.9')
    bus_symbol_blue = QgsMarkerSymbol()
    bus_symbol_blue.setColor(QColor(BLUE_COLOR))
    bus_rule_blue.setSymbol(bus_symbol_blue)
    bus_root_rule.appendChild(bus_rule_blue)


    # Create a rule-based renderer for the line layer
    line_renderer = QgsRuleBasedRenderer(QgsLineSymbol())
    line_root_rule = line_renderer.rootRule()

    # Line rule 0: loading_percent IS NULL (gray) - for newly added features
    line_rule_gray = QgsRuleBasedRenderer.Rule(QgsLineSymbol())
    line_rule_gray.setFilterExpression('"loading_percent" IS NULL')
    line_rule_gray.setLabel('Not calculated')
    line_symbol_gray = QgsLineSymbol()
    line_symbol_gray.setColor(QColor(GRAY_COLOR))
    line_symbol_gray.setWidth(0.6)
    line_rule_gray.setSymbol(line_symbol_gray)
    line_root_rule.appendChild(line_rule_gray)

    # Line rule 1: loading_percent > 100 (red)
    line_rule_red = QgsRuleBasedRenderer.Rule(QgsLineSymbol())
    line_rule_red.setFilterExpression('"loading_percent" > 100')
    line_rule_red.setLabel('loading_percent > 100%')
    line_symbol_red = QgsLineSymbol()
    line_symbol_red.setColor(QColor(RED_COLOR))
    line_symbol_red.setWidth(0.6)
    line_rule_red.setSymbol(line_symbol_red)
    line_root_rule.appendChild(line_rule_red)

    # Line rule 2: loading_percent <= 100 (green)
    line_rule_green = QgsRuleBasedRenderer.Rule(QgsLineSymbol())
    line_rule_green.setFilterExpression('"loading_percent" <= 100')
    line_rule_green.setLabel('loading_percent <= 100%')
    line_symbol_green = QgsLineSymbol()
    line_symbol_green.setColor(QColor(GREEN_COLOR))
    line_symbol_green.setWidth(0.6)
    line_rule_green.setSymbol(line_symbol_green)
    line_root_rule.appendChild(line_rule_green)

    # Remove the default 'no filter' rule
    bus_root_rule.removeChildAt(0)
    line_root_rule.removeChildAt(0)

    return bus_renderer, line_renderer


def create_pipe_renderer():
    pass
