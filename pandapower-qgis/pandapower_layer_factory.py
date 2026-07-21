# -*- coding: utf-8 -*-
"""Building QgsVectorLayers for pandapower tables.

Layer construction used to live inline in ``ppqgis_import``, tangled up with
dialogs, layer groups and the project tree. That made it unreachable from any
other entry point. This module owns it instead, and deliberately has **no
project side effects**: it builds a layer and hands it back. The caller decides
where it goes.

That is what lets the import dialog, the browser tree (phase 4) and the Data
Source Manager (phase 5) all produce identical layers.

See docs/dataprovider_v2_plan.md section 3.4.
"""

from qgis.core import QgsProviderRegistry, QgsVectorLayer

from .pandapower_maptip import MapTipUtils
from .pandapower_uri import encode_uri, has_geometry, layer_name_for

PROVIDER_KEY = 'PandapowerProvider'


def build_uri(path, table, level=None, epsg=None):
    """Build a layer URI for one pandapower table.

    Goes through the registered provider metadata when it is available, so the
    encoding stays consistent with whatever the provider itself decodes, and
    falls back to the local encoder when the provider is not registered (which
    is the case in unit tests).

    Args:
        path: Path of the network JSON file.
        table: pandapower table name.
        level: Voltage or pressure level, or None for the whole table.
        epsg: EPSG code of the geodata.
    Returns:
        str: Encoded URI.
    """
    metadata = QgsProviderRegistry.instance().providerMetadata(PROVIDER_KEY)
    if metadata is None:
        return encode_uri(path, table, level=level, epsg=epsg)

    parts = {'path': path, 'table': table}
    if level not in (None, ''):
        parts['level'] = str(level)
    if epsg not in (None, ''):
        parts['epsg'] = str(epsg)
    return metadata.encodeUri(parts)


def configure_field_edit_permissions(layer):
    """Mark provider-computed fields as read-only in the attribute form.

    Result columns and derived values must not be edited by hand, so the
    provider is asked about each field and the form config follows its answer.

    Args:
        layer: The QgsVectorLayer to configure.
    """
    provider = layer.dataProvider()
    if not hasattr(provider, 'is_field_editable'):
        return

    fields = layer.fields()
    config = layer.editFormConfig()

    for field in fields:
        index = fields.indexFromName(field.name())
        if index < 0:
            continue
        if not provider.is_field_editable(field.name()):
            config.setReadOnly(index, True)

    layer.setEditFormConfig(config)


def create_layer(path, table, level=None, epsg=None, name=None,
                 renderer=None, configure_permissions=True,
                 configure_map_tips=True):
    """Build a QgsVectorLayer for one pandapower table.

    The layer is **not** added to the project and **not** placed in any group;
    the caller owns placement.

    Args:
        path: Path of the network JSON file.
        table: pandapower table name, e.g. 'bus', 'line', 'trafo'.
        level: Voltage or pressure level to filter to, or None for the whole table.
        epsg: EPSG code of the geodata.
        name: Layer display name. Derived from the file and table when omitted.
        renderer: Renderer to apply. The layer keeps its default when omitted.
            Note that a renderer instance must not be shared between layers,
            since each layer takes ownership of it.
        configure_permissions: Mark provider-computed fields read-only.
        configure_map_tips: Attach the HTML map tip template.
    Returns:
        QgsVectorLayer: The layer. Check ``isValid()`` before using it; an
            invalid layer usually means the network file could not be read.
    """
    uri = build_uri(path, table, level=level, epsg=epsg)
    layer_name = name or layer_name_for(path, table, level)

    layer = QgsVectorLayer(uri, layer_name, PROVIDER_KEY)

    if not layer.isValid():
        # Hand the invalid layer back rather than raising: the caller is in a
        # better position to report the failure to the user.
        return layer

    if renderer is not None:
        layer.setRenderer(renderer)

    if configure_permissions:
        configure_field_edit_permissions(layer)

    # Map tips describe geometry-bearing elements; an attribute-only table has
    # nothing to show on the canvas.
    if configure_map_tips and has_geometry(table):
        MapTipUtils.configure_map_tips(layer, level, table)

    return layer
