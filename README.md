# pandapower-qgis

Plugin for interaction between QGIS and pandapower networks.

A pandapower network is opened as a **data source**, the way you would open a
PostgreSQL or SAP HANA database — not imported. You edit the geodata in QGIS and
the changes are written back to the same `.json` file. There is no import step
and no separate export step to get your work back out.

---

## Overview

- [Opening a network](#opening-a-network)
  - [From the Browser](#from-the-browser)
  - [From the Data Source Manager](#from-the-data-source-manager)
  - [What the tree shows](#what-the-tree-shows)
- [Editing the network](#editing-the-network)
- [Run a power flow](#run-a-power-flow)
- [Export to pandapower](#export-to-pandapower)

---

## Opening a network

### From the Browser

Expand any pandapower `.json` in the QGIS **Browser** panel and it opens like a
database, listing the tables it contains. Double-click a table, or drag it onto
the canvas, to add it as a layer.

Right-clicking a network offers *Add all geometry layers to project*,
*Run power flow*, *Save network* and *Reload from disk*.

### From the Data Source Manager

**Layer → Data Source Manager → pandapower** — the entry sits with the database
providers. Pick a network file, select one or more tables, press **Add**.

The dialog lists each table with its geometry type, voltage level and feature
count, and remembers recently opened networks.

### What the tree shows

```
mv_oberrhein.json
├── bus                  ← splits by voltage level
│   ├── 20.0 kV
│   └── 110.0 kV
├── line
│   └── 20.0 kV
├── trafo                ← attribute-only table
├── load
├── sgen
├── switch
└── Results
    ├── res_bus          ← greyed out until a power flow has run
    └── res_line
```

- `bus` and `line` carry geometry and are split by voltage level.
- Tables without geometry (`trafo`, `load`, `switch`, …) open as plain attribute
  tables, exactly like a non-spatial table in a database.
- Only tables that actually contain rows are listed. A pandapower network defines
  many more tables than a typical grid uses.
- Result tables live under **Results**. An empty one is still listed, greyed out —
  double-click it to run a power flow.

Result columns are also **merged into** the `bus` and `line` layers, which is what
lets the renderers colour buses by `vm_pu` and lines by `loading_percent`.

#### Coordinate reference system

pandapower does not record a CRS, so the plugin assumes **EPSG:4326** unless the
URI says otherwise. The network's coordinates are left exactly as they are; QGIS
reprojects for display. Set your project CRS as you like — your data is not
rewritten.

---

## Editing the network

### Supported operations

Standard QGIS editing, with pandapower-specific validation:

- Add features (bus / line)
- Delete features (bus / line)
- Modify attribute values
- Move features (geometry changes)

Click the layer in the Layers panel, toggle editing ![toggle_editing_icon], and
use the Move Feature tool ![move_feature_icon] to reposition a feature:

![move_feature_guide]

For general instructions see the
[QGIS documentation](https://docs.qgis.org/latest/en/docs/user_manual/working_with_vector/editing_geometry_attributes.html).

### When changes are written

Edits are held in the layer's edit buffer and written to the `.json` **when you
save the layer edits** — the same moment QGIS would commit to any other data
source. Toggling editing off and confirming, or pressing *Save Layer Edits*,
writes the file.

- **Rolling back an edit writes nothing.** The file is untouched.
- All layers of one network share a single in-memory network, so an edit made in
  one layer is immediately visible in the others, and one save writes them all.
- A timestamped backup (`network.json.20231215_143022.bak`) is written before the
  file is overwritten.
- If the file changed on disk since it was opened, you are asked before it is
  overwritten.

### Required attributes

`line`

| name      | type      | comment                     |
|-----------|-----------|-----------------------------|
| from_bus  | integer   | pandapower id               |
| to_bus    | integer   | pandapower id               |
| std_type  | string    | name of a standard linetype |

### Optional attributes

`bus`

| name       | type    | default value | comment                         |
|------------|---------|---------------|---------------------------------|
| name       | string  | None          |                                 |
| pp_index   | int     | None          | these might change after export |
| type       | string  | b             |                                 |
| zone       | string  | None          |                                 |
| in_service | boolean | True          |                                 |
| max_vm_pu  | float   | NAN           |                                 |
| min_vm_pu  | float   | NAN           |                                 |

`line`

| name                | type    | default value | comment                           |
|---------------------|---------|---------------|-----------------------------------|
| length_km           | float   |               | if not present derived from QGIS  |
| name                | string  | None          |                                   |
| in_service          | boolean | True          |                                   |
| df                  | float   | 1.0           |                                   |
| parallel            | integer | 1             |                                   |
| max_loading_percent | float   |               |                                   |
| pp_index            | integer | None          | these might change after export   |

### ⚠️ Important notes

**Bus deletion (cascade delete)**
- Deleting a bus **cascade deletes** every connected element (lines, loads,
  transformers, generators, …)
- A confirmation dialog lists the affected elements first
- A timestamped backup is written when the change is saved

**Line creation requirements**
- Required fields: `from_bus`, `to_bus`, `length_km`
- `std_type`:
  - If provided: a standard line type name (e.g. `NAYY 4x50 SE`)
  - If NULL or empty: you **must** provide `r_ohm_per_km`, `x_ohm_per_km`,
    `c_nf_per_km`

**Validation rules**
- `from_bus` / `to_bus` must reference existing bus IDs
- Physical parameters (`length_km`, `r_ohm_per_km`, …) must be positive
- Required fields cannot be NULL

**Editable tables**
- Adding and deleting rows is implemented for `bus` and `line`
- Other tables open read-mostly: attribute values can be changed, but rows cannot
  be added or deleted from QGIS

---

## Run a power flow

![run_icon][run_icon]
This icon is in the plugin toolbar. It is also on the context menu of a network
or the **Results** group in the Browser.

![run_guide]

#### • RunPP options
- **Function**: which pandapower run function to use.
- **Parameter (\*\*kwargs)**: parameters in any of these forms:
  - `key1=value1, key2=value2`
  - `{'key1': 'value1', 'key2': value2}`
  - `key1='value1', key2=value2`
- **Initialization**: `auto`, `flat` or `results`

An unrecognised parameter name falls back to that parameter's default. See the
[pandapower power flow documentation](https://pandapower.readthedocs.io/en/latest/powerflow/ac.html).

After a run, the **Results** tables fill and any layer coloured by a result
column repaints.

---

## Export to pandapower

![export icon][export_icon]
This icon is in the plugin toolbar.

Export builds a **new** pandapower network from arbitrary QGIS vector layers. It
is a different operation from opening a network: use it to turn layers that did
not come from pandapower into a network. To save changes to a network you opened
with this plugin, just save the layer edits — see
[When changes are written](#when-changes-are-written).

![export_guide][export_guide]

#### • Name
Optional. The name given to the new pandapower network.

#### • Frequency
Default `50`. The network frequency in Hz.

#### • Reference apparent power p.U.
Default `1`. The reference apparent power per unit.

#### • Add standard types
Adds the pandapower standard types to the network.

#### • Select layers to export
All selected layers are exported. Features are taken from vector layers whose
`pp_type` is `bus` or `line`.

---

## Requirements

- QGIS 3.44 or newer
- pandapower 3.5 or newer (geodata is read from the `geo` column)

See `pandapower-qgis/requirements.txt` for the full list.

---

[export_icon]: ./pp_export.svg "export from QGIS"
[run_icon]: ./pp.png "run pandapower network"
[run_guide]: user_manual_image/run.png "how to run"
[move_feature_guide]: user_manual_image/move_feature.png "how to move"
[export_guide]: user_manual_image/export.png "how to export"
[toggle_editing_icon]: user_manual_image/toggle_editing_icon.png "toggle editing icon"
[move_feature_icon]: user_manual_image/move_feature_icon.png "move feature icon"
