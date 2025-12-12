from qgis.core import QgsAbstractFeatureSource, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextUtils, QgsFeatureIterator, QgsProject
#from .pandapower_provider import PandapowerProvider
from . import pandapower_feature_iterator

class PandapowerFeatureSource(QgsAbstractFeatureSource):
    def __init__(self, provider):
        """
        Initialize the feature source with a pandapower data provider.
        Args:
            provider: PandapowerProvider instance containing network data and configuration
        """
        super().__init__()
        self.provider = provider

    def getFeatures(self, request) -> QgsFeatureIterator:
        """
        Create and return a feature iterator for accessing pandapower network features.
        Args:
            request: QgsFeatureRequest specifying filtering, ordering, and transformation requirements
        Returns:
            QgsFeatureIterator: Iterator wrapping PandapowerFeatureIterator for QGIS compatibility
        """
        return QgsFeatureIterator(pandapower_feature_iterator.PandapowerFeatureIterator(self, request))

    def get_provider(self):
        """
        Get the associated pandapower data provider instance.
        Returns:
            PandapowerProvider: Provider instance containing network data and metadata
        """
        return self.provider