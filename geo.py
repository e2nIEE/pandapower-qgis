"""
this code is part of PR #1731 at e2nIEE/pandapower
when the PR has been merged this file should be removed and its call replaced in pandapower_qgis.py

https://github.com/e2nIEE/pandapower/blob/develop/pandapower/plotting/geo.py
"""

import sys

from pandapower.auxiliary import soft_dependency_error

try:
    from pyproj import Proj, transform
    pyproj_INSTALLED = True
except ImportError:
    pyproj_INSTALLED = False

try:
    import geojson
    geojson_INSTALLED = True
except ImportError:
    geojson_INSTALLED = False


def _convert_xy_epsg(x, y, epsg_in=4326, epsg_out=31467):
    """
    Converts the given x and y coordinates according to the defined epsg projections.
    :param x: x-values of coordinates
    :type x: iterable
    :param y: y-values of coordinates
    :type y: iterable
    :param epsg_in: current epsg projection
    :type epsg_in: int, default 4326 (= WGS84)
    :param epsg_out: epsg projection to be transformed to
    :type epsg_out: int, default 31467 (= Gauss-Krüger Zone 3)
    :return: transformed_coords - x and y values in new coordinate system
    """
    if not pyproj_INSTALLED:
        soft_dependency_error(str(sys._getframe().f_code.co_name)+"()", "pyproj")
    in_proj = Proj(init='epsg:%i' % epsg_in)
    out_proj = Proj(init='epsg:%i' % epsg_out)
    return transform(in_proj, out_proj, x, y)


def dump_to_geojson(net, epsg=4326, node=True, branch=True):
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
                for c in cols:
                    try:
                        prop[c] = float(row[c])
                    except (ValueError, TypeError):
                        prop[c] = str(row[c])
                if uid not in props:
                    props[uid] = {}
                props[uid].update(prop)
        for uid, row in net.bus_geodata.iterrows():
            if row.coords is not None:
                # [(x, y), (x2, y2)] start and end of bus bar
                if epsg == 4326:
                    geom = geojson.LineString(row.coords)
                else:
                    [(x, y), (x2, y2)] = row.coords
                    geom = geojson.LineString([_convert_xy_epsg(x, y, epsg_in=epsg, epsg_out=4326),
                                               _convert_xy_epsg(x2, y2, epsg_in=epsg, epsg_out=4326)])
            else:
                # this is just a bus with x, y
                if epsg == 4326:
                    geom = geojson.Point((row.x, row.y))
                else:
                    geom = geojson.Point(_convert_xy_epsg(row.x, row.y, epsg_in=epsg, epsg_out=4326))
            features.append(geojson.Feature(geometry=geom, id=uid, properties=props[uid]))

    # build geojson features for branches
    if branch:
        props = {}
        for table in ['line', 'res_line']:
            cols = net[table].columns
            prop = {}
            for uid, row in net[table].iterrows():
                for c in cols:
                    try:
                        prop[c] = float(row[c])
                    except (ValueError, TypeError):
                        prop[c] = str(row[c])
                if uid not in props:
                    props[uid] = {}
                props[uid].update(prop)
        for uid, row in net.line_geodata.iterrows():
            coords = row.coords
            if not epsg == 4326:
                for i, [x, y] in enumerate(coords):
                    x2, y2 = _convert_xy_epsg(x, y, epsg_in=epsg, epsg_out=4326)
                    coords[i] = [x2, y2]
            geom = geojson.LineString(coords)
            features.append(geojson.Feature(geometry=geom, id=uid, properties=props[uid]))

    return geojson.FeatureCollection(features)