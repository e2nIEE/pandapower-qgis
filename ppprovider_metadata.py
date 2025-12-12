import re
from typing import Dict
from .pandapower_provider import PandapowerProvider
from qgis.core import QgsProviderMetadata, QgsReadWriteContext

class PandapowerProviderMetadata(QgsProviderMetadata):
    def __init__(self):
        """
        Initialize the PandapowerProvider metadata with provider identification and factory method.
        Registers the provider with QGIS using name "PandapowerProvider", description, and
        createProvider factory method reference.
        """
        super().__init__(
            "PandapowerProvider",
            "Pandapower Network Provider",
            PandapowerProvider.createProvider  # Factory Method Reference
        )


    def decodeUri(self, uri):
        """
        Parse URI string into component dictionary using regex pattern matching.
        Extracts key-value pairs from format: key="value";key2="value2" with support
        for escaped quotes in values.
        Args:
            uri: URI string containing encoded provider parameters
        Returns:
            dict: Dictionary of decoded key-value pairs from the URI
        """
        matches = re.findall(r'(\w+)="((?:\\"|[^"])*)"', uri)
        return {key: value for key, value in matches}


    def encodeUri(self, parts):
        """
        Encode component dictionary into URI string format.
        Converts key-value pairs into semicolon-separated string with quoted values.
        Args:
            parts: Dictionary of key-value pairs to encode
        Returns:
            str: Encoded URI string in format key="value";key2="value2"
        """
        uri_components = []
        for key, value in parts.items():
            if value:
                uri_components.append(f'{key}="{value}"')
        return ";".join(uri_components)


    def capabilities(self):
        """
        QGIS에게 "이 Provider는 파일 기반 데이터야!"라고 알려줍니다.
        이것이 있어야:
        - Layer → Add Layer → Add Vector Layer 메뉴에서
        - "File" 소스 타입 선택 시
        - 파일 선택 대화상자에 우리 provider가 나타납니다!
        Returns:
            FileBasedUris 플래그 - 파일 기반 데이터 소스임을 표시
        """
        return QgsProviderMetadata.FileBasedUris


    def filters(self, filterType):
        """
        이 메서드로 파일 필터를 정의합니다!

        "Add Vector Layer" → "File" 선택 시
        드롭다운에 나타나는 파일 형식 목록을 정의합니다.

        예: "ESRI Shapefiles (*.shp)", "GeoJSON (*.geojson)" 같은 것들

        Args:
            filterType: QGIS가 요청하는 필터 타입
                       (Vector/Raster/Mesh 등)

        Returns:
            str: 파일 필터 문자열
                 형식: "설명 (*.확장자);;다른설명 (*.확장자)"
        """
        if filterType == QgsProviderMetadata.FilterType.FilterVector:
            # 세미콜론 2개(;;)로 여러 필터 구분
            return "Pandapower Networks (*.json);;All files (*.*)"
        return ""


    def icon(self):
        """
        🎨 Provider 아이콘 (선택사항이지만 있으면 좋아요!)

        Data Source Manager와 Browser에 표시될 아이콘입니다.
        pp.png 파일이 플러그인 폴더에 있다면 사용합니다.

        Returns:
            QIcon: Provider 아이콘
        """
        icon_path = os.path.join(os.path.dirname(__file__), 'pp.png')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()  # 아이콘 없으면 빈 아이콘 반환
