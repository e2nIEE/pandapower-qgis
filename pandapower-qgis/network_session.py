# -*- coding: utf-8 -*-
"""One loaded pandapower network per file, shared by every layer of that file.

This module replaces the old ``network_container`` module. The essential
difference is the key: ``NetworkContainer`` stored one entry per *layer URI*,
so ``bus@20kV`` and ``line@20kV`` of the same file were separate entries, each
holding its own reference to a network and a copy of the metadata. Nothing
guaranteed that two layers of one file operated on the same ``net`` object.

``NetworkSession`` is keyed by the normalised absolute file path and owns
exactly one ``net`` per file. Every provider for that file shares it, so an
edit made through one layer is immediately visible to all others. That is what
makes the plugin operate on the pandapower network itself rather than on
per-layer copies.

See docs/dataprovider_v2_plan.md section 3.3.
"""

import os
import weakref

# Network kinds. Only KIND_POWER is exercised today; KIND_PIPES exists so the
# pandapipes integration (plan section 5.4) can slot in without restructuring.
KIND_POWER = 'power'
KIND_PIPES = 'pipes'

# Default CRS assumed when a network carries no explicit EPSG code.
DEFAULT_EPSG = 4326


def add_vn_kv_to_lines(net):
    """Copy the bus voltage level onto the line table as a ``vn_kv`` column.

    Line layers are filtered by the voltage level of their ``from_bus``, which
    requires that level to be present on the line table itself.

    ``add_column_from_node_to_elements`` lives in ``pandapower.toolbox`` since
    pandapower 3 and was only re-exported at package level in pandapower 2, so
    both locations are tried.

    Args:
        net: The pandapower network to modify in place.
    """
    try:
        from pandapower.toolbox import add_column_from_node_to_elements
    except ImportError:  # pragma: no cover - pandapower 2 fallback
        from pandapower import add_column_from_node_to_elements

    # 'elements' is a list of table names; passing a bare string makes
    # pandapower iterate over its characters.
    add_column_from_node_to_elements(net, 'vn_kv', True, ['line'])


def normalise_path(path):
    """Normalise a file path for use as a session key.

    Two URIs pointing at the same file must map to the same session, so the
    path is made absolute and case-normalised (the latter matters on Windows,
    where ``C:/net.json`` and ``c:\\NET.json`` are the same file).

    Args:
        path: File system path to normalise.
    Returns:
        str: Normalised absolute path, or an empty string for a falsy input.
    """
    if not path:
        return ''
    return os.path.normcase(os.path.abspath(path))


class NetworkSession:
    """A single loaded pandapower network, shared by all layers of one file.

    Sessions are obtained through :py:meth:`acquire` and released through
    :py:meth:`release`. They are reference counted: the session is dropped from
    the registry when the last provider using it goes away.
    """

    # Registry of live sessions, keyed by normalised absolute file path.
    _sessions = {}

    def __init__(self, path, net, epsg=DEFAULT_EPSG, kind=KIND_POWER):
        """Initialise a session. Use :py:meth:`acquire` instead of calling this.

        Args:
            path: Normalised absolute path of the network file.
            net: The loaded pandapower network object.
            epsg: EPSG code of the network geodata.
            kind: KIND_POWER or KIND_PIPES.
        """
        self.path = path
        self.net = net
        self.epsg = int(epsg) if epsg else DEFAULT_EPSG
        self.kind = kind

        # Set when the in-memory net diverges from the file on disk. Phase 6
        # turns this into commit-based writing; until then the provider still
        # saves eagerly and simply keeps this flag up to date.
        self.dirty = False

        # Guards the once-per-session warning emitted when a feature moves
        # between voltage-level layers (plan section 5.1).
        self.voltage_move_warned = False

        # mtime and size of the file as we last read or wrote it, for the
        # concurrent-external-edit check (plan section 5.3).
        self.file_mtime = None
        self.file_size = None
        self.remember_file_state()

        self._refcount = 0
        # Weak references, so a provider that QGIS destroys without calling
        # release() cannot keep the session alive.
        self._providers = weakref.WeakSet()

    # -- acquisition ------------------------------------------------------

    @classmethod
    def acquire(cls, path, loader, epsg=DEFAULT_EPSG, kind=KIND_POWER):
        """Get the session for a file, loading it if it is not open yet.

        Args:
            path: Path of the network file.
            loader: Zero-argument callable returning a loaded network object.
                Only called when the file is not already open.
            epsg: EPSG code to record if the session is created now.
            kind: KIND_POWER or KIND_PIPES, recorded if created now.
        Returns:
            NetworkSession: The shared session for this file.
        Raises:
            ValueError: If the path is empty.
            Any exception raised by ``loader``.
        """
        key = normalise_path(path)
        if not key:
            raise ValueError('Cannot open a network session without a path.')

        session = cls._sessions.get(key)
        if session is None:
            session = cls(key, loader(), epsg=epsg, kind=kind)
            cls._sessions[key] = session

        session._refcount += 1
        return session

    @classmethod
    def seed(cls, path, net, epsg=DEFAULT_EPSG, kind=KIND_POWER):
        """Pre-populate the session for a file with an already loaded network.

        Used by the import path, which has read the file itself and would
        otherwise make the first provider parse the same JSON a second time.
        If a session for the file is already open, its network is replaced, so
        the freshly read data wins and every open layer sees it.

        This does not take a reference: providers still call :py:meth:`acquire`,
        which finds the seeded session instead of loading.

        Args:
            path: Path of the network file.
            net: The already loaded network object.
            epsg: EPSG code of the network geodata.
            kind: KIND_POWER or KIND_PIPES.
        Returns:
            NetworkSession: The seeded session.
        """
        key = normalise_path(path)
        if not key:
            raise ValueError('Cannot open a network session without a path.')

        session = cls._sessions.get(key)
        if session is None:
            session = cls(key, net, epsg=epsg, kind=kind)
            cls._sessions[key] = session
        else:
            session.net = net
            session.epsg = int(epsg) if epsg else DEFAULT_EPSG
            session.kind = kind
            session.mark_clean()
            session.notify_changed()
        return session

    @classmethod
    def get(cls, path):
        """Return the open session for a file, without loading it.

        Args:
            path: Path of the network file.
        Returns:
            NetworkSession or None: The session, or None if not open.
        """
        return cls._sessions.get(normalise_path(path))

    @classmethod
    def all_sessions(cls):
        """Return all currently open sessions.

        Returns:
            list: The live NetworkSession instances.
        """
        return list(cls._sessions.values())

    @classmethod
    def clear(cls):
        """Drop all sessions. Intended for tests and plugin unload."""
        cls._sessions.clear()

    def release(self):
        """Drop one reference; forget the session when the last one goes.

        Returns:
            bool: True if the session was dropped from the registry.
        """
        self._refcount -= 1
        if self._refcount <= 0:
            self._sessions.pop(self.path, None)
            return True
        return False

    # -- provider registration --------------------------------------------

    def add_provider(self, provider):
        """Register a provider as a user of this session.

        Args:
            provider: The PandapowerProvider instance.
        """
        self._providers.add(provider)

    def remove_provider(self, provider):
        """Unregister a provider.

        Args:
            provider: The PandapowerProvider instance.
        """
        self._providers.discard(provider)

    def providers(self):
        """Return the providers currently using this session.

        Returns:
            list: Live PandapowerProvider instances.
        """
        return list(self._providers)

    def notify_changed(self, source=None):
        """Tell every other provider of this file that the network changed.

        Because all providers share one ``net``, they need only invalidate
        their cached dataframe and repaint; no data is copied between them.

        Args:
            source: Provider that caused the change, skipped during
                notification. Pass None to notify all providers.
        """
        for provider in self.providers():
            if provider is source:
                continue
            try:
                provider.on_session_changed()
            except Exception as error:  # pragma: no cover - defensive
                print('Failed to notify provider of network change: '
                      '{}'.format(error))

    # -- file state -------------------------------------------------------

    def remember_file_state(self):
        """Record the file's current mtime and size as the known-good state."""
        try:
            stat = os.stat(self.path)
            self.file_mtime = stat.st_mtime
            self.file_size = stat.st_size
        except OSError:
            self.file_mtime = None
            self.file_size = None

    def file_changed_externally(self):
        """Check whether the file changed since we last read or wrote it.

        Used before writing, so an external edit is never silently overwritten
        (plan section 5.3).

        Returns:
            bool: True if the file on disk differs from the recorded state.
        """
        if self.file_mtime is None:
            return False
        try:
            stat = os.stat(self.path)
        except OSError:
            # The file disappeared; treat that as an external change.
            return True
        return (stat.st_mtime != self.file_mtime
                or stat.st_size != self.file_size)

    def create_backup(self):
        """Copy the current file aside before it is overwritten.

        Returns:
            str: Path of the backup, or an empty string if none was made.
        """
        import shutil
        from datetime import datetime

        if not os.path.exists(self.path):
            return ''

        backup_path = '{}.{}.bak'.format(
            self.path, datetime.now().strftime('%Y%m%d_%H%M%S'))
        try:
            shutil.copy2(self.path, backup_path)
            return backup_path
        except OSError:
            # A failed backup must not block the save; the user asked to write.
            return ''

    def write(self, backup=True):
        """Write the in-memory network to its file.

        This is the single place the network reaches disk. Because every layer
        of a file shares one ``net``, the whole network is written once, rather
        than each layer merging its own slice into a re-read copy of the file.

        The caller is responsible for checking :py:meth:`file_changed_externally`
        first and asking the user what to do; this method does not prompt.

        Args:
            backup: Copy the existing file aside first.
        Returns:
            tuple: ``(success, message, backup_path)``.
        """
        if self.net is None:
            return False, 'No network loaded.', ''

        backup_path = self.create_backup() if backup else ''

        try:
            if self.kind == KIND_PIPES:
                import pandapipes as writer
            else:
                import pandapower as writer

            writer.to_json(self.net, self.path)
        except PermissionError:
            return (False,
                    'Cannot write {}. The file may be open in another '
                    'program, or you may not have permission.'.format(self.path),
                    backup_path)
        except Exception as error:
            return False, 'Could not save network: {}'.format(error), backup_path

        self.mark_clean()
        return True, 'Network saved to {}'.format(self.path), backup_path

    def mark_dirty(self):
        """Flag the in-memory network as diverged from the file on disk."""
        self.dirty = True

    def mark_clean(self):
        """Flag the network as matching the file, and refresh the file state.

        Call this after a successful write.
        """
        self.dirty = False
        self.remember_file_state()

    def __repr__(self):
        return ('<NetworkSession {} kind={} refs={} dirty={}>'
                .format(self.path, self.kind, self._refcount, self.dirty))
