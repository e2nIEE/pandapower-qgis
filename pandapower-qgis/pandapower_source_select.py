# -*- coding: utf-8 -*-
"""The "pandapower" entry in the Data Source Manager.

Puts pandapower alongside PostgreSQL, SAP HANA and Oracle in the left-hand list
of the Data Source Manager, so a network is opened as a data source rather than
imported. Pick a ``.json``, see what tables it holds, select some, press Add.

See docs/dataprovider_v2_plan.md section 3.1.
"""

import os

from qgis.core import Qgis, QgsProviderRegistry
from qgis.gui import QgsAbstractDataSourceWidget, QgsSourceSelectProvider
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                                 QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                                 QPushButton, QTableWidget, QTableWidgetItem,
                                 QVBoxLayout)

from .network_session import KIND_POWER, NetworkSession
from .pandapower_data_items import list_tables, sniff_network_kind, table_levels
from .pandapower_layer_factory import PROVIDER_KEY
from .pandapower_uri import geometry_type_for, has_geometry, layer_name_for

# QSettings key under which recently opened networks are remembered.
RECENT_KEY = 'pandapower-qgis/recentNetworks'
MAX_RECENT = 10

# Columns of the table listing.
COL_TABLE = 0
COL_GEOMETRY = 1
COL_LEVEL = 2
COL_FEATURES = 3


def _plugin_icon():
    """Load the plugin icon.

    Returns:
        QIcon: The pandapower icon, or an empty one when the file is missing.
    """
    from qgis.PyQt.QtGui import QIcon

    path = os.path.join(os.path.dirname(__file__), 'pp.svg')
    return QIcon(path) if os.path.exists(path) else QIcon()


def recent_networks():
    """Return the recently opened network paths that still exist.

    Returns:
        list: Absolute paths, most recent first.
    """
    stored = QSettings().value(RECENT_KEY, []) or []
    if isinstance(stored, str):
        stored = [stored]
    return [path for path in stored if os.path.exists(path)]


def remember_network(path):
    """Record a network as recently opened.

    Args:
        path: Path of the network file.
    """
    recent = [entry for entry in recent_networks()
              if os.path.normcase(entry) != os.path.normcase(path)]
    recent.insert(0, path)
    QSettings().setValue(RECENT_KEY, recent[:MAX_RECENT])


def describe_tables(net):
    """Describe a network's contents for display in the listing.

    Each geometry table is expanded into one row per voltage level, so the
    listing mirrors what the Browser tree shows.

    Args:
        net: A loaded pandapower network.
    Returns:
        list: Dicts with 'table', 'level', 'geometry' and 'features' keys.
    """
    inputs, results = list_tables(net)
    rows = []

    for table in inputs:
        levels = table_levels(net, table)
        df = getattr(net, table, None)
        geometry = geometry_type_for(table)

        if len(levels) > 1:
            for level in levels:
                rows.append({
                    'table': table,
                    'level': level,
                    'geometry': geometry,
                    'features': _count_at_level(net, table, level),
                })
        else:
            rows.append({
                'table': table,
                'level': levels[0] if levels else None,
                'geometry': geometry,
                'features': 0 if df is None else len(df),
            })

    for table in results:
        df = getattr(net, table, None)
        rows.append({
            'table': table,
            'level': None,
            'geometry': geometry_type_for(table),
            'features': 0 if df is None else len(df),
        })

    return rows


def _count_at_level(net, table, level):
    """Count the rows of a table belonging to one voltage level.

    Args:
        net: A loaded pandapower network.
        table: Table name, 'bus' or 'line'.
        level: The voltage level.
    Returns:
        int: Number of rows, 0 when it cannot be determined.
    """
    try:
        df = getattr(net, table)
        if table in ('bus', 'junction'):
            column = 'vn_kv' if table == 'bus' else 'pn_bar'
            return int((df[column] == level).sum())

        # A line belongs to the level of its from_bus.
        bus = net.bus
        indices = bus[bus['vn_kv'] == level].index
        return int(df['from_bus'].isin(indices).sum())
    except Exception:
        return 0


class PandapowerSourceSelectWidget(QgsAbstractDataSourceWidget):
    """Lets the user pick a network file and add tables from it as layers."""

    def __init__(self, parent=None, fl=Qt.Widget, widgetMode=None):
        """Initialise the widget.

        Args:
            parent: Parent widget.
            fl: Window flags.
            widgetMode: QgsProviderRegistry.WidgetMode.
        """
        if widgetMode is None:
            widgetMode = QgsProviderRegistry.WidgetMode.Standalone
        super().__init__(parent, fl, widgetMode)

        self.setWindowTitle('Add pandapower Layer(s)')
        self.path = None
        self.rows = []

        self._build_ui()
        self._load_recent()

    def _build_ui(self):
        """Construct the widget layout."""
        layout = QVBoxLayout(self)

        # File chooser row
        chooser = QHBoxLayout()
        chooser.addWidget(QLabel('Network:'))

        self.file_combo = QComboBox()
        self.file_combo.setEditable(True)
        self.file_combo.setMinimumWidth(360)
        self.file_combo.activated.connect(self._on_recent_chosen)
        chooser.addWidget(self.file_combo, 1)

        browse = QPushButton('Browse...')
        browse.clicked.connect(self._browse)
        chooser.addWidget(browse)

        layout.addLayout(chooser)

        # Table listing
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ['Table', 'Geometry', 'Level', 'Features'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            COL_TABLE, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table, 1)

        # Quick selection. Opening a whole network is the common case, so it
        # gets a button rather than requiring the user to rubber-band the list.
        buttons = QHBoxLayout()

        select_all = QPushButton('Select all')
        select_all.clicked.connect(self.table.selectAll)
        buttons.addWidget(select_all)

        select_map = QPushButton('Select map layers')
        select_map.setToolTip(
            'Select only the tables that carry geometry (bus, line)')
        select_map.clicked.connect(self.select_geometry_tables)
        buttons.addWidget(select_map)

        # Adds every selected table at once. The dialog's own Add button is not
        # always wired up when the widget is embedded in the Data Source
        # Manager, and double-clicking a row collapses the selection to that
        # single row first, so neither reliably adds a multi-row selection.
        self.add_button = QPushButton('Add selected')
        self.add_button.setToolTip('Add every selected table as a layer')
        self.add_button.setDefault(True)
        self.add_button.clicked.connect(self.addButtonClicked)
        buttons.addWidget(self.add_button)

        buttons.addStretch(1)

        self.group_checkbox = QCheckBox('Add layers in a group named after the network')
        self.group_checkbox.setChecked(True)
        buttons.addWidget(self.group_checkbox)

        layout.addLayout(buttons)

        self.status = QLabel('Choose a pandapower network file.')
        layout.addWidget(self.status)

    def _load_recent(self):
        """Populate the file combo with recently opened networks."""
        self.file_combo.clear()
        self.file_combo.addItem('')
        for path in recent_networks():
            self.file_combo.addItem(path)
        self.file_combo.setCurrentIndex(0)

    # -- file selection ---------------------------------------------------

    def _browse(self):
        """Open a file dialog and load the chosen network."""
        start = os.path.dirname(self.path) if self.path else ''
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open pandapower network', start,
            'pandapower networks (*.json);;All files (*.*)')
        if path:
            self.file_combo.setEditText(path)
            self.load_network(path)

    def _on_recent_chosen(self, index):
        """Load the network picked from the recent list.

        Args:
            index: Index chosen in the combo box.
        """
        path = self.file_combo.itemText(index)
        if path:
            self.load_network(path)

    def load_network(self, path):
        """Load a network and list its tables.

        Args:
            path: Path of the network file.
        Returns:
            bool: True when the network was listed.
        """
        if not path or not os.path.exists(path):
            self._set_status('File not found: {}'.format(path), error=True)
            self._clear_listing()
            return False

        kind = sniff_network_kind(path)
        if kind is None:
            self._set_status(
                'Not a pandapower network: {}'.format(os.path.basename(path)),
                error=True)
            self._clear_listing()
            return False

        session = None
        try:
            from .pandapower_provider import PandapowerProvider

            session = NetworkSession.acquire(
                path,
                lambda: PandapowerProvider._load_network_from_file(path, kind),
                kind=kind)
            self.rows = describe_tables(session.net)
            self.epsg = session.epsg
        except Exception as error:
            self._set_status('Could not read network: {}'.format(error),
                             error=True)
            self._clear_listing()
            return False
        finally:
            # The listing only needed the network to enumerate tables. Any
            # layer the user adds re-acquires the session for itself.
            if session is not None:
                session.release()

        self.path = path
        remember_network(path)
        self._populate_listing()
        # Preselect the geometry tables: opening a network to see it on the map
        # is the common case, so Add works straight away.
        self.select_geometry_tables()
        self._set_status('{} table(s) in {}. Press Add to open the selected '
                         'ones.'.format(len(self.rows), os.path.basename(path)))
        return True

    # -- listing ----------------------------------------------------------

    def _clear_listing(self):
        """Empty the table listing."""
        self.rows = []
        self.table.setRowCount(0)

    def _populate_listing(self):
        """Fill the table listing from the current network."""
        self.table.setRowCount(len(self.rows))

        for index, row in enumerate(self.rows):
            name = QTableWidgetItem(row['table'])
            geometry = QTableWidgetItem(
                '' if row['geometry'] == 'None' else row['geometry'])
            level = QTableWidgetItem(
                '' if row['level'] is None else str(row['level']))
            features = QTableWidgetItem(str(row['features']))
            features.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # An empty result table holds nothing to show, so the row is greyed
            # out and made unselectable. "Select all" therefore skips it, which
            # is intended: adding it would produce an empty layer.
            if row['table'].startswith('res_') and row['features'] == 0:
                for item in (name, geometry, level, features):
                    item.setFlags(Qt.NoItemFlags)
                    item.setToolTip('No results yet - run a power flow first')
                name.setText('{}  (no results)'.format(row['table']))

            self.table.setItem(index, COL_TABLE, name)
            self.table.setItem(index, COL_GEOMETRY, geometry)
            self.table.setItem(index, COL_LEVEL, level)
            self.table.setItem(index, COL_FEATURES, features)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            COL_TABLE, QHeaderView.Stretch)

    def _on_row_double_clicked(self, index):
        """Add the double-clicked table.

        Qt collapses the selection to the clicked row before the double-click
        arrives, so this adds exactly that one table. Use "Add selected" to add
        a multi-row selection.

        Args:
            index: QModelIndex of the row that was double-clicked.
        """
        if not index.isValid() or not self.path:
            return

        row = index.row()
        if 0 <= row < len(self.rows):
            self._add_rows([self.rows[row]])

    def select_geometry_tables(self):
        """Select every row whose table carries geometry.

        These are the layers that actually show up on the map, and are what
        most users want when opening a network.
        """
        from qgis.PyQt.QtCore import QItemSelection, QItemSelectionModel

        model = self.table.selectionModel()
        model.clearSelection()

        for index, row in enumerate(self.rows):
            if not has_geometry(row['table']):
                continue
            model.select(
                self.table.model().index(index, 0),
                QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def selected_rows(self):
        """Return the descriptions of the currently selected rows.

        Returns:
            list: Row dicts, in listing order.
        """
        indices = sorted({index.row()
                          for index in self.table.selectedIndexes()})
        return [self.rows[i] for i in indices if 0 <= i < len(self.rows)]

    # -- QgsAbstractDataSourceWidget ---------------------------------------

    def addButtonClicked(self):
        """Add every selected table to the project.

        Called both by the widget's own "Add selected" button and by the Data
        Source Manager's Add button.
        """
        if not self.path:
            self._set_status('Choose a network file first.', error=True)
            return

        selection = self.selected_rows()
        if not selection:
            self._set_status('Select at least one table.', error=True)
            return

        self._add_rows(selection)

    def _add_rows(self, rows):
        """Add the given tables to the project.

        Args:
            rows: Row dicts to add.
        """
        if self.group_checkbox.isChecked():
            self._add_layers_grouped(rows)
        else:
            self._add_layers_flat(rows)

    def _add_layers_grouped(self, selection):
        """Add the selected tables into a group named after the network.

        The layers are built and placed here rather than emitted as signals,
        because QGIS drops a signalled layer at the top of the tree and there
        is no reliable way to catch it again afterwards to group it.

        Args:
            selection: Row dicts to add.
        """
        from qgis.core import QgsProject
        from .pandapower_layer_factory import create_layer

        project = QgsProject.instance()
        group_name = os.path.basename(self.path).rsplit('.', 1)[0]

        root = project.layerTreeRoot()
        group = root.findGroup(group_name) or root.addGroup(group_name)

        added = 0
        failed = []
        for row in selection:
            layer = create_layer(
                self.path, row['table'], level=row['level'],
                epsg=getattr(self, 'epsg', None))
            if not layer.isValid():
                failed.append(row['table'])
                continue
            # addMapLayer(layer, False) keeps QGIS from putting it at the root,
            # so it can be placed inside the group instead.
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            added += 1

        if failed:
            self._set_status(
                'Added {} layer(s); could not open: {}'.format(
                    added, ', '.join(failed)), error=True)
        else:
            self._set_status('Added {} layer(s) to group "{}".'.format(
                added, group_name))

    def _add_layers_flat(self, selection):
        """Add the selected tables at the top level of the project.

        Args:
            selection: Row dicts to add.
        """
        from .pandapower_layer_factory import build_uri

        for row in selection:
            uri = build_uri(self.path, row['table'],
                            level=row['level'], epsg=getattr(self, 'epsg', None))
            name = layer_name_for(self.path, row['table'], row['level'])
            self._emit_add_layer(uri, name)

        self._set_status('Added {} layer(s).'.format(len(selection)))

    def _emit_add_layer(self, uri, name):
        """Ask QGIS to add one layer.

        The plan called for the modern ``addLayer(type, url, name, key)``
        signal, but emitting it from Python segfaults on QGIS 3.44: the
        Qgis::LayerType argument is not marshalled correctly, and the crash
        happens even with no receiver connected. Only C++ source selects emit
        it upstream, so the binding path is untested there.

        ``addVectorLayer`` is deprecated since 3.40 but works from Python and
        is what this widget only ever needs, since every pandapower table opens
        as a vector layer. Revisit once the binding is fixed.

        Args:
            uri: Layer URI.
            name: Layer display name.
        """
        self.addVectorLayer.emit(uri, name, PROVIDER_KEY)

    def reset(self):
        """Clear the selection when the dialog is reopened.

        The Data Source Manager recycles widgets, so this runs on every
        reopening.
        """
        self.table.clearSelection()
        self._load_recent()

    # -- helpers ----------------------------------------------------------

    def _set_status(self, message, error=False):
        """Show a status message under the listing.

        Args:
            message: Text to show.
            error: True to render it as a warning.
        """
        self.status.setText(message)
        self.status.setStyleSheet('color: #b00;' if error else '')


class PandapowerSourceSelectProvider(QgsSourceSelectProvider):
    """Registers the pandapower page of the Data Source Manager."""

    def providerKey(self):
        """Key of the data provider this page creates layers for.

        Returns:
            str: Provider key.
        """
        return PROVIDER_KEY

    def text(self):
        """Label shown in the Data Source Manager list.

        Returns:
            str: Menu entry text.
        """
        return 'pandapower'

    def toolTip(self):
        """Tooltip for the menu entry.

        Returns:
            str: Tooltip text.
        """
        return 'Open tables of a pandapower network'

    def icon(self):
        """Icon shown next to the menu entry.

        Returns:
            QIcon: The pandapower icon.
        """
        return _plugin_icon()

    def ordering(self):
        """Position in the Data Source Manager list.

        Places the entry in the database group, below the built-in database
        providers, so it sits alongside PostgreSQL, SAP HANA and Oracle.

        Returns:
            int: Sort key.
        """
        return QgsSourceSelectProvider.OrderDatabaseProvider + 100

    def createDataSourceWidget(self, parent=None, fl=Qt.Widget,
                               widgetMode=QgsProviderRegistry.WidgetMode.Embedded):
        """Create the page widget.

        Args:
            parent: Parent widget.
            fl: Window flags.
            widgetMode: Embedding mode requested by QGIS.
        Returns:
            PandapowerSourceSelectWidget: A new page instance.
        """
        return PandapowerSourceSelectWidget(parent, fl, widgetMode)
