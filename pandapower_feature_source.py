from qgis.core import QgsAbstractFeatureSource, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextUtils, QgsFeatureIterator, QgsProject
#from .pandapower_provider import PandapowerProvider
from . import pandapower_feature_iterator

class PandapowerFeatureSource(QgsAbstractFeatureSource):
    def __init__(self, provider):
        """Constructor"""
        super().__init__()
        self.provider = provider

    def getFeatures(self, request) -> QgsFeatureIterator:
        """피처 이터레이터를 생성하여 반환합니다"""
        return QgsFeatureIterator(pandapower_feature_iterator.PandapowerFeatureIterator(self, request))

    def get_provider(self):
        """프로바이더 인스턴스에 대한 접근을 제공합니다"""
        return self.provider