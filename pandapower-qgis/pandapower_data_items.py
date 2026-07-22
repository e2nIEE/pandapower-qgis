# -*- coding: utf-8 -*-
"""Browser tree items for pandapower networks.

A pandapower ``.json`` found anywhere in the Browser expands into its tables,
so the network can be explored like a database rather than imported:

    mv_oberrhein.json
    ├── bus
    │   ├── 20.0 kV
    │   └── 110.0 kV
    ├── line
    │   └── 20.0 kV
    ├── trafo                (attribute-only table)
    ├── load
    └── Results
        ├── res_bus
        └── res_line         (greyed out until a power flow has run)

There is no saved-connection layer: networks are discovered as files in the
normal Home/Directory tree, the way GeoPackage behaves.

See docs/dataprovider_v2_plan.md sections 3.2 and 5.2.
"""

import os

from qgis.core import Qgis, QgsDataCollectionItem, QgsDataItemProvider, \
    QgsLayerItem, QgsMimeDataUtils
from qgis.PyQt.QtGui import QIcon

# The sip module moved into the PyQt package; a bare "import sip" fails on a
# modern PyQt5. qgis.PyQt.sip is the shim QGIS itself uses.
try:
    from qgis.PyQt import sip
except ImportError:  # pragma: no cover - very old PyQt
    import sip

from .network_session import KIND_PIPES, KIND_POWER, NetworkSession
from .pandapower_layer_factory import PROVIDER_KEY, build_uri
from .pandapower_uri import LEVELLED_TABLES, has_geometry, layer_name_for

# Markers identifying a pandapower / pandapipes JSON. Both are checked so that
# pipe networks appear in the tree once pandapipes is integrated (plan 5.4).
POWER_MARKER = '"pandapowerNet"'
PIPES_MARKER = '"pandapipesNet"'

# How much of a candidate file to read when sniffing. The Browser calls
# createDataItem() for every .json in every directory the user expands, so this
# must stay a bounded read - never a full parse.
SNIFF_BYTES = 8192

# Tables never shown as their own item: geodata is exposed through the geometry
# of bus/line, and the private bookkeeping tables are noise.
HIDDEN_TABLES = frozenset({
    'bus_geodata', 'line_geodata', 'junction_geodata', 'pipe_geodata',
    'std_types', 'parameters', 'user_pf_options', 'OPF_converged',
    'converged', 'version', 'format_version', 'name', 'f_hz', 'sn_mva',
})


def sniff_network_kind(path):
    """Cheaply decide whether a file is a pandapower or pandapipes network.

    Reads a bounded prefix rather than parsing, because this runs for every
    ``.json`` in every directory the user expands in the Browser.

    Args:
        path: Path of the candidate file.
    Returns:
        str or None: KIND_POWER, KIND_PIPES, or None if it is neither.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as handle:
            head = handle.read(SNIFF_BYTES)
    except OSError:
        return None

    if POWER_MARKER in head:
        return KIND_POWER
    if PIPES_MARKER in head:
        return KIND_PIPES
    return None


def _icon(name):
    """Load a plugin icon by file name.

    Args:
        name: File name inside the plugin directory, e.g. 'pp.svg'.
    Returns:
        QIcon: The icon, or an empty QIcon when the file is missing.
    """
    path = os.path.join(os.path.dirname(__file__), name)
    return QIcon(path) if os.path.exists(path) else QIcon()


def _release_to_cpp(items_):
    """Hand freshly created browser items over to C++ ownership.

    Items returned to the browser model must be constructed with **no parent**:
    QgsDataItem's documentation says "Children are not expected to have parent
    set", and QGIS parents them itself. Setting the parent up front makes it
    happen twice and crashes QGIS when the tree is expanded.

    The items are also Python subclasses. Two failure modes have to be avoided
    at once, and ``sip.transferto(item, None)`` avoids both:

    * If Python keeps owning the wrapper, it may be garbage collected while the
      browser model still points at the C++ object — a use-after-free.
    * If Python keeps a *reference* to guard against that, the wrapper instead
      outlives the C++ object QGIS deletes, and the mismatch corrupts the heap
      at collection time.

    Transferring ownership to C++ (``None`` target) makes sip stop tracking the
    wrapper's lifetime entirely: the object lives and dies with its C++ owner,
    exactly like the items a C++ provider returns, and the Python subclass
    behaviour is preserved for as long as that object exists.

    Args:
        items_: The items about to be returned to the browser model.
    Returns:
        The same list, for use as ``return _release_to_cpp(items_)``.
    """
    for item in items_:
        sip.transferto(item, None)
    return items_


def list_tables(net):
    """List the pandapower tables worth showing, derived from the net itself.

    Derived rather than hardcoded, so pandapipes tables appear for free once
    pipe networks are supported (plan section 5.4).

    Only **populated** input tables are listed. A pandapower 3 network defines
    around 33 input tables but a typical grid fills fewer than ten; listing the
    rest would bury the useful ones under empty DC and asymmetric tables.
    Result tables are returned whether populated or not, because an empty
    ``res_*`` is shown greyed out to advertise that a power flow can be run
    (plan section 5.2).

    Args:
        net: A loaded pandapower/pandapipes network.
    Returns:
        tuple: (input_tables, result_tables), each a sorted list of names.
    """
    import pandas as pd

    inputs = []
    results = []

    for name in dir(net):
        if name.startswith('_') or name in HIDDEN_TABLES:
            continue
        try:
            value = getattr(net, name)
        except Exception:
            continue
        if not isinstance(value, pd.DataFrame):
            continue
        if name.startswith('res_'):
            results.append(name)
        elif len(value) > 0:
            inputs.append(name)

    # Keep only the result tables whose input table is actually present. A
    # res_ssc for an empty ssc table can never hold anything.
    populated = set(inputs)
    results = [name for name in results if name[4:] in populated]

    # Show the geometry-bearing tables first: they are what most users open.
    def input_key(name):
        return (name not in LEVELLED_TABLES, name)

    return sorted(inputs, key=input_key), sorted(results)


def table_levels(net, table):
    """List the voltage or pressure levels a table can be split by.

    Args:
        net: A loaded network.
        table: Table name, e.g. 'bus' or 'line'.
    Returns:
        list: Sorted level values, empty when the table has no level column.
    """
    try:
        if table in ('bus', 'line'):
            column = 'vn_kv'
        elif table in ('junction', 'pipe'):
            column = 'pn_bar'
        else:
            return []

        df = getattr(net, table, None)
        if df is None or df.empty or column not in df.columns:
            return []
        return sorted(df[column].dropna().unique().tolist())
    except Exception:
        return []


class PandapowerTableItem(QgsLayerItem):
    """A single pandapower table, addable to the project as a layer."""

    def __init__(self, parent, name, path, table, level=None, epsg=None,
                 enabled=True):
        """Initialise the item.

        Args:
            parent: Parent QgsDataItem.
            name: Display name.
            path: Path of the network file.
            table: pandapower table name.
            level: Voltage or pressure level, or None for the whole table.
            epsg: EPSG code of the geodata.
            enabled: False renders the item greyed out, for an empty res_*
                table that has no rows until a power flow has run.
        """
        uri = build_uri(path, table, level=level, epsg=epsg)

        if has_geometry(table):
            layer_type = (Qgis.BrowserLayerType.Point
                          if table in ('bus', 'junction')
                          else Qgis.BrowserLayerType.Line)
        else:
            layer_type = Qgis.BrowserLayerType.TableLayer

        super().__init__(parent, name, '{}|{}'.format(path, name), uri,
                         layer_type, PROVIDER_KEY)

        self.file_path = path
        self.table = table
        self.level = level
        self.epsg = epsg
        self.enabled = enabled

    def layerName(self):
        """Name the added layer should carry.

        Returns:
            str: Layer name derived from the file, table and level.
        """
        return layer_name_for(self.file_path, self.table, self.level)

    def hasDragEnabled(self):
        """Whether the item can be dragged onto the canvas.

        An empty result table has nothing to show, so dragging is disabled.

        Returns:
            bool: True when the item is enabled.
        """
        return self.enabled

    def mimeUris(self):
        """URIs handed to QGIS when the item is dragged or double-clicked.

        Returns:
            list: A single QgsMimeDataUtils.Uri, or none when disabled.
        """
        if not self.enabled:
            return []

        uri = QgsMimeDataUtils.Uri()
        uri.layerType = 'vector'
        uri.providerKey = PROVIDER_KEY
        uri.name = self.layerName()
        uri.uri = self.uri()
        return [uri]


class PandapowerLevelledTableItem(QgsDataCollectionItem):
    """A table that expands into one child per voltage or pressure level."""

    def __init__(self, parent, name, path, table, levels, epsg=None):
        """Initialise the item.

        Args:
            parent: Parent QgsDataItem.
            name: Display name, e.g. 'bus'.
            path: Path of the network file.
            table: pandapower table name.
            levels: Level values to create children for.
            epsg: EPSG code of the geodata.
        """
        super().__init__(parent, name, '{}|{}'.format(path, name),
                         PROVIDER_KEY)
        self.file_path = path
        self.table = table
        self.levels = levels
        self.epsg = epsg
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.Fertile |
                               Qgis.BrowserItemCapability.Fast)

    def createChildren(self):
        """Build one child item per level.

        Returns:
            list: PandapowerTableItem instances.
        """
        unit = 'kV' if self.table in ('bus', 'line') else 'bar'
        children = []
        for level in self.levels:
            children.append(PandapowerTableItem(
                None, '{} {}'.format(level, unit), self.file_path,
                self.table, level=level, epsg=self.epsg))
        return _release_to_cpp(children)


class PandapowerResultsItem(QgsDataCollectionItem):
    """Groups the res_* tables so the top level of the tree stays readable."""

    def __init__(self, parent, path, tables, epsg=None, has_results=False):
        """Initialise the item.

        Args:
            parent: Parent QgsDataItem.
            path: Path of the network file.
            tables: Sequence of (table_name, row_count) pairs.
            epsg: EPSG code of the geodata.
            has_results: Whether any result table holds rows.
        """
        super().__init__(parent, 'Results', '{}|Results'.format(path),
                         PROVIDER_KEY)
        self.file_path = path
        self.tables = list(tables)
        self.epsg = epsg
        self.has_results = has_results
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.Fertile |
                               Qgis.BrowserItemCapability.Fast)

    def createChildren(self):
        """Build one child per result table.

        Empty tables are still listed, greyed out, so the user can see that
        running a power flow is possible (plan section 5.2).

        Returns:
            list: PandapowerTableItem instances.
        """
        children = []
        for table, row_count in self.tables:
            item = PandapowerTableItem(
                None, table, self.file_path, table, epsg=self.epsg,
                enabled=row_count > 0)
            if row_count == 0:
                item.setToolTip('No results yet - run a power flow')
            children.append(item)
        return _release_to_cpp(children)


class PandapowerNetworkItem(QgsDataCollectionItem):
    """A pandapower network file, expandable into its tables."""

    def __init__(self, parent, name, path, kind=KIND_POWER):
        """Initialise the item.

        Args:
            parent: Parent QgsDataItem.
            name: Display name, normally the file name.
            path: Path of the network file.
            kind: KIND_POWER or KIND_PIPES.
        """
        super().__init__(parent, name, path, PROVIDER_KEY)
        self.file_path = path
        self.kind = kind
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.Fertile |
                               Qgis.BrowserItemCapability.ItemRepresentsFile)
        self.setIcon(_icon('pp.svg'))

    def _acquire_session(self):
        """Open (or join) the session for this file.

        Returns:
            NetworkSession or None: The session, or None if loading failed.
        """
        from .pandapower_provider import PandapowerProvider

        try:
            return NetworkSession.acquire(
                self.file_path,
                lambda: PandapowerProvider._load_network_from_file(
                    self.file_path, self.kind),
                kind=self.kind)
        except Exception as error:
            print('Could not open pandapower network {}: {}'.format(
                self.file_path, error))
            return None

    def createChildren(self):
        """Build the table items for this network.

        Loading the network is unavoidable here, so it goes through
        NetworkSession: the same load then serves any layer the user opens.

        Returns:
            list: Child items, or an empty list when the file cannot be read.
        """
        session = self._acquire_session()
        if session is None:
            return []

        try:
            net = session.net
            epsg = session.epsg
            inputs, results = list_tables(net)

            children = []
            for table in inputs:
                levels = table_levels(net, table)
                if len(levels) > 1:
                    # Split into one child per level only when there is more
                    # than one; a single level would add a pointless nesting.
                    children.append(PandapowerLevelledTableItem(
                        None, table, self.file_path, table, levels, epsg))
                else:
                    children.append(PandapowerTableItem(
                        None, table, self.file_path, table,
                        level=levels[0] if levels else None, epsg=epsg))

            if results:
                counts = []
                for table in results:
                    df = getattr(net, table, None)
                    counts.append((table, 0 if df is None else len(df)))
                children.append(PandapowerResultsItem(
                    None, self.file_path, counts, epsg,
                    has_results=any(count for _, count in counts)))

            return _release_to_cpp(children)
        finally:
            # createChildren() only needed the network to enumerate tables; the
            # reference is dropped so the session lives exactly as long as the
            # layers that actually use it.
            session.release()


class PandapowerDataItemProvider(QgsDataItemProvider):
    """Registers pandapower networks as expandable items in the Browser."""

    def name(self):
        """Provider name shown in QGIS.

        Returns:
            str: Provider name.
        """
        return 'pandapower'

    def dataProviderKey(self):
        """Key of the data provider that opens these items.

        Returns:
            str: Provider key.
        """
        return PROVIDER_KEY

    def capabilities(self):
        """Kinds of browser entries this provider handles.

        Returns:
            Qgis.DataItemProviderCapabilities: Files.
        """
        return Qgis.DataItemProviderCapability.Files

    def createDataItem(self, path, parentItem):
        """Create a browser item for a candidate file.

        Args:
            path: Path of the file the Browser is offering.
            parentItem: Parent item in the tree.
        Returns:
            PandapowerNetworkItem or None: An item for pandapower networks,
                None for every other file.
        """
        if not path or not path.lower().endswith('.json'):
            return None

        kind = sniff_network_kind(path)
        if kind is None:
            return None

        return PandapowerNetworkItem(
            parentItem, os.path.basename(path), path, kind)
