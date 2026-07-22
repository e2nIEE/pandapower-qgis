# -*- coding: utf-8 -*-
"""Encoding and decoding of pandapower layer URIs.

A layer URI addresses one pandapower table inside one network file, optionally
narrowed to a single voltage (or pressure) level::

    path="C:/net/mv_oberrhein.json";table="bus";level="20.0";epsg="4326"
    path="C:/net/mv_oberrhein.json";table="trafo";epsg="4326"

The scheme changed in the data provider rework (plan section 3.5):

======================  ==========================================================
``network_type=``       renamed to ``table=``, because a URI can now address any
                        pandapower table, not only the four geometry-bearing ones
``voltage_level=``      renamed to ``level=``
``pressure_level=``     merged into ``level=`` as well
``geometry=``           dropped; it is derivable from the table name
======================  ==========================================================

:py:func:`decode_uri` still understands the old keys, so projects saved with an
earlier version keep opening. Note that the old scheme had a latent bug: the
import path wrote ``pressure_level`` for pipe networks while the provider only
ever read ``voltage_level``, so pipe layers silently lost their level. Folding
both into ``level`` fixes that.
"""

# Tables that carry point geometry, and those that carry line geometry.
POINT_TABLES = ('bus', 'junction')
LINE_TABLES = ('line', 'pipe')

# Tables that can be filtered by a voltage or pressure level.
LEVELLED_TABLES = POINT_TABLES + LINE_TABLES

# URI keys understood for the level, newest first. The old names are accepted so
# that projects saved before the rework still load.
_LEVEL_KEYS = ('level', 'voltage_level', 'pressure_level')

# URI keys understood for the table name, newest first.
_TABLE_KEYS = ('table', 'network_type')


def geometry_type_for(table):
    """Return the geometry type a table carries.

    Args:
        table: pandapower table name, e.g. 'bus' or 'trafo'.
    Returns:
        str: 'Point', 'LineString', or 'None' for attribute-only tables.
    """
    if table in POINT_TABLES:
        return 'Point'
    if table in LINE_TABLES:
        return 'LineString'
    return 'None'


def has_geometry(table):
    """Whether a table carries geometry.

    Args:
        table: pandapower table name.
    Returns:
        bool: True for bus/junction/line/pipe, False otherwise.
    """
    return table in LEVELLED_TABLES


def encode_uri(path, table, level=None, epsg=None):
    """Build a layer URI.

    Args:
        path: Path of the network JSON file.
        table: pandapower table name, e.g. 'bus', 'line', 'trafo'.
        level: Voltage or pressure level to filter to, or None for the whole table.
        epsg: EPSG code of the geodata.
    Returns:
        str: Encoded URI.
    """
    parts = [('path', path), ('table', table)]
    if level not in (None, ''):
        parts.append(('level', str(level)))
    if epsg not in (None, ''):
        parts.append(('epsg', str(epsg)))

    # Quotes inside a value would terminate it early, so they are escaped.
    return ';'.join(
        '{}="{}"'.format(key, str(value).replace('"', '\\"'))
        for key, value in parts if value not in (None, '')
    )


def decode_uri(uri_parts):
    """Normalise a decoded URI dictionary into the current scheme.

    Accepts both the current keys and the pre-rework ones, so a project saved
    by an earlier version still opens.

    Args:
        uri_parts: Dictionary as returned by QgsProviderMetadata.decodeUri.
    Returns:
        dict: With keys 'path', 'table', 'level' and 'epsg'. 'level' is None
            when the URI addresses a whole table.
    """
    parts = dict(uri_parts or {})

    table = None
    for key in _TABLE_KEYS:
        if parts.get(key):
            table = parts[key]
            break

    level = None
    for key in _LEVEL_KEYS:
        value = parts.get(key)
        if value not in (None, ''):
            level = value
            break

    return {
        'path': parts.get('path', ''),
        'table': table,
        'level': level,
        'epsg': parts.get('epsg') or None,
    }


def layer_name_for(path, table, level=None):
    """Build the display name for a layer.

    Args:
        path: Path of the network file.
        table: pandapower table name.
        level: Voltage or pressure level, or None.
    Returns:
        str: e.g. 'mv_oberrhein_20.0_bus' or 'mv_oberrhein_trafo'.
    """
    import os

    base = os.path.basename(path).split('.')[0] if path else 'network'
    if level not in (None, ''):
        return '{}_{}_{}'.format(base, level, table)
    return '{}_{}'.format(base, table)
