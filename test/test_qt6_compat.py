# coding=utf-8
"""Tests that the plugin runs on both QGIS 3 (Qt5) and QGIS 4 (Qt6).

PyQt6 dropped the unscoped enum aliases (``QMessageBox.Yes``) and QGIS 4
dropped the deprecated QGIS ones (``QgsWkbTypes.Point``). Most of those
references sit inside functions that the other tests never reach, so a
missing name would only surface when a user clicks the wrong button. These
tests resolve every such reference against the running QGIS instead, and load
the plugin the way QGIS does.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.
"""

import ast
import configparser
import glob
import importlib
import os
import sys
import unittest

from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()

PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'pandapower-qgis'))

# Modules a Qt or QGIS name in the plugin can come from.
API_MODULES = ['qgis.core', 'qgis.gui', 'qgis.PyQt.QtCore', 'qgis.PyQt.QtGui',
               'qgis.PyQt.QtWidgets']


def load_plugin_module(name):
    """Import a module from the plugin directory by name.

    :param name: Module name inside the plugin package.
    :returns: The imported module.
    """
    parent = os.path.dirname(PLUGIN_DIR)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    package = 'pandapower_qgis_plugin'
    if package not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            package,
            os.path.join(PLUGIN_DIR, '__init__.py'),
            submodule_search_locations=[PLUGIN_DIR])
        module = importlib.util.module_from_spec(spec)
        sys.modules[package] = module
        spec.loader.exec_module(module)

    return importlib.import_module('{}.{}'.format(package, name))


def api_references(path):
    """Yield (line, dotted name) for each constant-style API reference.

    Only chains whose parts after the root are all capitalised are returned
    (``QMessageBox.StandardButton.Yes``, ``Qgis.WkbType.Point``): those are
    enums, flags and nested classes. Method calls and attributes are skipped.
    """
    with open(path, encoding='utf-8') as source:
        tree = ast.parse(source.read(), path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.insert(0, current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            continue
        root = current.id
        if root == 'QtCore':  # "from qgis.PyQt import QtCore"
            root, parts = parts[0], parts[1:]
        if not parts or not all(part[:1].isupper() for part in parts):
            continue
        yield node.lineno, root, parts


def resolve(root, parts):
    """Resolve ``root.parts...`` against the QGIS and Qt modules.

    :returns: True if it resolves, False if it does not, None if the root is
        not a Qt or QGIS name at all (a plugin class, for example).
    """
    for module_name in API_MODULES:
        module = importlib.import_module(module_name)
        if hasattr(module, root):
            value = getattr(module, root)
            break
    else:
        return None

    for part in parts:
        if not hasattr(value, part):
            return False
        value = getattr(value, part)
    return True


class ApiReferenceTest(unittest.TestCase):
    """Every enum, flag and nested class the plugin names must exist."""

    def test_api_references_resolve(self):
        """No reference to a Qt or QGIS name that this QGIS no longer has."""
        sources = glob.glob(os.path.join(PLUGIN_DIR, '*.py')) + \
            glob.glob(os.path.join(PLUGIN_DIR, 'provider_utils', '*.py'))
        missing = []
        checked = set()
        for path in sources:
            for line, root, parts in api_references(path):
                dotted = '.'.join([root] + parts)
                result = resolve(root, parts)
                if result is False:
                    missing.append('{}:{}: {}'.format(
                        os.path.relpath(path, PLUGIN_DIR), line, dotted))
                elif result:
                    checked.add(dotted)

        self.assertFalse(missing, 'Not available in this QGIS:\n' + '\n'.join(missing))
        # Guard against the walk silently checking nothing.
        self.assertGreater(len(checked), 20)


class PluginLoadTest(unittest.TestCase):
    """Load the plugin the way QGIS does and build its dialogs."""

    def test_metadata_offers_plugin_to_qt6(self):
        """QGIS 4 hides plugins that do not declare Qt6 support."""
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(os.path.join(PLUGIN_DIR, 'metadata.txt'))
        general = parser['general']

        self.assertIn(general.get('supportsQt6', '').strip().lower(), ('true', 'yes'))
        # Without an explicit maximum QGIS assumes <major of minimum>.99.
        self.assertTrue(general.get('qgisMaximumVersion', '').startswith('4.'))

    def test_init_gui_and_unload(self):
        """classFactory, initGui and unload run, and the actions have icons."""
        from qgis.testing.mocked import get_iface

        iface = get_iface()
        package = load_plugin_module('pandapower_qgis')
        plugin = sys.modules['pandapower_qgis_plugin'].classFactory(iface)
        self.assertIsInstance(plugin, package.ppqgis)

        plugin.initGui()
        try:
            self.assertEqual(len(plugin.actions), 2)
            for action in plugin.actions:
                self.assertFalse(action.icon().isNull(), action.text())
        finally:
            plugin.unload()

    def test_dialogs_build(self):
        """The .ui based dialogs and the run dialog can be constructed."""
        export = load_plugin_module('pandapower_export_dialog')
        summary = load_plugin_module('pandapower_export_summary_dialog')
        runpp = load_plugin_module('pandapower_runpp_dialog')

        for dialog_class in (export.ppExportDialog,
                             summary.ppExportSummaryDialog,
                             runpp.ppRunDialog):
            dialog = dialog_class()
            self.assertIsNotNone(dialog)
            dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
