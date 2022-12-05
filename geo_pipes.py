# -*- coding: utf-8 -*-
"""
this code should be summited as PR to e2nIEE/pandapipes
when the PR has been merged this file should be removed and its call replaced in ppqgis.py

https://github.com/e2nIEE/pandapipes/blob/develop/pandapipes/plotting/geo.py
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
    Converts junction and pipe geodata in net from epsg_in to epsg_out
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

    def _geo_junction_transformer(r):
        (x, y) = transformer.transform(r.x, r.y)
        return pd.Series([x, y], ["x", "y"])

    def _geo_pipe_transformer(r):
        return list(transformer.itransform(r))

    net.junction_geodata = net.junction_geodata.apply(lambda r: _geo_junction_transformer(r), axis=1)
    net.pipe_geodata.coords = net.pipe_geodata.coords.apply(lambda r: _geo_pipe_transformer(r))
    net.junction_geodata.attrs = {"crs": f"EPSG:{epsg_out}"}
    net.pipe_geodata.attrs = {"crs": f"EPSG:{epsg_out}"}


# TODO: It should be possible to rewrite this to support pandapower AND pandapipes
def dump_to_geojson(net, nodes=False, branches=False):
    """
    Dumps all primitive values from junction, junction_geodata, res_junction, pipe, pipe_geodata and res_pipe into a geojson object.
    It is recommended to only dump networks using WGS84 for GeoJSON specification compliance.

    :param net: The pandapipes network
    :type net: pandapipesNet
    :param nodes: if True return contains all junction data, can be a list of junction ids that should be contained
    :type nodes: bool | list, default True
    :param branches: if True return contains all pipe data, can be a list of pipe ids that should be contained
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
        for table in ['junction', 'res_junction']:
            if table not in net.keys():
                continue
            cols = net[table].columns
            # I use uid for the id of the feature, but it is NOT a unique identifier in the geojson structure,
            # as pipe and junction can have same ids.
            for uid, row in net[table].iterrows():
                prop = {
                    'pp_type': 'junction',
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
            iterator = net.junction_geodata.iterrows()
        else:
            iterator = net.junction_geodata.loc[nodes].iterrows()
        for uid, row in iterator:
            geom = geojson.Point((row.x, row.y))
            features.append(geojson.Feature(geometry=geom, id=uid, properties=props[uid]))

    # build geojson features for branches
    if branches:
        props = {}
        for table in ['pipe', 'res_pipe']:
            if table not in net.keys():
                continue
            cols = net[table].columns
            for uid, row in net[table].iterrows():
                prop = {
                    'pp_type': 'pipe',
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

        # Iterating over pipe_geodata won't work
        # pipe_geodata only contains pipes that have inflection points!
        if isinstance(branches, bool):
            # if all iterating over pipe
            iterator = net.pipe.iterrows()
        else:
            iterator = net.pipe.loc[branches].iterrows()
        for uid, row in iterator:
            coords = []
            from_coords = net.junction_geodata.loc[row.from_junction]
            to_coords = net.junction_geodata.loc[row.to_junction]
            coords.append([float(from_coords.x), float(from_coords.y)])
            if uid in net.pipe_geodata:
                coords.append(net.pipe_geodata.loc[uid].coords)
            coords.append([float(to_coords.x), float(to_coords.y)])

            geom = geojson.LineString(coords)
            features.append(geojson.Feature(geometry=geom, id=uid, properties=props[uid]))
    # find and set crs if available
    crs_junction = None
    if nodes and "crs" in net.junction_geodata.attrs:
        crs_junction = net.junction_geodata.attrs["crs"]
    crs_pipe = None
    if branches and "crs" in net.pipe_geodata.attrs:
        crs_pipe = net.pipe_geodata.attrs["crs"]
    crs = {
        "type": "name",
        "properties": {
            "name": ""
        }
    }
    if crs_junction:
        if crs_pipe and crs_pipe != crs_junction:
            raise ValueError("junction and pipe crs mismatch")
        crs["properties"]["name"] = crs_junction
    elif crs_pipe:
        crs["properties"]["name"] = crs_pipe
    else:
        crs = None
    if crs:
        return geojson.FeatureCollection(features, crs=crs)
    return geojson.FeatureCollection(features)
