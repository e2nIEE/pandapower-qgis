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
