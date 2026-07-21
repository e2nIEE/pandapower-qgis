# Tests

The tests need the QGIS Python bindings, so they must run under the QGIS
interpreter rather than a plain `python`.

## Running

From the repository root:

```bash
# Windows (OSGeo4W)
C:\OSGeo4W\bin\python-qgis.bat -m unittest discover -s test -t .

# Linux (system QGIS)
python3 -m unittest discover -s test -t .
```

Add `-v` for per-test output. To run a single module:

```bash
C:\OSGeo4W\bin\python-qgis.bat -m unittest test.test_provider_registration -v
```

`-t .` matters: the tests are a package (`test.…`) and use relative imports, so
the repository root has to be the top-level directory.

## Layout

| File | Covers |
| --- | --- |
| `test_init.py` | `metadata.txt` has the fields plugins.qgis.org requires |
| `test_qgis_environment.py` | Required providers are present; EPSG codes resolve |
| `test_provider_registration.py` | Provider registers, `icon()` works, URI round-trips, `unload()` does not deregister the shared provider type |
| `test_network_session.py` | One loaded network per file, ref counting, dirty tracking, external-change detection |
| `test_pandapower_uri.py` | URI encode/decode, including the pre-rework keys |
| `test_result_column_merge.py` | `res_*` columns reach the layers whose renderers filter on them (guards a silent styling regression) |
| `test_data_items.py` | Browser tree: cheap file sniffing, only populated tables listed, voltage-level children, greyed empty `res_*` |
| `test_source_select.py` | Data Source Manager page: registry ordering, table listing, Add emits a usable URI |
| `test_commit_writes.py` | Edits reach disk only on commit, backups, coalescing, external-change detection |
| `utilities.py` | `get_qgis_app()` — starts one headless `QgsApplication` per process |

`test_result_column_merge.py` needs pandapower and builds a real network, so it is slower
than the rest. Set `SKIP_PANDAPOWER_TESTS=1` to skip it.

## In CI

`.github/workflows/test.yaml` runs this suite on every push and pull request,
inside the `qgis/qgis:release-3_44` container (the QGIS Python bindings cannot be
pip-installed, so a bare runner will not do).

The same workflow builds the plugin package and fails if any module on disk is
missing from it. `qgis-plugin-ci` packages from **git**, so a module that was
never committed is silently dropped — the plugin then works perfectly in a
developer checkout and fails to load for everyone else.

## Notes

`get_qgis_app()` returns a single `QgsApplication` and reuses it; QGIS does not
support more than one per process. It runs headless (no GUI flag), so tests
must not depend on widgets being shown.

Tests that import the plugin package do so by path, because the plugin
directory is named `pandapower-qgis` — not a valid Python identifier, so it
cannot be imported with a plain `import` statement. See
`load_provider_metadata_class()` in `test_provider_registration.py`.
