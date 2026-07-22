# coding=utf-8
"""Common functionality used by the test suite.

Run the tests from the repository root with the QGIS Python interpreter, e.g.
on Windows with an OSGeo4W install::

    C:\\OSGeo4W\\bin\\python-qgis.bat -m unittest discover -s test -t .
"""

import logging
import sys

LOGGER = logging.getLogger('QGIS')

QGIS_APP = None  # Holds the single QgsApplication used by the whole test run


def get_qgis_app():
    """Start one QgsApplication to test against.

    The instance is created once per process and reused, since QGIS does not
    support more than one QgsApplication per process.

    :returns: The running QgsApplication, or None if QGIS cannot be imported.
    :rtype: QgsApplication
    """
    global QGIS_APP  # pylint: disable=W0603

    if QGIS_APP is not None:
        return QGIS_APP

    try:
        from qgis.core import QgsApplication
    except ImportError:
        LOGGER.exception(
            'Could not import QGIS. Run the tests with the QGIS Python '
            'interpreter (e.g. C:/OSGeo4W/bin/python-qgis.bat).')
        return None

    # QgsApplication expects argv as a list of bytes, not str.
    argv = [arg.encode('utf-8') for arg in sys.argv]
    # GUI mode is off: the suite is headless and needs no widgets.
    QGIS_APP = QgsApplication(argv, False)
    QGIS_APP.initQgis()
    LOGGER.debug(QGIS_APP.showSettings())

    return QGIS_APP
