#!/usr/bin/env python
#
# setup.py
#
# Copyright (C) 2009 Damien Churchill <damoxc@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301  USA
#

import os
import os.path as osp
import sys
import platform

from setuptools import setup, Extension
from setuptools.command.test import test as TestCommand

LINK_FREETDS_STATICALLY = True
LINK_OPENSSL = False

ROOT = osp.abspath(osp.dirname(__file__))

def fpath(*parts):
    """
    Return fully qualified path for parts, e.g.
    fpath('a', 'b') -> '<this dir>/a/b'
    """
    return osp.join(ROOT, *parts)

have_c_files = osp.exists(fpath('_mssql.c')) and osp.exists(fpath('pymssql.c'))

from distutils import log
from distutils.cmd import Command
from distutils.command.clean import clean as _clean
if have_c_files:
    from distutils.command.build_ext import build_ext as _build_ext
else:
    #
    # Force `setup_requires` stuff like Cython to be installed before proceeding
    #
    from setuptools.dist import Distribution
    Distribution(dict(setup_requires='Cython>=0.19.1'))

    from Cython.Distutils import build_ext as _build_ext
import struct

def add_dir_if_exists(filtered_dirs, *dirs):
    for d in dirs:
        if osp.exists(d):
            filtered_dirs.append(d)

_extra_compile_args = [
    '-DMSDBLIB'
]

WINDOWS = False
SYSTEM = platform.system()

print("setup.py: platform.system() => %r" % SYSTEM)
print("setup.py: platform.architecture() => %r" % (platform.architecture(),))
if SYSTEM != 'Windows':
    print("setup.py: platform.libc_ver() => %r" % (platform.libc_ver(),))

# 32 bit or 64 bit system?
BITNESS = struct.calcsize("P") * 8

include_dirs = []
library_dirs = []
if sys.platform == 'win32':
    WINDOWS = True
else:
    FREETDS = None

    if sys.platform == 'darwin':
        FREETDS = fpath('freetds', 'darwin_%s' % BITNESS)
        print("""setup.py: Detected Darwin/Mac OS X.
    You can install FreeTDS with Homebrew or MacPorts, or by downloading
    and compiling it yourself.

    Homebrew (http://brew.sh/)
    --------------------------
    brew install freetds

    MacPorts (http://www.macports.org/)
    -----------------------------------
    sudo port install freetds
        """)

    if not os.getenv('PYMSSQL_DONT_BUILD_WITH_BUNDLED_FREETDS'):
        if SYSTEM == 'Linux':
            FREETDS = fpath('freetds', 'nix_%s' % BITNESS)
        elif SYSTEM == 'FreeBSD':
            print("""setup.py: Detected FreeBSD.
    For FreeBSD, you can install FreeTDS with FreeBSD Ports or by downloading
    and compiling it yourself.
            """)

    if FREETDS and osp.exists(FREETDS) and os.getenv('PYMSSQL_BUILD_WITH_BUNDLED_FREETDS'):
        print('setup.py: Using bundled FreeTDS in %s' % FREETDS)
        include_dirs.append(osp.join(FREETDS, 'include'))
        library_dirs.append(osp.join(FREETDS, 'lib'))
    else:
        print('setup.py: Not using bundled FreeTDS')

    libraries = ['sybdb']

    # check for clock_gettime, link with librt for glibc<2.17
    from dev import ccompiler
    compiler = ccompiler.new_compiler()
    if not compiler.has_function('clock_gettime(0,NULL)', includes=['time.h']):
        if compiler.has_function('clock_gettime(0,NULL)', includes=['time.h'], libraries=['rt']):
            libraries.append('rt')
        else:
            print("setup.py: could not locate 'clock_gettime' function required by FreeTDS.")
            sys.exit(1)

usr_local = '/usr/local'
if osp.exists(usr_local):
    add_dir_if_exists(
        include_dirs,
        osp.join(usr_local, 'include'),
        osp.join(usr_local, 'include/freetds'),
        osp.join(usr_local, 'freetds/include')
    )
    add_dir_if_exists(
        library_dirs,
        osp.join(usr_local, 'lib'),
        osp.join(usr_local, 'lib/freetds'),
        osp.join(usr_local, 'freetds/lib')
    )

if sys.platform == 'darwin':
    fink = '/sw'
    if osp.exists(fink):
        add_dir_if_exists(include_dirs, osp.join(fink, 'include'))
        add_dir_if_exists(library_dirs, osp.join(fink, 'lib'))

    macports = '/opt/local'
    if osp.exists(macports):
        # some mac ports paths
        add_dir_if_exists(
            include_dirs,
            osp.join(macports, 'include'),
            osp.join(macports, 'include/freetds'),
            osp.join(macports, 'freetds/include')
        )
        add_dir_if_exists(
            library_dirs,
            osp.join(macports, 'lib'),
            osp.join(macports, 'lib/freetds'),
            osp.join(macports, 'freetds/lib')
        )

if sys.platform != 'win32':
    # Windows uses a different piece of code to detect these
    print('setup.py: include_dirs = %r' % include_dirs)
    print('setup.py: library_dirs = %r' % library_dirs)

class build_ext(_build_ext):
    """
    Subclass the Cython build_ext command so it:
    * Can handle different C compilers on Windows
    * Links in the libraries we collected
    """

    def build_extensions(self):
        global library_dirs, include_dirs, libraries

        if WINDOWS:
            # Detect the compiler so we can specify the correct command line switches
            # and libraries
            from distutils.cygwinccompiler import Mingw32CCompiler
            extra_cc_args = []
            if isinstance(self.compiler, Mingw32CCompiler):
                # Compiler is Mingw32
                extra_cc_args = [
                    '-Wl,-allow-multiple-definition',
                    '-Wl,-subsystem,windows-mthreads',
                    '-mwindows',
                    '-Wl,--strip-all'
                ]
                libraries = [
                    'libiconv', 'iconv',
                    'sybdb',
                    'ws2_32', 'wsock32', 'kernel32',
                ]
            else:
                # Assume compiler is Visual Studio
                if LINK_FREETDS_STATICALLY:
                    libraries = [
                        'iconv', 'replacements',
                        'db-lib', 'tds', 'tdsutils',
                        'ws2_32', 'wsock32', 'kernel32', 'shell32',
                    ]
                    if LINK_OPENSSL:
                        libraries.extend([
                            'libeay{}MD'.format(BITNESS),
                            'ssleay{}MD'.format(BITNESS)
                        ])
                else:
                    libraries = [
                        'ct', 'sybdb',
                        'ws2_32', 'wsock32', 'kernel32', 'shell32',
                    ]
                    if LINK_OPENSSL:
                        libraries.extend(['libeay32MD', 'ssleay32MD'])

            FREETDS = 'freetds'
            suffix = '' if BITNESS == 32 else '64'
            OPENSSL = fpath('openssl', 'lib{}'.format(suffix))
            for e in self.extensions:
                e.extra_compile_args.extend(extra_cc_args)
                e.libraries.extend(libraries)
                e.include_dirs.append(osp.join(FREETDS, 'include'))
                e.library_dirs.append(osp.join(FREETDS, 'lib'))
                e.include_dirs.append(osp.join(ROOT, 'build', 'include'))
                e.library_dirs.append(osp.join(ROOT, 'build', 'lib'))
                if LINK_OPENSSL:
                    freetds_lib_dir = ''
                else:
                    freetds_lib_dir = 'lib'
                if LINK_FREETDS_STATICALLY:
                    e.library_dirs.append(osp.join(FREETDS, freetds_lib_dir))
                else:
                    e.library_dirs.append(osp.join(FREETDS, freetds_lib_dir))
                if LINK_OPENSSL:
                    e.library_dirs.append(OPENSSL)

        else:
            for e in self.extensions:
                e.libraries.extend(libraries)
        _build_ext.build_extensions(self)


class clean(_clean):
    """
    Subclass clean so it removes all the Cython generated files.
    """

    def run(self):
        _clean.run(self)
        for ext in self.distribution.ext_modules:
            cy_sources = [osp.splitext(s)[0] for s in ext.sources]
            for cy_source in cy_sources:
                # .so/.pyd files are created in place when using 'develop'
                for ext in ('.c', '.so', '.pyd'):
                    generated = cy_source + ext
                    if osp.exists(generated):
                        log.info('removing %s', generated)
                        os.remove(generated)


class release(Command):
    """
    Setuptools command to run all the required commands to perform
    a release. This acts differently depending on the platform it
    is being run on.
    """

    description = "Run all the commands required for a release."

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        if WINDOWS:
            self.release_windows()
        else:
            self.release_unix()

    def release_windows(self):
        # generate windows source distributions
        sdist = self.distribution.get_command_obj('sdist')
        sdist.formats = 'zip'
        sdist.ensure_finalized()
        sdist.run()

        # generate a windows egg
        self.run_command('bdist_egg')

        # generate windows installers
        bdist = self.reinitialize_command('bdist')
        bdist.formats = 'zip,wininst'
        bdist.ensure_finalized()
        bdist.run()

    def release_unix(self):
        # generate linux source distributions
        sdist = self.distribution.get_command_obj('sdist')
        sdist.formats = 'gztar,bztar'
        sdist.ensure_finalized()
        sdist.run()

def ext_modules():
    if have_c_files:
        source_extension = 'c'
    else:
        source_extension = 'pyx'

    ext_modules = [
        Extension('_mssql', [osp.join('src', '_mssql.%s' % source_extension)],
            extra_compile_args = _extra_compile_args,
            include_dirs = include_dirs,
            library_dirs = library_dirs
        ),
        Extension('pymssql', [osp.join('src', 'pymssql.%s' % source_extension)],
            extra_compile_args = _extra_compile_args,
            include_dirs = include_dirs,
            library_dirs = library_dirs
        ),
    ]
    for e in ext_modules:
        e.cython_directives = {'language_level': sys.version_info[0]}
    return ext_modules


class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = None

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        #import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.pytest_args)
        sys.exit(errno)


setup(
    name  = 'pymssql',
    use_scm_version = {
        "write_to": "src/version.h",
        "write_to_template": '#define PYMSSQL_VERSION "{version}"',
        "local_scheme": "no-local-version",
    },
    description = 'DB-API interface to Microsoft SQL Server for Python. (new Cython-based version)',
    long_description = open('README.rst').read() +"\n\n" + open('ChangeLog_highlights.rst').read(),
    author = 'Damien Churchill',
    author_email = 'damoxc@gmail.com',
    maintainer = 'pymssql development team',
    maintainer_email = 'pymssql@googlegroups.com',
    license = 'LGPL',
    platforms = 'any',
    keywords = ['mssql', 'SQL Server', 'database', 'DB-API'],
    url = 'http://pymssql.org',
    cmdclass = {
        'build_ext': build_ext,
        'clean': clean,
        'release': release,
        'test': PyTest,
    },
    classifiers=[
      "Development Status :: 5 - Production/Stable",
      "Intended Audience :: Developers",
      "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
      "Programming Language :: Python",
      "Programming Language :: Python :: 3.6",
      "Programming Language :: Python :: 3.7",
      "Programming Language :: Python :: 3.8",
      "Programming Language :: Python :: 3.9",
      "Programming Language :: Python :: Implementation :: CPython",
      "Topic :: Database",
      "Topic :: Database :: Database Engines/Servers",
      "Topic :: Software Development :: Libraries :: Python Modules",
      "Operating System :: Microsoft :: Windows",
      "Operating System :: POSIX",
      "Operating System :: Unix",
    ],
    zip_safe = False,
    setup_requires=['setuptools_scm', 'Cython'],
    tests_require=['psutil', 'pytest', 'pytest-timeout'],
    ext_modules = ext_modules(),

)
