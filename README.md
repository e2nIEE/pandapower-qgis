# pandapower-qgis

Plugin for interaction between QGis and pandapower Networks.

Import and export of pandapower networks.

---

## Overview

- [Pandapower](#pandapower)
  - [Import from pandapower](#import-from-pandapower)
  - [Editing the network](#editing-the-network-in-qgis)
  - [Run pandapower network](#run_pandapower_network)
  - [Export to pandapower](#export-to-pandapower)

---

## pandapower

### Import from pandapower 
![import icon][import_icon]  
This icon can be found in the menu.  
The plugin can automatically detect if you are importing a pandapower
or pandapipes network, it will show only relevant settings.

![import_guide][import_guide]  

#### • crs - coordinate reference system
Selecting the appropriate crs is required as pandapower does
not store this information by default.

The crs for the resulting GeoJSON is taken from the QGIS Project.
GeoJSON has deprecated support for crs, WGS-84 is highly recommended.
If a specific crs is preferred it is recommended to create a Project
with that crs first and then import the network.

#### • run pandapower
If this option is selected `pandapower.runpp()`
is executed before exporting any data.

#### • color lines by load
If this option is selected the network is coloured by load for each line individually.
However, if this option is selected but the network's power was not calculated,
the network will be grayed out.
If this option is not selected, the different voltage levels are colored in different colors.

---

### Editing the network in QGIS

#### Required Attributes

`line`

| name      | type      | comment                     |
|-----------|-----------|-----------------------------|
| from_bus  | integer   | pandapower id               |
| to_bus    | integer   | pandapower id               |
| std_type  | string    | name of a standard linetype |

#### Optional Attributes

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

<br>

#### Supported Editing Options
This plugin supports standard QGIS editing operations with **pandapower-specific validations**:
- Add features (bus/line nodes)
- Delete features (bus/line nodes)
- Modify attributes values
- Move features (geometry changes)

<br>

#### ⚠️ Important Notes

**Bus Deletion (Cascade Delete)**
- Deleting a bus will **cascade delete** all connected elements (lines, loads, transformers, generators, etc.)
- A confirmation dialog shows all affected elements before deletion
- This action cannot be undone (a timestamped backup is created automatically)

**Line Creation Requirements**
- Required fields: `from_bus`, `to_bus`, `length_km`
- `std_type` field:
  - If provided: Standard line type name (e.g., "NAYY 4x50 SE")
  - If NULL or empty: You **must** provide `r_ohm_per_km`, `x_ohm_per_km`, `c_nf_per_km`

**Validation Rules**
- `from_bus`/`to_bus` must reference existing bus IDs
- Physical parameters (`length_km`, `r_ohm_per_km`, etc.) must be positive
- Required fields cannot be NULL

**Automatic Backup**
- All changes automatically create a timestamped backup file (`.bak`)
- Format: `network.json.20231215_143022.bak`

**Async Save**
- Changes are saved in the background (UI remains responsive)
- Cannot edit while a save operation is in progress

<br>

#### How to use editing operation
Add features / Delete features / Modify attribute values Operations are
standard QGIS editing operations of point and line.  
For general editing instructions, please refer to the [QGIS documentation](https://docs.qgis.org/latest/en/docs/user_manual/working_with_vector/editing_geometry_attributes.html).

To **change the feature's geometry(position)** through mouse clicks needs to be explained:  

![move_feature_guide]

click a layer to edit in Layers panel and activate layer editing mode
![toggle_editing_icon].  
Then select the Move Feature tool ![move_feature_icon].

Click on the feature and then click on the desired location to change the feature's position.  
Click ![toggle_editing_icon] once more to save the edit.  
When the layer editing mode is deactivated, the changes can be saved,
and a backup file will be created to preserve the previous data.

---

### Run pandapower load flow
![run_icon][run_icon]  
This icon can be found in the menu.  
Here you can configure the options required for running pandapower network.  

![run_guide]
#### • RunPP Options
- Function: Various run functions can be selected.
- Parameter(**kwargs): You can directly input parameters in the following formats.
	- key1=value1, key2=value2
	- {'key1': 'value1', 'key2': value2}
	- key1='value1', key2=value2
- Note: Information about the runpp function and options can be found at the link below.
    https://pandapower.readthedocs.io/en/latest/powerflow/ac.html
- Note: If you enter an incorrect parameter name, the function will run with the default value for that parameter.
- Network initialization method: auto, flat, results

---

### Export to pandapower
![export icon][export_icon]  
This icon can be found in the menu.

![export_guide][export_guide]
#### • Name
This is optional. The name is set when creating the pandapower network

#### • Frequency
Default value: 50 \
The Frequency of the network in Hz.

#### • Reference apparent power p.U.
Default value: 1 \
The Reference apparent power per Unit.

#### • add standard types
If selected the pandapower standard types are added to the
network.

#### • Select layers to export
The plugin attempts to export all selected layers.
It will export all features of vector layers
that have `pp_type` set to `bus` or `line`.

---

[import_icon]: ./pp_import.svg "import to QGIS"
[export_icon]: ./pp_export.svg "export from QGIS"
[run_icon]: ./pp.png "run pandapower network"
[import_guide]: user_manual_image/import.png "how to import"
[run_guide]: user_manual_image/run.png "how to run"
[move_feature_guide]: user_manual_image/move_feature.png "how to move"
[export_guide]: user_manual_image/export.png "how to export"
[toggle_editing_icon]: user_manual_image/toggle_editing_icon.png "toggle editing icon"
[move_feature_icon]: user_manual_image/move_feature_icon.png "move feature icon"