# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ppqgisDialog
                                 A QGIS plugin
 Plugin to work with pandapower networks
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2022-09-23
        git sha              : $Format:%H$
        copyright            : (C) 2022 by Fraunhofer IEE
        email                : mike.vogt@iee.fraunhofer.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os

from qgis.PyQt import uic, QtWidgets

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'pandapower_export_dialog_base.ui'))


class ppExportDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(ppExportDialog, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        self.power = True
        self.convert_to_power()
        self.powerPipesToggle.clicked.connect(self.switch)

    def convert_to_pipes(self):
        self.setWindowTitle(self.tr("Export pandapipes network"))
        # set frequencyHLayout content invisible
        self.frequencyEdit.setVisible(False)
        self.frequencyLabel.setVisible(False)
        self.frequencyUnitLabel.setVisible(False)
        # set repApHLayout content invisible
        self.refApparentPowerEdit.setVisible(False)
        self.refApparentPowerLabel.setVisible(False)
        # set pipesFluidHLayout content visible
        self.fluidLabel.setVisible(True)
        self.fluidLineEdit.setVisible(True)
        # change button label
        self.powerPipesToggle.setText(self.tr("switch to export pandapower"))

    def convert_to_power(self):
        self.setWindowTitle(self.tr("Export pandapower network"))
        # set pipesFluidHLayout content invisible
        self.fluidLabel.setVisible(False)
        self.fluidLineEdit.setVisible(False)
        # set frequencyHLayout content visible
        self.frequencyEdit.setVisible(True)
        self.frequencyLabel.setVisible(True)
        self.frequencyUnitLabel.setVisible(True)
        # set repApHLayout content visible
        self.refApparentPowerEdit.setVisible(True)
        self.refApparentPowerLabel.setVisible(True)
        # change button label
        self.powerPipesToggle.setText(self.tr("switch to export pandapipes"))

    def switch(self):
        if self.power:
            self.convert_to_pipes()
        else:
            self.convert_to_power()
        self.power = not self.power
