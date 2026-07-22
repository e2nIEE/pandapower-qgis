title Compile Translation strings

:: change directory to i18n folder
cd /d %~dp0\..\i18n

:: run command
:: TODO: this should be modified at some point to autodetect .ts files
REM compiling language strings...
lrelease ^
-removeidentical ^
pandapower_qgis_de.ts ^
pandapower_qgis_en.ts