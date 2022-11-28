title Update Translation strings

:: change directory to i18n folder
cd /d %~dp0\..\i18n

:: run command
REM updating language strings...
pylupdate5 -noobsolete ^
pandapower_qgis.pro

