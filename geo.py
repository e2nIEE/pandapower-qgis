"""
this code is part of PR #1731 at e2nIEE/pandapower
when the PR has been merged this file should be removed and its call replaced in pandapower_qgis.py

https://github.com/e2nIEE/pandapower/blob/develop/pandapower/plotting/geo.py
"""

import sys
import pandas as pd
from pandapower.auxiliary import soft_dependency_error
from shapely.geometry import Point, LineString
import math

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


def dump_to_geojson(net, epsg_in=4326, epsg_out=4326, node=True, branch=True):
    """
    Dumps all primitive values from bus, bus_geodata, res_bus, line, line_geodata and res_line into a geojson object.
    :param net: The pandapower network
    :type net: pandapowerNet
    :param epsg: current epsg projection
    :type epsg: int, default 4326 (= WGS84)
    :param node: flag if return contains the bus data
    :type node: bool, default True
    :param branch: flag if return contains the line data
    :type branch: bool, default True
    :return: geojson
    :return type: geojson.FeatureCollection
    """
    if not geojson_INSTALLED:
        soft_dependency_error(str(sys._getframe().f_code.co_name)+"()", "geojson")

    if epsg_in != epsg_out:
        if not pyproj_INSTALLED:
            soft_dependency_error(str(sys._getframe().f_code.co_name)+"()", "pyproj")

        transformer = Transformer.from_crs(epsg_in, epsg_out)

    features = []
    # build geojson features for nodes
    if node:
        props = {}
        for table in ['bus', 'res_bus']:
            cols = net[table].columns
            # I use uid for the id of the feature, but it is NOT a unique identifier in the geojson structure,
            # as line and bus can have same ids.
            for uid, row in net[table].iterrows():
                prop = {}
                prop['pp_index'] = uid
                for c in cols:
                    try:
                        prop[c] = float(row[c])
                        if math.isnan(prop[c]):
                            prop[c] = -1.
                    except (ValueError, TypeError):
                        prop[c] = str(row[c])
                if uid not in props:
                    props[uid] = {}
                props[uid].update(prop)
        # props = net.bus.to_dict(orient='records')

        if epsg_in != epsg_out:
            def geo_transformer(x):
                d = transformer.transform(x[1], x[0])
                return pd.Series([d[1], d[0], Point(d[1], d[0]), x[3]])

            new = net.bus_geodata.apply(lambda x: geo_transformer(x), axis=1)
            new.columns = ["x", "y", "geometry", "coords"]
            net.bus_geodata = new

        for uid, row in net.bus_geodata.iterrows():
            if row.coords is not None:
                # [(x, y), (x2, y2)] start and end of bus bar
                geom = geojson.LineString(row.coords)
            else:
                # this is just a bus with x, y
                geom = geojson.Point((row.x, row.y))

            features.append(geojson.Feature(geometry=geom, id=uid, properties=props[uid]))

    # build geojson features for branches
    if branch:
        if epsg_in != epsg_out:
            def geo_line_transformer(x):
                ret = []
                for y in x:
                    d = transformer.transform(y[1], y[0])
                    ret.append([d[1], d[0]])
                # return pd.Series(ret, LineString(ret))
                # return pd.Series(ret, x[1])
                return ret

            net.line_geodata.coords = net.line_geodata.coords.apply(lambda x: geo_line_transformer(x))
            net.line_geodata.geometry = net.line_geodata.coords.apply(lambda x: LineString(x))

        props = {}
        for table in ['line', 'res_line']:
            cols = net[table].columns
            for uid, row in net[table].iterrows():
                prop = {}
                prop['pp_index'] = uid
                for c in cols:
                    try:
                        prop[c] = float(row[c])
                        if math.isnan(prop[c]):
                            prop[c] = -1.
                    except (ValueError, TypeError):
                        prop[c] = str(row[c])
                if uid not in props:
                    props[uid] = {}
                props[uid].update(prop)
        # props = net.line.to_dict(orient='records')

        for uid, row in net.line_geodata.iterrows():
            coords = row.coords
            geom = geojson.LineString(coords)
            features.append(geojson.Feature(geometry=geom, id=uid, properties=props[uid]))

    return geojson.FeatureCollection(features)