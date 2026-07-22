# Plan: pandapower as a first-class QGIS data source

**Status:** all phases complete · **Branch:** `feature/dataprovider_v2` · **Date:** 2026-07-21

All seven phases are implemented and verified (90 unit tests, plus a per-phase end-to-end
check against real QGIS layers). Section 4 records what each phase did, including the
decisions and pre-existing bugs found along the way. §5.2.1 records the multiple-load-case
idea deliberately left for later.

## 1. Goal

Make a pandapower network behave like a database connection in QGIS — comparable to
PostgreSQL, SAP HANA or Oracle — rather than an import/export round trip.

Concretely:

- The user picks a network in the **Data Source Manager** (left-hand list) or expands a
  `.json` in the **Browser**, and gets layers straight out of the network file.
- Viewing and editing geodata operates **transparently on the pandapower JSON itself**.
  There is no "import into QGIS" step and no separate "export back out" step.
- Non-spatial pandapower tables (`trafo`, `load`, `sgen`, `switch`, …) are reachable too,
  as attribute-only tables, exactly like non-spatial tables in a real database.

## 2. Where the project stands today

The repo already contains far more of this than the import/export UI suggests. What exists:

| Piece | File | State |
| --- | --- | --- |
| Vector data provider | [pandapower_provider.py](../pandapower-qgis/pandapower_provider.py) | Substantial (2359 lines): read, add, delete, change geometry, change attributes |
| Provider metadata | [ppprovider_metadata.py](../pandapower-qgis/ppprovider_metadata.py) | Minimal but functional URI encode/decode |
| Feature source / iterator | [pandapower_feature_source.py](../pandapower-qgis/pandapower_feature_source.py), [pandapower_feature_iterator.py](../pandapower-qgis/pandapower_feature_iterator.py) | Working |
| Registration | [\_\_init\_\_.py:38](../pandapower-qgis/__init__.py#L38) | `QgsProviderRegistry.registerProvider(...)` at `classFactory` time |
| Layer creation | [ppqgis_import.py:213](../pandapower-qgis/ppqgis_import.py#L213) | `QgsVectorLayer(uri, name, "PandapowerProvider")` — driven by the import dialog |

So the **provider layer is largely done**; layers already point at the live `net` object and
write back to the JSON. What is missing is everything that makes it *discoverable and
mountable as a data source*, plus several structural problems in how the network is shared.

### 2.1 The four blockers

**B1 — No GUI registration.** Only `QgsProviderMetadata` is registered. Appearing in the
Data Source Manager needs a `QgsSourceSelectProvider`; appearing in the Browser needs a
`QgsDataItemProvider`. Neither exists. See §3.1/§3.2 — both are fully exposed to Python
(`python/gui/auto_generated/qgssourceselectprovider.sip.in`,
`python/core/auto_generated/browser/qgsdataitemprovider.sip.in`).

**B2 — `capabilities()` lies about the provider.**
[ppprovider_metadata.py:60](../pandapower-qgis/ppprovider_metadata.py#L60) returns
`FileBasedUris`, which files the provider under "Add Vector Layer → File". That is the
*opposite* of the intended framing and must change (§3.1).

**B3 — Layer creation is coupled to the import dialog.** The only path that produces a
layer is `ppqgis_import.power_network()`, which also does renderers, groups, map tips and
`NetworkContainer` registration. A browser double-click cannot reuse any of that. The
layer-construction logic has to be extracted into a provider-owned factory (§3.4).

**B4 — `NetworkContainer` is keyed wrongly and holds duplicated state.**
[network_container.py](../pandapower-qgis/network_container.py) keys networks by *full layer
URI*, so `bus@20kV` and `line@20kV` of the same file are separate entries each holding a
`net` reference plus copied metadata. Two layers of one file are not guaranteed to share one
`net`. For "operate on the network itself" semantics, the container must be keyed by
**file path** and own exactly one `net` per file (§3.3).

Two smaller defects worth fixing while in the area:

- [ppprovider_metadata.py:96](../pandapower-qgis/ppprovider_metadata.py#L96) uses `os` and
  `QIcon` without importing them — `icon()` raises `NameError` the moment QGIS calls it.
- [pandapower_provider.py:2359](../pandapower-qgis/pandapower_provider.py#L2359)
  `unload()` calls `QgsProviderRegistry.removeProvider('PandapowerProvider')`. That
  deregisters the *provider type globally* when a single layer closes, breaking every other
  pandapower layer in the project. It must not do this.

## 3. Target architecture

```
QgsProviderRegistry ──── PandapowerProviderMetadata          (exists, needs fixes)
                              └── PandapowerProvider          (exists)

QgsGui.sourceSelectProviderRegistry()
      └── PandapowerSourceSelectProvider                      (NEW)
            └── PandapowerSourceSelectWidget                  (NEW)

QgsApplication.dataItemProviderRegistry()
      └── PandapowerDataItemProvider                          (NEW)
            └── PandapowerNetworkItem            (a .json file)
                  └── PandapowerTableItem        (bus, line, trafo, load, …)
                        └── PandapowerVoltageItem (20.0 kV, 110.0 kV — bus/line only)

QgsGui.dataItemGuiProviderRegistry()
      └── PandapowerDataItemGuiProvider                       (NEW, context menus)

NetworkSession  (NEW, replaces NetworkContainer)
      one loaded pandapower net per file path, ref-counted, owns dirty state
```

The reference implementation to follow is SAP HANA — the same shape the user named. See
`src/providers/hana/qgshanaprovidergui.cpp`, which registers exactly one
`QgsSourceSelectProvider` and one `QgsDataItemGuiProvider`. Our version is the Python
equivalent, minus connection management (see §3.2).

### 3.1 Data Source Manager entry

New file `pandapower_source_select.py`.

```python
class PandapowerSourceSelectProvider(QgsSourceSelectProvider):
    def providerKey(self):  return "PandapowerProvider"
    def text(self):         return "pandapower"
    def icon(self):         return QIcon(":/plugins/pandapower_qgis/pp.svg")
    def ordering(self):     return QgsSourceSelectProvider.OrderDatabaseProvider + 100
    def createDataSourceWidget(self, parent=None, fl=Qt.Widget, widgetMode=...):
        return PandapowerSourceSelectWidget(parent, fl, widgetMode)
```

`OrderDatabaseProvider + 100` places the entry in the database group, below the built-in DB
providers — the position the user is asking for. Registered via
`QgsGui.sourceSelectProviderRegistry().addProvider(...)` in `initGui()`, removed in
`unload()`.

`PandapowerSourceSelectWidget(QgsAbstractDataSourceWidget)` contains:

- a file picker for the network `.json` (recent paths in `QSettings`),
- a table listing the network's contents once a file is chosen — table name, geometry type,
  feature count, voltage level,
- multi-select + **Add**, which emits `addLayer(Qgis.LayerType.Vector, uri, name, "PandapowerProvider")`
  per selected row.

Note the signal contract: `QgsAbstractDataSourceWidget` exposes the modern
`addLayer(type, url, baseName, providerKey)` signal alongside the deprecated
`addVectorLayer`. Use `addLayer`.

**B2 fix:** `PandapowerProviderMetadata.capabilities()` changes from `FileBasedUris` to
`QgsProviderMetadata.ProviderMetadataCapability.LayerTypesForUri`, and `filters()` stops
advertising `*.json` as a generic vector file filter. The provider should not be reachable
through "Add Vector Layer → File" any more; that path is what makes it feel like an import.

### 3.2 Browser tree

New file `pandapower_data_items.py`. Per the decision taken, there is **no saved-connection
layer** — networks are discovered as files in the normal Home/Directory tree, the way
GeoPackage behaves (`src/core/providers/ogr/qgsgeopackagedataitems.h` is the model).

```python
class PandapowerDataItemProvider(QgsDataItemProvider):
    def name(self):            return "pandapower"
    def dataProviderKey(self): return "PandapowerProvider"
    def capabilities(self):    return Qgis.DataItemProviderCapability.Files
    def createDataItem(self, path, parentItem):
        if not path.lower().endswith(".json"):        return None
        if not _is_pandapower_json(path):             return None   # cheap sniff
        return PandapowerNetworkItem(parentItem, os.path.basename(path), path)
```

`_is_pandapower_json` must be **cheap** — the browser calls `createDataItem` for every
`.json` in every directory the user expands. Read a bounded prefix of the file (e.g. 8 KB)
and look for `"pandapowerNet"` **or** `"pandapipesNet"` (§5.4); never `pp.from_json` here.
Record which kind matched on the session.

Tree structure (the chosen "all tables + voltage sublevels" variant, with the `Results`
group from §5.2):

```
mv_oberrhein.json                 PandapowerNetworkItem     (QgsDataCollectionItem)
├── bus                           PandapowerTableItem       (collection, has geometry)
│   ├── 20.0 kV                   PandapowerVoltageItem     (QgsLayerItem → addable)
│   └── 110.0 kV                  PandapowerVoltageItem
├── line
│   ├── 20.0 kV
│   └── 110.0 kV
├── trafo                         PandapowerTableItem       (QgsLayerItem, TableLayer)
├── load
├── sgen
├── switch
└── Results                       PandapowerResultsItem     (collection)
    ├── res_bus                   PandapowerTableItem       (grey when empty)
    ├── res_line
    └── res_trafo
```

Rules that fall out of this:

- `bus` and `line` are **collection** items (they have voltage children). Every other table
  is a **leaf** `QgsLayerItem` with `Qgis.BrowserLayerType.TableLayer` and no geometry.
- Only leaves implement `mimeUris()` (drag to canvas) and are double-clickable.
- The table list is **derived from the loaded net object**, not hardcoded — this is what
  makes pandapipes tables appear for free later (§5.4).
- `res_*` tables live under `Results` and are shown greyed when empty (§5.2).
- Populating `PandapowerNetworkItem.createChildren()` **does** require loading the net.
  Do it through `NetworkSession` (§3.3) so the same load serves the subsequent layer
  creation, and set `Qgis.BrowserItemState.Populating` so the UI stays responsive.

`PandapowerDataItemGuiProvider` supplies context menus: *Save network*, *Reload from disk*,
*Run power flow* (reusing `ppqgis_runpp`), *Add all layers to project*.

### 3.3 One network per file: `NetworkSession`

This is the change that actually delivers "work on the pp network itself". New file
`network_session.py`, replacing `network_container.py`.

```python
class NetworkSession:
    """One loaded pandapower net per file path. Ref-counted by open providers."""
    _sessions: dict[str, NetworkSession]   # keyed by normalised absolute file path

    path: str
    net: pandapowerNet          # THE single shared net object
    epsg: int
    dirty: bool
    _refcount: int
    _providers: list            # weak refs, for cross-layer change notification
```

Key differences from today's `NetworkContainer`:

| | `NetworkContainer` (today) | `NetworkSession` (target) |
| --- | --- | --- |
| Key | full layer URI | normalised file path |
| `net` instances per file | one per layer URI | exactly one |
| Metadata | duplicated into each entry | derived from `net` on demand |
| Lifetime | never released | ref-counted; released at zero |
| Dirty tracking | none (writes are immediate) | explicit `dirty` flag |
| Module identity | `sys.modules` hack ([network_container.py:4](../pandapower-qgis/network_container.py#L4)) | plain module-level singleton |

The `sys.modules['network_container']` trick exists to survive plugin reloads. It is fragile
and, worse, it makes the class identity depend on import order. Replace it with an explicit
module-level dict guarded by a version key, or accept that a plugin reload drops sessions
(the honest behaviour — reloading the plugin should reload networks).

Because all layers of a file now share one `net`, the cross-layer notification machinery
(`add_listener` / `_notify_all_listeners` / `on_update_changed_network`) shrinks to
"invalidate cached dataframes and repaint" rather than "ship a new net around".

### 3.4 Layer factory extracted from the import dialog (B3)

New module-level function, e.g. in `pandapower_layer_factory.py`:

```python
def create_layer(path: str, table: str, voltage: float | None, epsg: int) -> QgsVectorLayer:
    """Build a QgsVectorLayer for one pandapower table. No dialogs, no project side effects."""
```

It owns URI encoding, layer naming, renderer selection (via `renderer_utils`), field edit
permissions and map tips — everything `ppqgis_import.power_network()` currently does inline
around [ppqgis_import.py:213](../pandapower-qgis/ppqgis_import.py#L213) — but **does not**
touch `QgsProject` or layer groups. Callers decide placement:

- browser double-click / drag → adds to project root,
- source select widget **Add** → adds to project root,
- `ppqgis_import` → keeps its existing grouping behaviour, now as a thin caller.

This is what lets three entry points produce identical layers.

### 3.5 URI scheme

Extend the current scheme to address any table, and make voltage optional:

```
path="C:/net/mv_oberrhein.json";table="bus";voltage="20.0";epsg="4326"
path="C:/net/mv_oberrhein.json";table="trafo";epsg="4326"
```

`network_type` is renamed to `table` (it now names any pandapower table, not just the four
geo types). Keep `decodeUri` tolerant of the old `network_type` key for one release so
existing `.qgz` projects still open — a one-line alias in `decodeUri`.

`geometry=` can be dropped from the URI: it is derivable from the table name and is already
ignored by the provider.

### 3.6 Non-spatial tables

`PandapowerProvider` currently assumes a geometry
([wkbType()](../pandapower-qgis/pandapower_provider.py#L2335) returns `None` for anything
outside bus/line/junction/pipe, and the iterator unconditionally reads `.geo`). For
attribute-only tables:

- `wkbType()` → `QgsWkbTypes.NoGeometry`,
- `extent()` → empty `QgsRectangle`,
- the iterator skips geometry construction and the `.geo` lookup entirely,
- `merge_df()` skips the voltage filter and the `res_*` merge when no result table exists.

This is what makes `trafo`/`load`/`switch` open as plain tables — the database-like part of
the goal. It is also the mechanism behind the separately-listed `res_*` items in §5.2: a
`res_bus` layer is just a non-spatial table whose source DataFrame is `net.res_bus`. No extra
provider code is needed for them beyond this section, since `merge_df()` on a `res_*` table
is the identity case (no filter, no second merge).

### 3.7 Write policy: commit-based (B-decision)

Per the decision taken, the JSON is written when the user **commits the layer edit buffer**,
not on every change. This replaces the current per-change async save.

- `changeGeometryValues` / `changeAttributeValues` / `addFeatures` / `deleteFeatures` mutate
  the shared `net` and set `session.dirty = True`. They no longer spawn save threads.
- The provider connects to the layer's commit signal; on commit, if `session.dirty`,
  **check the file mtime** (§5.3) and then write `pp.to_json(net, path)` once.
- A write-back guard: if several layers of the same file commit in one action, coalesce to a
  single write.
- After commit, refresh sibling layers whose filtered view may have changed (§5.1), coalesced
  to one refresh per commit.
- On QGIS close / project close with `dirty` still set, prompt.

This deletes a large amount of code —
`update_geodata_in_json_async`, `update_attributes_in_json_async`,
`update_entire_network_in_json_async`, the three inner `QThread` subclasses, `_save_in_progress`,
and the "previous save operation is still running" warning path
([pandapower_provider.py:338](../pandapower-qgis/pandapower_provider.py#L338)) — roughly
400 lines, and removes the existing save-race class of bugs outright.

Backups: keep the existing backup-before-write behaviour, now on the single commit write.

## 4. Work plan

Ordered so each phase is independently testable in a running QGIS.

### Phase 0 — Corrective fixes (small, do first) — **done**
- [x] Import `os` / `QIcon` in `ppprovider_metadata.py`; verify `icon()` returns.
- [x] Remove the global `removeProvider` call from `PandapowerProvider.unload()`.
- [x] Add a smoke test that loads the plugin and asserts the provider is registered.
- [x] Unplanned: `test/utilities.py` imported `QWidget` from `QtGui`, so `get_qgis_app()`
      silently returned `None` and no test ever had a running QGIS. Fixed, and the QGIS 2
      era scaffolding (`qgis_interface.py`, translation/dialog/resource tests, raster
      fixtures) was removed.

### Phase 1 — `NetworkSession` (foundation for everything else) — **done**
- [x] Implement `network_session.py`; one `net` per path, ref-counted.
- [x] Record `st_mtime` + size at load, for the §5.3 check.
- [x] Add the `kind` field (`"power"` / `"pipes"`) per §5.4, even though only `"power"` is
      exercised now.
- [x] Port `PandapowerProvider.__init__` to acquire a session instead of reading `NetworkContainer`.
- [x] Port `ppqgis_import` / `ppqgis_runpp` / `ppqgis_export` / `pandapower_runpp_dialog`
      to the session API.
- [x] Delete `network_container.py`.
- [x] Verify: two layers of one file share one `net` (`assert a.net is b.net`).

Notes from the implementation:

- `NetworkSession.seed()` was added beyond the plan. The import path has already parsed the
  file, and without seeding the first provider would parse the same JSON a second time.
- `provider.network_data` survives as a **property** derived from the session, rather than a
  stored dict. Call sites that expected the old shape keep working and can no longer read a
  stale copy.
- `_notify_affected_layers()` no longer scans every project layer; the session knows its own
  providers. It now notifies **all** network types of the file rather than only those of the
  same voltage level, which is what cascade deletion (bus → line) actually needs.
- The environment had pandapower 2.14, but the plugin targets 3.x, where geodata lives in a
  `geo` column. Upgrading to 3.5.4 surfaced that
  `pp.add_column_from_node_to_elements` moved to `pandapower.toolbox` and that both call
  sites passed `'line'` where a **list** of table names is expected. Both are fixed behind
  `network_session.add_vn_kv_to_lines()`.

### Phase 2 — Layer factory + URI scheme — **done**
- [x] `pandapower_layer_factory.create_layer(...)`, no project side effects.
- [x] URI `network_type` → `table`, with backward-compatible decode.
- [x] Refactor `ppqgis_import` to call the factory. Behaviour must not change.

Notes from the implementation:

- The URI scheme lives in its own module, `pandapower_uri.py`, so the browser (phase 4) and
  source select (phase 5) can build URIs without importing the provider.
- `voltage_level` **and** `pressure_level` both fold into a single `level` key. This fixes a
  latent bug: the import path wrote `pressure_level` for pipe networks while the provider
  only ever read `voltage_level`, so pipe layers silently lost their level filter.
- `provider.network_type` keeps its name internally (~100 uses); only the URI key was
  renamed. `provider.parts` now holds the normalised URI.
- `configure_field_edit_permissions` moved out of `ppqgis_import` into the factory and no
  longer needs the table name — it asks the provider per field.
- Verified against real layers: a pre-rework URI (`network_type=` / `voltage_level=` /
  `geometry=`) still opens, yields the same feature count, resolves its level, and shares one
  session with a new-scheme layer of the same file.

Pre-existing bug found and fixed: `ppqgis_import` built renderers *outside* the level loop
and assigned the same instance to every level. `QgsVectorLayer.setRenderer()` is annotated
`/Transfer/` — "Ownership is transferred" — so two layers holding one renderer is a
double-ownership bug that can double-free on teardown. Both branches were affected:

- the power branch hoisted `bus_renderer_by_load` / `line_renderer_by_load`;
- the pipes branch hoisted the graduated `junction_renderer` / `pipe_renderer`.

Both now build a fresh pair per level. The pipes symbology block was extracted into
`create_graduated_pipe_renderers()` so calling it per level stays readable. The equivalent
bug in `ppqgis_runpp` was fixed in phase 1.

Verification note: assert renderer identity with `sip.unwrapinstance(layer.renderer())`, not
`id()`. `id()` reports the address of a transient Python wrapper, which CPython recycles, so
distinct C++ renderers can appear equal and a passing `id()` check proves nothing.

### Phase 3 — Non-spatial table support — **done**
- [x] `wkbType` / `extent` / iterator / `merge_df` handle geometry-less tables.
- [x] Verify `trafo` and `load` open as attribute tables.
- [x] Verify a `res_bus` layer opens as a non-spatial table (§5.2) while `bus` keeps its
      merged result columns — check a `loading_percent` renderer still colors lines.

Notes from the implementation:

- `capabilities()` is now **per table** rather than a fixed set. Attribute-only tables drop
  `ChangeGeometries` and `CreateSpatialIndex`; `AddFeatures`/`DeleteFeatures` are advertised
  only for `bus` and `line`, which are the only tables those methods actually implement.
  Previously QGIS was told every layer could do everything, so it offered edits the provider
  then rejected.
- The network *kind* can no longer be inferred from the table name — `trafo` exists in both
  pandapower and pandapipes. Only `junction`/`pipe` imply pipes now.
- The provider validates that the named table exists on the loaded net, so an unknown table
  yields a cleanly invalid layer instead of a late `AttributeError`.
- `getattr(net, 'res_<table>')` is now a **guarded** lookup: not every table has a result
  twin (`switch` has none), and a `res_*` table is its own source with nothing behind it.

Three pre-existing bugs fixed along the way:

- `merge_df()` returned early on an empty table, *before* adding the `pp_type`/`pp_index`
  meta columns, so an empty layer reported a different field list than a populated one.
- The iterator called `self._provider()` — invoking the provider as a function — when
  building a coordinate transform. It would have raised `TypeError` for any request with a
  destination CRS differing from the layer's.
- `fields()` computed a `geometry_type` local that was never used, and printed a debug line
  on every call.

The §6 risk about a silent styling regression is now covered by
`test/test_result_column_merge.py`, which asserts that `vm_pu`/`loading_percent` reach the
layers whose renderers filter on them, that the values are populated rather than NULL, and
that no column name collides between a table and its `res_*` twin. Verified by removing the
merge and confirming the tests fail.

### Phase 4 — Browser integration — **done**
- [x] `PandapowerDataItemProvider` + the item classes, with cheap JSON sniffing
      (`pandapowerNet` **or** `pandapipesNet`).
- [x] Derive the table list from the net object rather than hardcoding table names.
- [x] `Results` collection with greyed-out empty `res_*` items + "run a power flow" tooltip
      (§5.2).
- [x] Refresh the network item after a power flow completes so `Results` un-greys.
- [x] Register/unregister in `initGui()` / `unload()`.
- [x] `PandapowerDataItemGuiProvider` context menus.
- [x] Verify: expand a `.json` in Browser, double-click `bus → 20.0 kV`, layer appears.

**Decision taken during implementation: only populated input tables are listed.** A
pandapower 3 network defines ~33 input tables but a typical grid fills fewer than ten —
`mv_oberrhein` populates 7 and leaves 26 empty (`dcline`, `ssc`, `tcsc`, `vsc_bipolar`,
`ward`, …). Listing all of them buried the useful tables under empty DC and asymmetric ones.
Result tables are handled differently and deliberately: an empty `res_*` **is** listed, greyed
out, because that advertises that a power flow can be run. Result tables whose input table is
absent are dropped too — a `res_ssc` for an empty `ssc` can never hold anything.

Other notes:

- The item classes live in `pandapower_data_items.py` (qgis.core only) and the menus in
  `pandapower_data_item_gui.py` (qgis.gui). Splitting them keeps the items importable
  headless, which is what lets them be unit tested.
- `createChildren()` **releases** the session it borrowed. Without that, merely browsing a
  directory would pin every network in it into memory for the rest of the QGIS session.
- A table is only split into level children when it has **more than one** level; a single
  level would add a pointless nesting layer.
- Both registries take ownership on the C++ side, so the plugin holds Python references and
  removes the providers in `unload()` — otherwise a plugin reload leaves QGIS pointing into
  a module that no longer exists (see the risk in §6).

Testing note: `mv_oberrhein` **ships with results already computed**, so it cannot test the
greyed-out state. `create_cigre_network_mv()` has empty `res_*` tables and is used for that.

### Phase 5 — Data Source Manager entry — **done**
- [x] `PandapowerSourceSelectProvider` + widget.
- [x] `capabilities()` off `FileBasedUris`; drop the vector file filter.
- [x] Verify: "pandapower" appears in the left-hand list next to the DB providers.

Verified in the registry, the entry lists alongside `PostgreSQL`, `MS SQL Server` and
`SAP HANA` — the position §3.1 was aiming for.

**`addLayer` cannot be emitted from Python on QGIS 3.44.** The plan specified the modern
`addLayer(type, url, baseName, providerKey)` signal over the deprecated `addVectorLayer`.
Emitting it from Python segfaults (access violation), and it does so *even with no receiver
connected*, with both an enum and an int for the `Qgis::LayerType` argument. A search of the
QGIS tree shows `addLayer` is emitted only from C++ source selects and by no Python code at
all, so the binding path is untested upstream. The widget therefore emits `addVectorLayer`,
which works and is sufficient — every pandapower table opens as a vector layer, including the
non-spatial ones. `_emit_add_layer()` isolates this so it is a one-line change once the
binding is fixed.

Two corrections to the B2 fix as specified:

- `capabilities()` previously returned `FileBasedUris`, which belongs to the **`ProviderCapability`**
  enum, while `capabilities()` returns **`ProviderMetadataCapability`** — two unrelated enums.
  It now returns `LayerTypesForUri`, and `FileBasedUris` moved to `providerCapabilities()`
  where it is accurate: the URI really does address a file.
- `filters()` returns an empty string rather than a narrowed filter. Contributing any vector
  filter is what put networks into "Add Vector Layer → File", and that dialog is the import
  framing the rework removes.

The widget reuses `list_tables()` and `table_levels()` from the browser module, so the listing
and the tree cannot drift apart. Like `createChildren()`, it **releases** the session after
listing, so browsing networks in the dialog does not pin them into memory.

### Phase 6 — Commit-based writes — **done**
- [x] Wire commit signals; single coalesced write per file.
- [x] mtime check before write, with an overwrite prompt (§5.3); the stored mtime is
      refreshed after every successful write.
- [x] Delete the async save machinery and `_save_in_progress` state.
- [x] Sibling-layer refresh on commit (§5.1).
- [x] Prompt on close when dirty.

`pandapower_provider.py` lost **665 lines and gained 364**, a net ~300 removed, and the
save-race class of bugs is gone with them: there is no longer any state that can be
"in progress", so there is nothing to collide.

How it fits together:

- The mutation methods only touch the shared net and call `_mark_dirty()`.
- `_mark_dirty()` also connects `afterCommitChanges` lazily — the layer does not exist yet
  while the provider is being constructed, so the connection cannot be made in `__init__`.
- `NetworkSession.write()` is the single place the network reaches disk. Because all layers
  share one net, it writes the whole network once instead of each layer merging its slice
  into a re-read copy of the file, which is what the old save threads did.
- Coalescing needs no extra bookkeeping: the first write clears `session.dirty`, so any
  sibling committing in the same action finds a clean session and skips. Verified by counting
  calls to `write()`.

Two pre-existing bugs fixed while in this code:

- `changeGeometryValues()` wrote geometry into `net.<table>.geo`, which is a **Series copy** —
  pandas raised `SettingWithCopyWarning` and the write went into a temporary. It only worked
  because a second write further down targeted the real table. The dead write is gone.
- `_validate_can_save()` and the old save threads re-read the file on every change; with one
  shared net that indirection was obsolete.

### Phase 7 — Retire the import dialog — **done**
- [x] Import **removed**, not merely deprecated: the browser is the only path.
- [x] Export keeps its role (writing a *new* network from arbitrary QGIS layers) — that is a
      genuinely different operation and should stay.
- [x] Update README and user manual.

Deleted: `ppqgis_import.py`, `pandapower_import_dialog.py`,
`pandapower_import_dialog_base.ui`, the toolbar action and its wiring.

Also deleted `geo.py`. Its own header said to remove it once
[pandapower PR #1731](https://github.com/e2nIEE/pandapower/pull/1731) merged; that landed
long ago and pandapower 3.5 ships `pandapower.plotting.geo`. Its only caller was the import
module, so it went with it.

**A behavioural difference worth knowing.** The old import called
`geo.convert_crs(net, ...)`, which **rewrote the network's coordinates in place** to match
the project CRS. Opening a network now leaves the stored coordinates untouched and declares
the CRS on the layer, letting QGIS reproject for display. That is the correct behaviour for a
live data source — the plugin must not silently rewrite the user's data on open — but a user
who relied on import-time reprojection will notice the change.

Three pre-existing bugs fixed here:

- The plugin **failed to load entirely** on a profile where `locale/userLocale` was unset:
  `QSettings().value(...)[0:2]` subscripted `None`. Plugin Builder boilerplate, hit on any
  fresh QGIS profile.
- `metadata.txt` had a stray line, `Category of the plugin: ...`, missing its `#`, which
  parses as a config key rather than a comment.
- A comment in the provider still pointed at `ppqgis_import.py` for context that had moved.

## 5. Resolved design decisions

These four were open in the first draft and are now decided. Each has consequences that are
folded into the phases above.

### 5.1 Voltage-level layers: allow the edit, refresh, warn once

A `bus @ 20 kV` layer is a filtered view. If the user edits `vn_kv` so a feature no longer
matches the filter, the edit is **allowed**; the feature disappears from this layer on
refresh and appears in the layer for its new voltage level (if one is open).

Implementation:

- Do **not** validate `vn_kv` against the layer filter in `_validate_field_value`.
- On commit, if any changed row's filter column moved out of range, refresh this layer and
  every sibling layer of the same file (they share one `net` — §3.3 makes this cheap).
- Warn **once per session**, not once per feature, via a `MessageManager` info bar:
  *"Feature 42 moved to voltage level 110.0 kV and is no longer shown in this layer."*
  Track a `NetworkSession._voltage_move_warned` flag so a bulk edit of 500 features produces
  one message, not 500.

The filter column is `vn_kv` for `bus` and — per
[merge_df()](../pandapower-qgis/pandapower_provider.py#L210) — the `vn_kv` of `from_bus` for
`line`. So **editing a line's `from_bus` can also move it between layers.** Both cases go
through the same refresh-and-warn path.

### 5.2 `res_*` tables: merged *and* separately listed

Results serve two distinct purposes and get two representations of the same data:

1. **Merged into `bus`/`line` as columns** — unchanged from today's `merge_df()`. This is
   required: renderers color buses by `vm_pu` and lines by `loading_percent`
   ([renderer_utils.py](../pandapower-qgis/renderer_utils.py)), and map tips read result
   columns. Breaking this would break styling.
2. **As their own browser items** — `res_bus`, `res_line`, `res_trafo`, … opening as
   attribute-only tables (§3.6). This is where a power-flow run surfaces its output, which is
   how pandapower returns results.

There is no duplication of *state*: both views read the same `net.res_*` DataFrame through
the shared session. The merged columns are a projection, not a copy.

Tree placement — `res_*` items are grouped under a **Results** collection so the top level
stays readable:

```
mv_oberrhein.json
├── bus
│   ├── 20.0 kV
│   └── 110.0 kV
├── line
│   ├── 20.0 kV
│   └── 110.0 kV
├── trafo
├── load
└── Results
    ├── res_bus       (grey when empty)
    ├── res_line      (grey when empty)
    └── res_trafo     (grey when empty)
```

**Empty results are shown, greyed out.** When `net.res_bus` is empty, the item is still
listed, rendered disabled (`setState`/dimmed icon) with tooltip *"No results — run a power
flow"*. This makes the capability discoverable instead of hiding it. Double-clicking a greyed
item offers to run the power flow rather than opening an empty table.

After a power flow completes, `ppqgis_runpp` must refresh the network item so the `Results`
children un-grey — one `item.refresh()` call on the session's browser item.

#### 5.2.1 Future: multiple load cases

Out of scope for now, recorded so the current design does not foreclose it.

A network may eventually carry **several result sets** — different load cases, time steps or
scenarios — that the user switches between to visualise different situations in one grid
model. That turns today's 1:1 assumption (one table, one index-aligned `res_*` twin) into
1:N, plus a notion of which set is currently active.

Two properties of the current code make this a small change rather than a rewrite, and
should be preserved:

- **The active case belongs on `NetworkSession`, not on the provider.** All layers of a file
  share one session, so switching the case is one assignment plus one
  `notify_changed()` — every layer rebuilds and repaints together. Putting it on the provider
  would mean walking layers and risk them disagreeing about which case is displayed.
- **`merge_df()` reaches its result table through a single guarded lookup**
  (`getattr(net, 'res_<table>', None)`). Redirecting that one line at a case-specific frame
  is the whole provider-side change.

The open question is where the cases live. `net.res_bus` is singular by design, so multi-case
data usually sits in an `OutputWriter`, a timeseries result store, or a user convention
outside the standard pandapower schema. Which of those is authoritative decides whether this
is a provider change or a new session-level concept — worth settling before designing it.

### 5.3 Concurrent external edits: mtime check at commit

`NetworkSession` records the file's `st_mtime` and size at load. Before writing on commit it
re-stats the file:

- **Unchanged** → write normally.
- **Changed** → block the write and prompt: *Overwrite* / *Reload from disk and discard my
  changes* / *Cancel*. Never silently overwrite; a power-flow script writing the same JSON
  from outside QGIS is a realistic scenario in this workflow.
- Refresh the stored mtime after every successful write, so the next commit compares against
  our own write rather than the original load.

The same check runs when `ppqgis_runpp` writes results back, since that is also an external
mutation of the file from the session's point of view.

### 5.4 pandapipes: keep the seams, integrate later

pandapipes was removed in `8e0d6f0` and **will be integrated later**. Therefore:

- Do **not** strip the `junction` / `pipe` branches from the provider, iterator or
  `_load_network_from_file`. Leave them in place as unexecuted paths.
- Do **not** widen them either — no new pandapipes work in this plan.
- Design the new code so pipes drop in without restructuring:
  - the JSON sniff (§3.2) checks for `"pandapowerNet"` **or** `"pandapipesNet"` and records
    which on the session, rather than hardcoding the electrical case;
  - `NetworkSession` carries a `kind` field (`"power"` / `"pipes"`) driving which module
    (`pandapower` vs `pandapipes`) loads and saves the file;
  - the table list in the browser is **derived from the net object**, not a hardcoded list of
    electrical table names — then `junction`/`pipe`/`valve` appear for free.
- The voltage sublevel logic (§3.2) is electrical-specific; its pipes analogue is `pn_bar`.
  Keep the sublevel key as a session-provided attribute name rather than a literal `vn_kv`.

Tracked as follow-up work, not a phase in §4.

## 6. Risks

- **Browser performance.** `createDataItem` runs per `.json` per directory expansion. If the
  sniff is not bounded-read, expanding a folder of large networks will stall the UI. This is
  the single most likely regression.
- **Sibling-layer refresh storms.** §5.1 refreshes every layer of a file when a feature
  changes voltage level. With many layers open this can cascade. Coalesce to one refresh per
  commit, never one per changed feature.
- **Styling regression from `res_*` work.** §5.2 keeps result columns merged precisely so
  renderers keep working. Any refactor that "cleans up" `merge_df()` by removing the merge
  will silently break bus/line coloring — the failure is visual, so tests won't catch it.
- **Python GUI provider lifetime.** `addProvider()` transfers ownership to C++
  (`/Transfer/` in the SIP files). Keep Python references alive and remove providers in
  `unload()`, or plugin reload will crash QGIS.
- **Project reload.** Restoring a `.qgz` constructs providers before any browser interaction;
  `NetworkSession` must be able to cold-load from the URI path alone. The existing
  `_load_network_from_file` fallback already does this and must be preserved.
- **Scope.** Phases 1–3 are refactors with no visible benefit to the user. They are
  prerequisites, not optional; resist shipping Phase 4/5 on top of `NetworkContainer`.
