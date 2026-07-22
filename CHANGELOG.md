# Changelog

## Unreleased

## 0.0.4 - 2026-07-21

pandapower networks are a data source, not an import.

**Networks are now opened, not imported.**

* pandapower appears in the **Data Source Manager** alongside PostgreSQL and SAP HANA.
  Pick a network file, select the tables you want, press Add.
* Every pandapower table can be opened, not just `bus` and `line`. Tables without
  geometry (`trafo`, `load`, `switch`, …) open as plain attribute tables.
* `res_*` tables can be opened in their own right, while their columns stay merged
  into the `bus`/`line` layers for styling.
* Only tables that contain rows are listed, so the dialog stays readable.

**Known limitation**

* Expanding a pandapower `.json` directly in the **Browser** panel is not available.
  Returning a Python subclass of `QgsDataCollectionItem` from
  `QgsDataItemProvider.createDataItem()` is unsafe on QGIS 3.44 — the object loses
  its Python half once QGIS stores it, and expanding the node crashes QGIS. This
  reproduces without this plugin, so it is a binding limitation rather than
  something the plugin can work around. Use the Data Source Manager instead; the
  code is kept behind `ENABLE_BROWSER_TREE` in `pandapower_qgis.py`.

**Edits are written on commit.**

* Changes are written to the `.json` when the layer edits are saved, not on every
  individual change. Rolling back writes nothing.
* All layers of one network share a single in-memory network, so one save writes
  them all and an edit in one layer is immediately visible in the others.
* A file that changed on disk is no longer silently overwritten.

**Removed**

* The *import from pandapower* action, together with `ppqgis_import.py` and its
  dialog. The Browser and Data Source Manager replace it. Note the old import
  reprojected the network's coordinates in place; opening a network now leaves the
  stored coordinates untouched and lets QGIS reproject for display.
* The vendored `geo.py`, superseded by `pandapower.plotting.geo` upstream.
* The asynchronous save machinery, and with it the "previous save operation is
  still running" class of errors.

*Export is unchanged* — it still builds a new network from arbitrary QGIS layers.

**Fixes**

* Plugin no longer fails to load on a profile where the locale setting is unset.
* Geometry edits no longer wrote into a pandas copy that was then discarded.
* Renderer instances are no longer shared between layers (a double-ownership crash).
* Closing a layer no longer deregisters the provider for every other open layer.
* `pressure_level` in a layer URI was written but never read, so pipe layers lost
  their level filter.

**Requires** pandapower 3.5 or newer, which stores geodata in the `geo` column.

## 0.0.3 - 2025-12-12

* Feature/dataprovider was included, which allows to use pandapower networks as a dataprovider.
* Large restructuring