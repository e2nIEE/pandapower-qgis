# -*- coding: utf-8 -*-
"""Context menus and double-click handling for the pandapower browser items.

Kept separate from ``pandapower_data_items`` because the item classes live in
qgis.core while this needs qgis.gui: the data items must stay importable in a
headless context (tests, qgis_process) where the GUI classes are unavailable.

See docs/dataprovider_v2_plan.md section 3.2.
"""

from qgis.core import QgsProject
from qgis.gui import QgsDataItemGuiProvider
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .network_session import NetworkSession
from .pandapower_data_items import PandapowerNetworkItem, \
    PandapowerResultsItem, PandapowerTableItem
from .pandapower_layer_factory import create_layer


def _add_table_item_to_project(item):
    """Build the layer for a table item and add it to the project.

    Args:
        item: The PandapowerTableItem that was activated.
    Returns:
        bool: True when a valid layer was added.
    """
    layer = create_layer(
        item.file_path,
        item.table,
        level=item.level,
        epsg=item.epsg,
        name=item.layerName(),
    )
    if not layer.isValid():
        return False

    QgsProject.instance().addMapLayer(layer)
    return True


class PandapowerDataItemGuiProvider(QgsDataItemGuiProvider):
    """Supplies the Browser context menu for pandapower items."""

    def name(self):
        """Provider name shown in QGIS.

        Returns:
            str: Provider name.
        """
        return 'pandapower'

    def handleDoubleClick(self, item, context):
        """Open a table as a layer when it is double-clicked.

        Args:
            item: The double-clicked QgsDataItem.
            context: QgsDataItemGuiContext.
        Returns:
            bool: True when the double-click was handled here.
        """
        if not isinstance(item, PandapowerTableItem):
            return False

        if not item.enabled:
            # An empty result table: offer the power flow instead of opening
            # a table with no rows in it.
            self._offer_power_flow(item)
            return True

        return _add_table_item_to_project(item)

    def populateContextMenu(self, item, menu, selectedItems, context):
        """Add pandapower entries to the Browser context menu.

        Args:
            item: The QgsDataItem the menu is for.
            menu: QMenu to populate.
            selectedItems: All currently selected items.
            context: QgsDataItemGuiContext.
        """
        if isinstance(item, PandapowerNetworkItem):
            self._populate_network_menu(item, menu)
        elif isinstance(item, PandapowerTableItem):
            self._populate_table_menu(item, menu)
        elif isinstance(item, PandapowerResultsItem):
            self._populate_results_menu(item, menu)

    # -- menu builders ----------------------------------------------------

    def _populate_network_menu(self, item, menu):
        """Add the whole-network entries.

        Args:
            item: The PandapowerNetworkItem.
            menu: QMenu to populate.
        """
        add_all = QAction('Add all geometry layers to project', menu)
        add_all.triggered.connect(lambda: self._add_all_layers(item))
        menu.addAction(add_all)

        run_pf = QAction('Run power flow...', menu)
        run_pf.triggered.connect(lambda: self._run_power_flow(item.file_path))
        menu.addAction(run_pf)

        menu.addSeparator()

        save = QAction('Save network', menu)
        save.triggered.connect(lambda: self._save_network(item.file_path))
        menu.addAction(save)

        reload_action = QAction('Reload from disk', menu)
        reload_action.triggered.connect(lambda: self._reload(item))
        menu.addAction(reload_action)

    def _populate_table_menu(self, item, menu):
        """Add the single-table entries.

        Args:
            item: The PandapowerTableItem.
            menu: QMenu to populate.
        """
        if item.enabled:
            add = QAction('Add layer to project', menu)
            add.triggered.connect(lambda: _add_table_item_to_project(item))
            menu.addAction(add)
        else:
            run_pf = QAction('Run power flow...', menu)
            run_pf.triggered.connect(lambda: self._run_power_flow(item.file_path))
            menu.addAction(run_pf)

    def _populate_results_menu(self, item, menu):
        """Add the entries for the Results group.

        Args:
            item: The PandapowerResultsItem.
            menu: QMenu to populate.
        """
        run_pf = QAction('Run power flow...', menu)
        run_pf.triggered.connect(lambda: self._run_power_flow(item.file_path))
        menu.addAction(run_pf)

    # -- actions ----------------------------------------------------------

    def _add_all_layers(self, item):
        """Add every geometry-bearing table of a network to the project.

        Args:
            item: The PandapowerNetworkItem.
        """
        # Expanding the item is what produces its children.
        if item.state() != item.state().__class__.Populated:
            item.populate(True)

        added = 0
        for child in item.children():
            for leaf in self._leaf_items(child):
                if leaf.enabled and _add_table_item_to_project(leaf):
                    added += 1

        if added == 0:
            self._warn('Nothing added',
                       'No layers could be created from this network.')

    def _leaf_items(self, item):
        """Yield the addable table items under a tree item.

        Only geometry-bearing tables are yielded, since 'Add all' is about
        putting a network on the map.

        Args:
            item: A tree item to walk.
        Returns:
            list: PandapowerTableItem instances carrying geometry.
        """
        from .pandapower_uri import has_geometry

        if isinstance(item, PandapowerResultsItem):
            return []

        if isinstance(item, PandapowerTableItem):
            return [item] if has_geometry(item.table) else []

        if item.state() != item.state().__class__.Populated:
            item.populate(True)

        leaves = []
        for child in item.children():
            leaves.extend(self._leaf_items(child))
        return leaves

    def _offer_power_flow(self, item):
        """Ask whether to run a power flow for an empty result table.

        Args:
            item: The disabled PandapowerTableItem.
        """
        answer = QMessageBox.question(
            None,
            'No results yet',
            'The table "{}" has no results.\n\n'
            'Run a power flow now?'.format(item.table),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self._run_power_flow(item.file_path)

    def _run_power_flow(self, path):
        """Run a power flow on a network and refresh its browser item.

        Args:
            path: Path of the network file.
        """
        session = NetworkSession.get(path)
        if session is None:
            self._warn(
                'Network not open',
                'Open a layer from this network first, then run the power '
                'flow.')
            return

        try:
            import pandapower as pp

            pp.runpp(session.net)
            session.mark_dirty()
            session.notify_changed()
            self._info('Power flow complete',
                       'Results are available under "Results".')
        except Exception as error:
            self._warn('Power flow failed', str(error))

    def _save_network(self, path):
        """Write the in-memory network back to its file.

        Args:
            path: Path of the network file.
        """
        session = NetworkSession.get(path)
        if session is None:
            self._warn('Network not open', 'This network is not open.')
            return

        if session.file_changed_externally():
            answer = QMessageBox.question(
                None,
                'File changed on disk',
                'The file has changed since it was opened.\n\n'
                'Overwrite it with the in-memory network?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            import pandapower as pp

            pp.to_json(session.net, path)
            session.mark_clean()
            self._info('Network saved', 'Written to {}'.format(path))
        except Exception as error:
            self._warn('Save failed', str(error))

    def _reload(self, item):
        """Discard in-memory changes and reload a network from disk.

        Args:
            item: The PandapowerNetworkItem.
        """
        session = NetworkSession.get(item.file_path)
        if session is not None and session.dirty:
            answer = QMessageBox.question(
                None,
                'Discard changes?',
                'This network has unsaved changes.\n\n'
                'Reload from disk and lose them?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            from .pandapower_provider import PandapowerProvider

            net = PandapowerProvider._load_network_from_file(
                item.file_path, item.kind)
            NetworkSession.seed(item.file_path, net, kind=item.kind)
            item.refresh()
            self._info('Network reloaded', 'Reloaded from disk.')
        except Exception as error:
            self._warn('Reload failed', str(error))

    # -- messaging --------------------------------------------------------

    @staticmethod
    def _info(title, message):
        QMessageBox.information(None, title, message)

    @staticmethod
    def _warn(title, message):
        QMessageBox.warning(None, title, message)
