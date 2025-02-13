import re
from typing import Dict
#from .ppprovider import PandapowerProvider
from .pandapower_provider import PandapowerProvider
from qgis.core import QgsProviderMetadata, QgsReadWriteContext

class PandapowerProviderMetadata(QgsProviderMetadata):
    def __init__(self):
        super().__init__(
            "PandapowerProvider",
            "Pandapower Network Provider",
            PandapowerProvider.createProvider  # 팩토리 메서드 참조
        )

    def decodeUri(self, uri):
        """URI 문자열을 파싱하여 구성요소로 분리"""
        matches = re.findall(r'(\w+)="((?:\\"|[^"])*)"', uri)
        return {key: value for key, value in matches}

    def encodeUri(self, parts):
        """구성요소들을 URI 문자열로 인코딩"""
        uri_components = []
        for key, value in parts.items():
            if value:
                uri_components.append(f'{key}="{value}"')
        return ";".join(uri_components)
