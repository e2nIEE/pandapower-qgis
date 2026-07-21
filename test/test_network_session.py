# coding=utf-8
"""Tests for NetworkSession — one loaded network per file.

The point of NetworkSession is that every layer of a network file operates on
one and the same ``net`` object, so an edit made through one layer is visible
to all others. The old NetworkContainer keyed on layer URI and could not
guarantee that. See docs/dataprovider_v2_plan.md section 3.3.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.
"""

import os
import sys
import tempfile
import unittest

from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()

PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'pandapower-qgis'))


def load_session_module():
    """Import network_session from the plugin directory.

    The plugin directory is named 'pandapower-qgis', which is not a valid
    Python identifier, so it is loaded by path under an alias.

    :returns: The imported network_session module.
    """
    import importlib

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

    return importlib.import_module('{}.network_session'.format(package))


class FakeNet:
    """Stand-in for a pandapower network.

    The session does not care what the object is, only that it is shared, so
    the tests avoid the cost of building a real pandapower network.
    """

    def __init__(self, name='net'):
        self.name = name
        self.value = 0


class NetworkSessionTest(unittest.TestCase):
    """Test session sharing, reference counting and dirty tracking."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_session_module()
        cls.NetworkSession = cls.module.NetworkSession

    def setUp(self):
        self.NetworkSession.clear()
        handle, self.path = tempfile.mkstemp(suffix='.json')
        os.close(handle)
        with open(self.path, 'w') as handle:
            handle.write('{}')

    def tearDown(self):
        self.NetworkSession.clear()
        if os.path.exists(self.path):
            os.remove(self.path)

    def _acquire(self, net=None):
        """Acquire a session for the temp file, loading the given net."""
        net = net if net is not None else FakeNet()
        return self.NetworkSession.acquire(self.path, lambda: net)

    def test_two_layers_share_one_net(self):
        """Two acquisitions of one file yield the identical net object.

        This is the core guarantee of the session model.
        """
        first = self._acquire()
        second = self._acquire(FakeNet('should not be loaded'))

        self.assertIs(first, second)
        self.assertIs(first.net, second.net)

    def test_loader_runs_only_once_per_file(self):
        """The loader is not called again while the file is already open."""
        calls = []

        def loader():
            calls.append(1)
            return FakeNet()

        self.NetworkSession.acquire(self.path, loader)
        self.NetworkSession.acquire(self.path, loader)

        self.assertEqual(len(calls), 1)

    def test_edit_through_one_session_is_visible_in_the_other(self):
        """An edit via one handle is seen by every other handle."""
        first = self._acquire()
        second = self._acquire()

        first.net.value = 42

        self.assertEqual(second.net.value, 42)

    def test_path_is_normalised(self):
        """Differently spelled paths for one file map to one session."""
        first = self._acquire()

        # Same file reached through a redundant path segment.
        directory, name = os.path.split(self.path)
        awkward = os.path.join(directory, '.', name)
        second = self.NetworkSession.acquire(awkward, lambda: FakeNet('other'))

        self.assertIs(first, second)

    def test_release_is_reference_counted(self):
        """The session survives until the last user releases it."""
        first = self._acquire()
        self._acquire()

        self.assertFalse(first.release())
        self.assertIsNotNone(self.NetworkSession.get(self.path))

        self.assertTrue(first.release())
        self.assertIsNone(self.NetworkSession.get(self.path))

    def test_reacquire_after_release_reloads(self):
        """Once dropped, the next acquisition loads the file again."""
        session = self._acquire()
        session.release()

        reloaded = self.NetworkSession.acquire(
            self.path, lambda: FakeNet('fresh'))

        self.assertEqual(reloaded.net.name, 'fresh')

    def test_seed_populates_without_loading(self):
        """seed() installs an already loaded net, so acquire does not load."""
        net = FakeNet('imported')
        self.NetworkSession.seed(self.path, net)

        def loader():
            raise AssertionError('loader must not run for a seeded session')

        session = self.NetworkSession.acquire(self.path, loader)
        self.assertIs(session.net, net)

    def test_seed_replaces_net_of_open_session(self):
        """Re-importing a file updates the net every open layer sees."""
        session = self._acquire()
        replacement = FakeNet('reimported')

        self.NetworkSession.seed(self.path, replacement)

        self.assertIs(session.net, replacement)

    def test_notify_changed_skips_source(self):
        """The provider that caused a change is not notified about it."""
        session = self._acquire()
        notified = []

        class Provider:
            def on_session_changed(self):
                notified.append(self)

        source, other = Provider(), Provider()
        session.add_provider(source)
        session.add_provider(other)

        session.notify_changed(source=source)

        self.assertEqual(notified, [other])

    def test_dirty_flag_round_trip(self):
        """mark_dirty/mark_clean track divergence from the file on disk."""
        session = self._acquire()
        self.assertFalse(session.dirty)

        session.mark_dirty()
        self.assertTrue(session.dirty)

        session.mark_clean()
        self.assertFalse(session.dirty)

    def test_external_change_is_detected(self):
        """A write by another process is noticed before we overwrite it."""
        session = self._acquire()
        self.assertFalse(session.file_changed_externally())

        # Rewrite the file with different content, as an external tool would.
        with open(self.path, 'w') as handle:
            handle.write('{"changed": true}')
        os.utime(self.path, (0, 0))

        self.assertTrue(session.file_changed_externally())

    def test_mark_clean_accepts_our_own_write(self):
        """After we write, the file state is no longer seen as external."""
        session = self._acquire()

        with open(self.path, 'w') as handle:
            handle.write('{"written_by": "us"}')
        os.utime(self.path, (0, 0))
        session.mark_clean()

        self.assertFalse(session.file_changed_externally())

    def test_acquire_without_path_raises(self):
        """An empty path is rejected rather than creating a bogus session."""
        with self.assertRaises(ValueError):
            self.NetworkSession.acquire('', lambda: FakeNet())


if __name__ == '__main__':
    unittest.main()
