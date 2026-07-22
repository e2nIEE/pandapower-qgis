import os
import re
from typing import Dict
from .pandapower_provider import PandapowerProvider
from qgis.core import QgsProviderMetadata, QgsReadWriteContext
from qgis.PyQt.QtGui import QIcon

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
        Declare what this provider metadata can do.
        A pandapower network is reached through the Data Source Manager entry and
        the Browser tree, not through the generic "Add Vector Layer -> File"
        dialog: that path is what made the plugin feel like an import step.
        Note this returns ProviderMetadataCapability values. The previous
        implementation returned FileBasedUris, which belongs to the unrelated
        ProviderCapability enum returned by providerCapabilities().
        Returns:
            QgsProviderMetadata.ProviderMetadataCapabilities
        """
        return QgsProviderMetadata.ProviderMetadataCapability.LayerTypesForUri


    def providerCapabilities(self):
        """
        Declare provider-level capabilities.
        The URI does address a file on disk, so FileBasedUris stays accurate;
        it belongs here rather than in capabilities().
        Returns:
            QgsProviderMetadata.ProviderCapabilities
        """
        return QgsProviderMetadata.FileBasedUris


    def filters(self, filterType):
        """
        Define the file filters offered for this provider.
        Deliberately empty: advertising "*.json" as a generic vector file filter
        put pandapower networks into the "Add Vector Layer -> File" dialog, where
        opening one behaves like an import rather than a live connection. Use the
        "pandapower" entry in the Data Source Manager or the Browser instead.
        Args:
            filterType: Filter type requested by QGIS (Vector/Raster/Mesh/...)
        Returns:
            str: Empty string, so no filter is contributed
        """
        return ""


    def icon(self):
        """
        Provider icon shown in the Data Source Manager and the Browser.
        Uses pp.png from the plugin folder when it is available.
        Returns:
            QIcon: Provider icon, or an empty icon if the file is missing
        """
        icon_path = os.path.join(os.path.dirname(__file__), 'pp.png')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()  # Fall back to an empty icon
