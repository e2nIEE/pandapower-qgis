# -*- coding: utf-8 -*-
"""
this code is part of PR #1731 at e2nIEE/pandapower
when the PR has been merged this file should be removed and its call replaced in pandapower_qgis.py

https://github.com/e2nIEE/pandapower/blob/develop/pandapower/plotting/geo.py
"""

import sys
import math
import pandas as pd
from pandapower.auxiliary import soft_dependency_error

try:
    from pyproj import Transformer
    pyproj_INSTALLED = True
except ImportError:
    pyproj_INSTALLED = False

try:
    import geojson
    geojson_INSTALLED = True
except ImportError:
    geojson_INSTALLED = False


def convert_crs(net, epsg_in=4326, epsg_out=31467):
    """
    Converts bus and line geodata in net from epsg_in to epsg_out
    if GeoDataFrame data is present convert_geodata_to_gis should be used to update geometries after crs conversion

    :param net: The pandapower network
    :type net: pandapowerNet
    :param epsg_in: current epsg projection
    :type epsg_in: int, default 4326 (= WGS84)
    :param epsg_out: epsg projection to be transformed to
    :type epsg_out: int, default 31467 (= Gauss-Krüger Zone 3)
    :return: net - the given pandapower network (no copy!)
    """
    if epsg_in == epsg_out:
        return

    if not pyproj_INSTALLED:
        soft_dependency_error(str(sys._getframe().f_code.co_name)+"()", "pyproj")
    transformer = Transformer.from_crs(epsg_in, epsg_out, always_xy=True)

    def _geo_bus_transformer(r):
        (x, y) = transformer.transform(r.x, r.y)
        coords = r.coords
        if coords and not pd.isna(coords):
            coords = _geo_line_transformer(coords)
        return pd.Series([x, y, coords], ["x", "y", "coords"])

    def _geo_line_transformer(r):
        return list(transformer.itransform(r))

    net.bus_geodata = net.bus_geodata.apply(lambda r: _geo_bus_transformer(r), axis=1)
    net.line_geodata.coords = net.line_geodata.coords.apply(lambda r: _geo_line_transformer(r))
    net.bus_geodata.attrs = {"crs": f"EPSG:{epsg_out}"}
    net.line_geodata.attrs = {"crs": f"EPSG:{epsg_out}"}


def dump_to_geojson(net, nodes=False, branches=False):
    """
    Dumps all primitive values from bus, bus_geodata, res_bus, line, line_geodata and res_line into a geojson object.
    It is recommended to only dump networks using WGS84 for GeoJSON specification compliance.

    :param net: The pandapower network
    :type net: pandapowerNet
    :param nodes: if True return contains all bus data, can be a list of bus ids that should be contained
    :type nodes: bool | list, default True
    :param branches: if True return contains all line data, can be a list of line ids that should be contained
    :type branches: bool | list, default True
    :return: geojson
    :return type: geojson.FeatureCollection
    """
    if not geojson_INSTALLED:
        soft_dependency_error(str(sys._getframe().f_code.co_name) + "()", "geojson")

    features = []
    # build geojson features for nodes
    if nodes:
        props = {}
        for table in ['bus', 'res_bus']:
            cols = net[table].columns
            # I use uid for the id of the feature, but it is NOT a unique identifier in the geojson structure,
            # as line and bus can have same ids.
            for uid, row in net[table].iterrows():
                prop = {
                    'pp_type': 'bus',
                    'pp_index': uid,
                }
                for c in cols:
                    try:
                        prop[c] = float(row[c])
                        if math.isnan(prop[c]):
                            prop[c] = None
                    except (ValueError, TypeError):
                        prop[c] = str(row[c])
                if uid not in props:
                    props[uid] = {}
                props[uid].update(prop)
        if isinstance(nodes, bool):
            iterator = net.bus_geodata.iterrows()
        else:
            iterator = net.bus_geodata.loc[nodes].iterrows()
        for uid, row in iterator:
            if row.coords is not None and not pd.isna(row.coords):
                # [(x, y), (x2, y2)] start and end of bus bar
                geom = geojson.LineString(row.coords)
            else:
                # this is just a bus with x, y
                geom = geojson.Point((row.x, row.y))
            features.append(geojson.Feature(geometry=geom, id=uid, properties=props[uid]))

    # build geojson features for branches
    if branches:
        props = {}
        for table in ['line', 'res_line']:
            cols = net[table].columns
            for uid, row in net[table].iterrows():
                prop = {
                    'pp_type': 'line',
                    'pp_index': uid,
                }
                for c in cols:
                    try:
                        prop[c] = float(row[c])
                        if math.isnan(prop[c]):
                            prop[c] = None
                    except (ValueError, TypeError):
                        prop[c] = str(row[c])
                if uid not in props:
                    props[uid] = {}
                props[uid].update(prop)
        if isinstance(branches, bool):
            iterator = net.line_geodata.iterrows()
        else:
            iterator = net.line_geodata.loc[branches].iterrows()
        for uid, row in iterator:
            geom = geojson.LineString(row.coords)
            features.append(geojson.Feature(geometry=geom, id=uid, properties=props[uid]))
    # find and set crs if available
    crs_bus = None
    if nodes and "crs" in net.bus_geodata.attrs:
        crs_bus = net.bus_geodata.attrs["crs"]
    crs_line = None
    if branches and "crs" in net.line_geodata.attrs:
        crs_line = net.line_geodata.attrs["crs"]
    crs = {
        "type": "name",
        "properties": {
            "name": ""
        }
    }
    if crs_bus:
        if crs_line and crs_line != crs_bus:
            raise ValueError("Bus and Line crs mismatch")
        crs["properties"]["name"] = crs_bus
    elif crs_line:
        crs["properties"]["name"] = crs_line
    else:
        crs = None
    if crs:
        return geojson.FeatureCollection(features, crs=crs)
    return geojson.FeatureCollection(features)
