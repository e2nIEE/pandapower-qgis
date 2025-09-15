# pandapower-qgis

Plugin for interaction between QGis and pandapower Networks.

Import and export of pandapower networks.

---

## Overview

- [pandapower](#pandapower)
  - [import from pandapower](#import-from-pandapower)
  - [Editing the network](#editing-the-network-in-qgis)
  - [run pandapower network](#run_pandapower_network)
  - [export to pandapower](#export-to-pandapower)

---

## pandapower

### import from pandapower 
![import icon][import_icon]

The plugin can automatically detect if you are importing a pandapower
or pandapipes network, it will show only relevant settings.

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

#### • Select save folder
If no folder is selected the network will be loaded into QGIS from memory.
The network then can not be edited directly.
If a folder is selected each layer will be saved there as a GeoJSON file and
then loaded into QGIS. The network can then be edited directly from within QGIS.
It is recommended to select a save folder.

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

To change the feature's position through mouse clicks:  
click on the desired layer → activate layer editing mode → select the Move Feature tool  

Click on the feature and then click on the desired location to change the feature's position.  
When the layer editing mode is deactivated, the changes can be saved,
and a backup file will be created to preserve the previous data.
---

### run pandapower network
![import icon][run_icon]

#### • RunPP Options
Here you can configure the options required for running pandapower network.

- Function: various run functions can be selected.
- Parameter(**kwargs): You can directly input parameters in the following formats.
	- key1=value1, key2=value2
	- {'key1': 'value1', 'key2': value2}
	- key1='value1', key2=value2
- Note: If you enter an incorrect parameter name, the function will run with the default value for that parameter.
- Network initialization method: auto, flat, results

---

### export to pandapower
![export icon][export_icon]

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