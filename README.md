# pandapower-qgis

Plugin for interaction between QGis and pandapower or pnadapipes Networks

Import and export of pandapower and pandapipes networks.

---

## Overview

- [pandapower](#pandapower)
  - [import from pandapower](#import-from-pandapower)
  - [Editing the network](#editing-the-network-in-qgis)
  - [export to pandapower](#export-to-pandapower)
- [pandapipes](#pandapipes) 
  - [import from pandapipes](#import-from-pandapipes)
  - [Editing the network](#editing-the-network-in-qgis-1)
  - [export to pandapipes](#export-to-pandapipes)

---

## pandapower

### import from pandapower ![import icon](./pp_import.svg){: height=25}

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
If not the different voltage levels are colored in different colors.

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

### export to pandapower ![export icon](./pp_export.svg){: height=25}

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

## pandapipes

### import from pandapipes ![import icon](./pp_import.svg){: height=25}

The plugin can automatically detect if you are importing a pandapower
or pandapipes network, it will show only relevant settings.

#### • crs - coordinate reference system
Selecting the appropriate crs is required as pandapipes does
not store this information by default.

The crs for the resulting GeoJSON is taken from the QGIS Project.
GeoJSON has deprecated support for crs, WGS-84 is highly recommended.
If a specific crs is preferred it is recommended to create a Project
with that crs first and then import the network.

#### • run pandapipes
If this option is selected `pandapipes.runpp()`
is executed before exporting any data.

#### • color pipes by pressure
If this option is selected the network is coloured by pressure for each line individually.
If not the different pressure levels are colored in different colors.

#### • Select save folder
If no folder is selected the network will be loaded into QGIS from memory.
The network then can not be edited directly.
If a folder is selected each layer will be saved there as a GeoJSON file and
then loaded into QGIS. The network can then be edited directly from within QGIS.
It is recommended to select a save folder.

---

### Editing the network in QGIS

#### Required Attributes

`junction`

| name     | type  | comment                 |
|----------|-------|-------------------------|
| pn_bar   | float | fluid pressure in bar   |
| tfluid_k | float | fluid temperature in °K |

`pipe`

| name       | type    | comment                     |
|------------|---------|-----------------------------|
| from_bus   | integer | pandapower id               |
| to_bus     | integer | pandapower id               |
| diameter_m | float   |                             |

#### Optional Attributes

`junction`

| name       | type    | default value | comment                         |
|------------|---------|---------------|---------------------------------|
| height_m   | float   | 0             |                                 |
| name       | string  | None          |                                 |
| pp_index   | int     | None          | these might change after export |
| in_service | boolean | True          |                                 |

`pipe`

| name             | type    | default value | comment                              |
|------------------|---------|---------------|--------------------------------------|
| length_km        | float   |               | if not present derived from QGIS     |
| k_mm             | float   | 1.0           | pipe roughness                       |
| loss_coefficient | float   | 0.0           | additional pressure loss coefficient |
| sections         | integer | 1             | number of internal pipe sections     |
| alpha_w_per_m2k  | float   | 0.0           | heat transfer coefficient            |
| qext_w           | float   | 0.0           | external heat input                  |
| text_k           | float   | 293           | ambient temperature of pipe          |
| name             | string  | None          |                                      |
| in_service       | boolean | True          |                                      |
| pp_index         | integer | None          | these might change after export      |

### export to pandapipes ![export icon](./pp_export.svg){: height=25}

#### • Name
This is optional. The name is set when creating the pandapower network

#### • Fluid
If the fluid is in the standard library this is used to create the pipes.
If not the pipes are created using the properties from the attributes table.

#### • add standard types
If selected the pandapipes standard types are added to the
network.

#### • Select layers to export
The plugin attempts to export all selected layers.
It will export all features of vector layers
that have `pp_type` set to `junction` or `pipe`.