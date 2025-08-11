# -*- coding: utf-8 -*-
"""
렌더러 유틸리티 - 기존 ppqgis_import 방식을 공통으로 사용
"""

from qgis.core import (QgsGraduatedSymbolRenderer, QgsRendererRange,
                       QgsClassificationRange, QgsMarkerSymbol, QgsLineSymbol,
                       QgsGradientColorRamp, QgsApplication, QgsSingleSymbolRenderer)
from qgis.PyQt.QtGui import QColor

# # 기존 ppqgis_import.py에서 사용하던 색상들
# BUS_LOW_COLOR = "#ccff00"  # lime
# BUS_HIGH_COLOR = "#00cc44"  # green
# LINE_LOW_COLOR = "#0000ff"  # blue
# LINE_HIGH_COLOR = "#ff0022"  # red

BUS_LOW_COLOR = QColor("#ccff00")  # lime
BUS_HIGH_COLOR = QColor("#00cc44")  # green
LINE_LOW_COLOR = QColor("#0000ff")  # blue
LINE_HIGH_COLOR = QColor("#ff0022")  # red


def create_bus_renderer(render=True):
    """
    Args:
        render (bool): True면 그라데이션 렌더링, False면 단일 색상
    Returns:
        QgsRenderer: 생성된 렌더러 (단일 색상일 때는 color_ramp도 함께)
    """
    bus_color_ramp = QgsGradientColorRamp(QColor(BUS_LOW_COLOR), QColor(BUS_HIGH_COLOR))

    if render:
        classification_method = QgsApplication.classificationMethodRegistry().method("EqualInterval")

        bus_target = "vm_pu"
        classification_str = f'scale_linear("{bus_target}", 0.9, 1.1, 0, 100)'

        bus_renderer = QgsGraduatedSymbolRenderer()
        bus_renderer.setClassificationMethod(classification_method)
        bus_renderer.setClassAttribute(classification_str)

        # 범위 수동 설정 (scale_linear 대신)
        for x in range(10):
            low_bound = x * 10
            high_bound = (x + 1) * 10 - .0001
            if x == 9:
                high_bound = 100
            bus_renderer.addClassRange(
                QgsRendererRange(
                    QgsClassificationRange(f'class {low_bound}-{high_bound}', low_bound, high_bound),
                    QgsMarkerSymbol()
                )
            )
        bus_renderer.updateColorRamp(bus_color_ramp)
        return bus_renderer
    else:
        # 단순 렌더러
        bus_symbol = QgsMarkerSymbol()
        bus_renderer = QgsSingleSymbolRenderer(bus_symbol)
        return bus_renderer, bus_color_ramp


def create_line_renderer(render=True):
    """
    수정된 라인 렌더러 - scale_linear 제거
    """
    line_color_ramp = QgsGradientColorRamp(QColor(LINE_LOW_COLOR), QColor(LINE_HIGH_COLOR))

    if render:
        classification_method = QgsApplication.classificationMethodRegistry().method("EqualInterval")

        line_target = "loading_percent"  # 필드명 직접 사용

        line_renderer = QgsGraduatedSymbolRenderer()
        line_renderer.setClassificationMethod(classification_method)

        # 🎯 핵심 수정: scale_linear 대신 필드명 직접 사용
        line_renderer.setClassAttribute(line_target)  # "loading_percent"만 사용

        # 범위 수동 설정
        for x in range(10):
            low_bound = x * 10
            high_bound = (x + 1) * 10 - .0001
            if x == 9:
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
        return line_renderer
    else:
        # 단순 렌더러
        line_symbol = QgsLineSymbol()
        line_symbol.setWidth(.6)
        line_renderer = QgsSingleSymbolRenderer(line_symbol)
        return line_renderer, line_color_ramp


# def create_bus_renderer(render=True):
#     """
#     기존 ppqgis_import.py와 동일한 버스 렌더러 생성
#     """
#     bus_color_ramp = QgsGradientColorRamp(QColor(BUS_LOW_COLOR), QColor(BUS_HIGH_COLOR))
#
#     if render:
#         # 기존 ppqgis_import의 그라데이션 방식 (render=True일 때)
#         classification_methode = QgsApplication.classificationMethodRegistry().method("EqualInterval")
#
#         bus_target = "vm_pu"
#         classification_str = f'scale_linear("{bus_target}", 0.9, 1.1, 0, 100)'
#
#         bus_renderer = QgsGraduatedSymbolRenderer()
#         bus_renderer.setClassificationMethod(classification_methode)
#         bus_renderer.setClassAttribute(classification_str)
#
#         # 10개 카테고리, 10% 증가
#         for x in range(10):
#             low_bound = x * 10
#             high_bound = (x + 1) * 10 - .0001
#             if x == 9:  # 100% 포함을 위한 수정
#                 high_bound = 100
#             bus_renderer.addClassRange(
#                 QgsRendererRange(
#                     QgsClassificationRange(f'class {low_bound}-{high_bound}', low_bound, high_bound),
#                     QgsMarkerSymbol()
#                 )
#             )
#         bus_renderer.updateColorRamp(bus_color_ramp)
#         return bus_renderer
#     else:
#         # 기존 ppqgis_import의 단일 색상 방식 (render=False일 때)
#         bus_symbol = QgsMarkerSymbol()
#         bus_renderer = QgsSingleSymbolRenderer(bus_symbol)
#         return bus_renderer, bus_color_ramp  # color_ramp도 함께 반환
#
#
# def create_line_renderer(render=True):
#     """
#     기존 ppqgis_import.py와 동일한 라인 렌더러 생성
#     """
#     line_color_ramp = QgsGradientColorRamp(QColor(LINE_LOW_COLOR), QColor(LINE_HIGH_COLOR))
#
#     if render:
#         # 기존 ppqgis_import의 그라데이션 방식 (render=True일 때)
#         classification_methode = QgsApplication.classificationMethodRegistry().method("EqualInterval")
#
#         line_target = "loading_percent"
#
#         line_renderer = QgsGraduatedSymbolRenderer()
#         line_renderer.setClassificationMethod(classification_methode)
#         line_renderer.setClassAttribute(line_target)
#
#         # 10개 카테고리, 10% 증가
#         for x in range(10):
#             low_bound = x * 10
#             high_bound = (x + 1) * 10 - .0001
#             if x == 9:  # 100% 포함을 위한 수정
#                 high_bound = 100
#             line_symbol = QgsLineSymbol()
#             line_symbol.setWidth(.6)
#             line_renderer.addClassRange(
#                 QgsRendererRange(
#                     QgsClassificationRange(f'class {low_bound}-{high_bound}', low_bound, high_bound),
#                     line_symbol
#                 )
#             )
#         line_renderer.updateColorRamp(line_color_ramp)
#         return line_renderer
#     else:
#         # 기존 ppqgis_import의 단일 색상 방식 (render=False일 때)
#         line_symbol = QgsLineSymbol()
#         line_symbol.setWidth(.6)
#         line_renderer = QgsSingleSymbolRenderer(line_symbol)
#         return line_renderer, line_color_ramp  # color_ramp도 함께 반환