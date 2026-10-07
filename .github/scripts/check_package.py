"""
Check that a plugin package built by qgis-plugin-ci is complete and well-formed.

qgis-plugin-ci packages from git, so a module that was never committed is
silently left out and the plugin fails to load for users while working
perfectly in the developer's checkout.

Usage: python3 .github/scripts/check_package.py <expected top-level directory>
"""
import glob
import os
import sys
import zipfile


def main(expected_directory):
    archives = glob.glob('*.zip')
    if len(archives) != 1:
        print('::error::Expected exactly one plugin package, found {}.'.format(archives))
        return 1
    archive = archives[0]
    names = zipfile.ZipFile(archive).namelist()

    # plugins.qgis.org identifies a plugin by the directory at the top of the
    # zip. A different directory is a different plugin: the upload is rejected,
    # and users of the existing plugin would never receive the update.
    top_level = sorted({name.split('/')[0] for name in names})
    if top_level != [expected_directory]:
        print('::error::{} unpacks to {}, expected only {!r}. '
              'Check use_project_slug_as_plugin_directory in .qgis-plugin-ci.'
              .format(archive, top_level, expected_directory))
        return 1

    shipped = {os.path.basename(name) for name in names if name.endswith('.py')}
    on_disk = {os.path.basename(path) for path in glob.glob('pandapower-qgis/*.py')}
    missing = sorted(on_disk - shipped)
    if missing:
        print('::error::These modules exist but are not in the package.')
        print('Most likely they were never committed to git:')
        for name in missing:
            print('  -', name)
        return 1

    print('{} unpacks to {}/ and contains all {} plugin modules.'.format(
        archive, expected_directory, len(on_disk)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
