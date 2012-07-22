# -*- coding: UTF-8 -*-

'''Provide a test environment with a fake /sys, modprobe, etc., and
implementations of OSLib, AbstractUI, DriverDB, and various handlers suitable
for self tests.'''

# (c) 2007 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import tempfile, atexit, shutil, os, os.path, sys, signal, subprocess
import unittest, time, socket, traceback
try:
    from xmlrpc.client import ServerProxy
    from xmlrpc.server import SimpleXMLRPCServer
except ImportError:
    from xmlrpclib import ServerProxy
    from SimpleXMLRPCServer import SimpleXMLRPCServer

from jockey.oslib import OSLib
from jockey.detection import HardwareID, DriverID, DriverDB
from jockey.ui import AbstractUI

fake_modinfo = {
    'vanilla': {
        'filename': '/lib/modules/0.8.15/foo/vanilla.ko',
        'license': 'GPL',
        'description': 'free module with available hardware, graphics card',
        'alias': 'pci:v00001001d*sv*sd*bc03sc*i*'
    },
    'chocolate': {
        'filename': '/lib/modules/0.8.15/bar/chocolate.ko',
        'license': 'BSD',
        'description': 'free module with nonavailable hardware',
        'alias': ['pci:v00001002d00000001sv*bc*sc*i*', 'pci:v00001002d00000002sv*sd*bc*sc*i*'],
    },
    'cherry': {
        'filename': '/lib/modules/0.8.15/extra/cherry.ko',
        'license': 'evil',
        'description': 'nonfree module with nonavailable hardware, wifi',
        'alias': 'pci:v0000EEEEd*sv*sd*bc02sc80i*',
    },
    'mint': {
        'filename': '/lib/modules/0.8.15/extra/mint.ko',
        'license': "Palpatine's Revenge",
        'description': 'nonfree module with available hardware, wifi',
        'alias': 'pci:v0000AAAAd000012*sv*sd*bc02sc*i*',
    },
    'vanilla3d': {
        'filename': '/lib/modules/0.8.15/extra/vanilla3d.ko',
        'license': 'PayMe',
        'description': 'nonfree, replacement graphics driver for vanilla',
        'alias': 'pci:v00001001d00003D*sv*sd*bc03sc*i*'
    },
    'spam': {
        'filename': '/lib/modules/0.8.15/extra/spam.ko',
        'license': 'GPL v2',
        'description': 'free mystical module without modaliases',
    },
    'dullstd': {
        'filename': '/lib/modules/0.8.15/standard/dullstd.ko',
        'license': 'GPL',
        'description': 'standard module which should be ignored for detection',
        'alias': 'pci:v0000DEAFd*sv*sd*bc99sc*i*'
    },
    'firmwifi': {
        'filename': '/lib/modules/0.8.15/standard/firmwifi.ko',
        'license': 'GPL',
        'description': 'standard module which needs firmware',
        'alias': 'fire:1.*',
    },
    'foodmi': {
        'filename': '/lib/modules/0.8.15/dmi/foo.ko',
        'license': 'GPL',
        'description': 'foo DMI driver for [A-1] devices',
        'alias': 'dmi:foo[A-1]*',
    },
}

fake_sys = {
    # graphics card, can use vanilla or vanilla3d, defaulting to free driver
    'pci0000:00/0000:00:11.2': {
        'modalias': 'pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00',
        'driver': '../../../bus/pci/drivers/vanilla',
        'module': 'vanilla',
    },

    # pretend that we have two devices using vanilla, to check for duplication
    # of handlers
    'pci0000:02/0000:00:03.4': {
        'modalias': 'pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00',
        'driver': '../../../bus/pci/drivers/vanilla',
        'module': 'vanilla',
    },

    # something that uses a statically built-in kernel driver
    'pci0000:00/0000:00:22.3': {
        'modalias': 'pci:v00003456d00000001sv00000000sd00000000bc09sc23i00',
        'driver': '../../../bus/pci/drivers/southbridge',
    },

    # wifi which can use mint, but not enabled
    'pci0000:00/0000:01:01.0': {
        'modalias': 'pci:v0000AAAAd000012AAsv00000000sdDEADBEEFbc02sc80i00',
    },

    # another wifi on a funny bus, used for firmware testing
    'fire0/1/2': {
        'modalias': 'fire:1.2'
    },

    # unknown piece of hardware
    'pci0000:01/0000:05:05.0': {
        'modalias': 'pci:v0000FFF0d00000001sv00000000sd00000000bc06sc01i01',
    },

    # uninteresting standard component
    'pci0000:02/0000:01:02.3': {
        'modalias': 'pci:v0000DEAFd00009999sv00000000sd00000000bc99sc00i00',
        'driver': '../../../bus/pci/drivers/dullstd',
        'module': 'dullstd',
    },

    # card on SSB bus which has an uevent, but not a modalias file (like the
    # b43 module)
    'pci0001:00/0001:00:00.1/ssb0:0': {
        'uevent': 'DRIVER=b43\nMODALIAS=ssb:v4243id0812rev05',
    },

    # device with shell glob-like characters in modalias
    'dmi0/1': {
        'modalias': 'dmi:foo[A-1]bar',
    }

}

fake_db = {
    # vanilla3d option for the graphics card
    HardwareID('modalias', 'pci:v00001001d00003D*sv*sd*bc03sc*i*'): {
        ('', ''): {
            ('Foonux', '42'): [DriverID(jockey_handler='VanillaGfxHandler'),
                DriverID(foobar='IHaveNoHandler')],
            ('Foonux', '41'): [DriverID(jockey_handler='IShallNotExist')],
            ('RedSock', '2.0'): [DriverID(jockey_handler='Vanilla3DHandler',
                repository='http://nonfree.redsock.com/addons')]
        }
    },

    # driver for the unknown piece of hardware; test multiple handlers here, as
    # well as multiple system IDs
    HardwareID('modalias', 'pci:v0000FFF0d0000*sv*sd*bc06sc01i*'): {
        ('', ''): {
            ('Foonux', '42'): [
                DriverID(jockey_handler='KernelModuleHandler', kernel_module='spam'),
                DriverID(jockey_handler='KernelModuleHandler', kernel_module='mint'),
                # entries without a driver type are invalid and should be
                # ignored; since our fake XMLRPC server always adds it by
                # default, we tell it not to
                DriverID(no_driver_type_tag='1', driver_vendor='Foo'),
                # unknown driver types should be ignored
                DriverID(driver_type='unknown_type', kernel_module='chocolate', driver_vendor='Bar'),
                # uninstantiable drivers should be ignored
                DriverID(jockey_handler='KernelModuleHandler',
                    kernel_module='chocolate', unknown_property='moo'),
            ],
        },
        ('VaporTech Inc.', 'Virtualtop X-1'): {
            ('Foonux', '42'): [
                DriverID(jockey_handler='KernelModuleHandler', kernel_module='chocolate',
                    repository='http://vaportech.com/x1',
                    fingerprint='0000 FFFF 1111 EEEE 2222  DDDD 3333 CCCC 4444 BBBB',
                    package='spam-x1', driver_vendor='VaporTech',
                    description={'C': 'VaporTech choc handler', 'de_DE':
                        'German description', 'cs': 'Czech description'},
                    long_description={'C': 'Multi\nline'},
                    version='1.1-foo42-vt3'),
                # test correct cloning of custom and standard handlers
                DriverID(jockey_handler='NoDetectMod', description={'C': 'WhiteHat ndmod'}, driver_vendor='White Hat'),
                DriverID(jockey_handler='NoDetectMod', description={'C': 'BlackHat ndmod'}, driver_vendor='Black Hat'),
                DriverID(jockey_handler='KernelModuleHandler', kernel_module='mint',
                    description={'C': 'UbuOne mintmod'}, driver_vendor='UbuOne'),
                DriverID(jockey_handler='KernelModuleHandler', kernel_module='mint',
                    description={'C': 'UbunTwo mintmod'},
                    driver_vendor='UbunTwo', recommended=True),
                # unknown kmod, need to specify license and description
                # ourselves
                DriverID(jockey_handler='KernelModuleHandler', kernel_module='apple',
                    description={'C': 'Unknown local kmod'}, package='pretzel',
                    driver_vendor='Apple', free=False, license='Kills kittens'),
            ],

        },
        ('VaporTech Inc.', 'Virtualtop Z-3'): {
            ('Foonux', '42'): [
                DriverID(jockey_handler='KernelModuleHandler', kernel_module='spam',
                    repository='http://vaportech.com/z3',
                    package='spam-z3', driver_vendor='VaporTech')
            ],
        },
    },

    # driver for the second wifi, test firmware handler
    HardwareID('modalias', 'fire:1.2'): {
        ('', ''): {
            ('Foonux', '42'): [
                DriverID(jockey_handler='FirmwareHandler', kernel_module='firmwifi',
                    testfile='/lib/firmware/firmwifi.bin',
                    url='http://foo.bar', recommended=True),
            ],
        },
    },

    # unknown driver
    HardwareID('pci', '9876/FEDC'): {
        ('', ''): {
            ('Foonux', '42'): [DriverID(jockey_handler='KernelModuleHandler',
                kernel_module='spam')],
            ('Oobuntu', 'Eccentric Emu'): [DriverID(jockey_handler='BogusHandler')],
        },
    }
}

fake_pkginfo = {
    'default': {
        'mesa-vanilla': {
            'description': ('X.org libraries for the Vanilla 3D driver', 
                'This package provides optimized Mesa libraries for the Vanilla '
                'graphics cards.'),
            'free': False,
            'files': ['/bin/mesa-vanilla-test', '/lib/X11/vesa.drv'],
        },
        'mesa-vanilla-updates': {
            'description': ('X.org libraries for the Vanilla 3D driver (updates)', 
                'This package provides optimized Mesa libraries for the Vanilla '
                'graphics cards.'),
            'free': False,
            'files': ['/bin/mesa-vanilla-test', '/lib/X11/vesa.drv'],
        },
        'mesa-std': {
            'description': ('standard system mesa libraries',
                'default mesa libs for free drivers'),
            'free': True,
        },
        'coreutils': {
            'description': ('unrelated system package',
                'This package should always be installed.'),
            'free': True,
        },
        'pretzel': {
            'description': ('yet another test packge',
                'This is yummy, but uninteresting.'),
            'free': False,
        },
        'linux-dev': {
            'description': ('fake kernel headers',
                'includes for building kernel modules'),
            'free': True,
        },
    },
    'http://vaportech.com/x1': {
        'spam-x1': {
            'description': ('SpamX1 driver', 'spamx1'),
            'free': True,
        },
        'foo-y1': {
            'description': ('FooY1 driver', 'fooy1'),
            'free': True,
        },
    },
}

#-------------------------------------------------------------------#

class LogTestCase(unittest.TestCase):
    '''TestCase which logs method names to sandbox.log.'''

    def run(self, result=None):
        log.write('--- Running test %s\n' % self.id())
        unittest.TestCase.run(self, result)

#-------------------------------------------------------------------#

class TestOSLib(OSLib):
    '''Test suite implementation of OSLib.
    
    This builds a realistic mini-chroot and fake module/package system.
    '''
    def __init__(self):
        # set up a fake environment
        self.workdir = tempfile.mkdtemp()
        atexit.register(shutil.rmtree, self.workdir)

        OSLib.__init__(self)

        self._make_modinfo()
        self._make_proc_modules()
        self._make_modprobe()
        self._make_modalias()
        self._make_sys()
        self._make_xorg_conf()

        self.reset_packages()
        self.reset_dmi()

        os.mkdir(os.path.join(self.workdir, 'modules.d'))
        self.module_blacklist_file = os.path.join(self.workdir, 'modules.d', 'module-blacklist')

        self.handler_dir = os.path.join(self.workdir, 'handlers')
        os.mkdir(self.handler_dir)
        self.check_cache = os.path.join(self.workdir, 'check_cache')

        self.help_available = False
        self.help_called = False

        self.kernel_header_package = 'linux-dev'

    def reset_packages(self):
        '''Reset repositories and packages.'''

        self.installed_packages = set(['mesa-std', 'coreutils'])
        self.next_package_install_fails = False
        self.repositories = set(['default'])
        # set this to a string to raise it on next install/remove_package()
        self.pending_install_remove_exception = None

    def reset_dmi(self):
        '''Reset system vendor/product to default.'''

        self.set_dmi('VaporTech Inc.', 'Virtualtop X-1')

    def set_dmi(self, vendor, product):
        '''Set system vendor/product strings.'''

        dmipath = os.path.join(self.sys_dir, 'class', 'dmi', 'id')
        if os.path.isdir(dmipath):
            shutil.rmtree(dmipath)
        os.makedirs(dmipath)
        if vendor is not None:
            f = open(os.path.join(dmipath, 'sys_vendor'), 'w')
            f.write(vendor + '\n')
            f.close()
        if product is not None:
            f = open(os.path.join(dmipath, 'product_name'), 'w')
            f.write(product + '\n')
            f.close()

    def _make_modinfo(self):
        '''Create a dummy modinfo program which outputs the fake_modinfo data
        and set self.modinfo_path.
        
        Note that this fake modinfo only supports one module argument, not
        several (as the original modinfo), and no options.'''

        os.mkdir(os.path.join(self.workdir, 'bin'))
        self.modinfo_path = os.path.join(self.workdir, 'bin', 'modinfo')
        mi = open(self.modinfo_path, 'w')
        mi.write('''#!/usr/bin/python
import sys

data = %s

if len(sys.argv) != 2:
    print >> sys.stderr, 'Usage: modinfo module'
    sys.exit(0)

m = sys.argv[1]
if m in data:
    attrs = data[m].keys()
    attrs.sort()
    for k in attrs:
        if hasattr(data[m][k], 'isspace'):
            print '%%-16s%%s' %% (k + ':', data[m][k])
        else:
            for i in data[m][k]:
                print '%%-16s%%s' %% (k + ':', i)
else:
    print >> sys.stderr, 'modinfo: could not find module', m
    sys.exit(1)

''' % repr(fake_modinfo))
        mi.close()
        os.chmod(self.modinfo_path, 0o755)

    def _make_modprobe(self):
        '''Create a dummy modprobe and set self.modprobe_path.'''

        self.modprobe_path = os.path.join(self.workdir, 'bin', 'modprobe')
        mp = open(self.modprobe_path, 'w')
        mp.write('''#!/usr/bin/python
import sys

modinfo = %s
proc_modules = %s

if len(sys.argv) != 2:
    print >> sys.stderr, 'Usage: modprobe module'
    sys.exit(1)

m = sys.argv[1]
if m in modinfo:
    if m not in open(proc_modules).read():
        print >> open(proc_modules, 'a'), '%%s 11111 2 - Live 0xbeefbeef' %% m
else:
    print >> sys.stderr, 'FATAL: Module %%s not found.' %% m
    sys.exit(1)
''' % (repr(fake_modinfo), repr(self.proc_modules)))

        mp.close()
        os.chmod(self.modprobe_path, 0o755)
        
    def _make_sys(self):
        '''Create a dummy /sys tree from fake_sys and set self.sys_dir.'''

        self.sys_dir = os.path.join(self.workdir, 'sys')

        for pcipath, info in fake_sys.iteritems():
            # create /sys/device entry
            device_dir = os.path.join(self.sys_dir, 'devices', pcipath)
            os.makedirs(device_dir)
            if 'modalias' in info:
                open(os.path.join(device_dir, 'modalias'), 'w').write(info['modalias'])
            if 'uevent' in info:
                open(os.path.join(device_dir, 'uevent'), 'w').write(info['uevent'])

            # create driver dir and symlink to device, if existing
            if 'driver' not in info:
                continue
            driver_dir = os.path.join(device_dir, info['driver'])
            try:
                os.makedirs(driver_dir)
            except OSError:
                pass
            os.symlink(info['driver'], os.path.join(device_dir, 'driver'))
            os.symlink(device_dir, os.path.join(driver_dir,
                os.path.basename(pcipath)))

            # create module dir and symlink to driver, if existing
            if 'module' not in info:
                continue
            module_dir = os.path.join(self.workdir, 'sys', 'module', info['module'])
            try:
                os.makedirs(os.path.join(module_dir, 'drivers'))
            except OSError:
                pass
            if not os.path.islink(os.path.join(driver_dir, 'module')):
                os.symlink(module_dir, os.path.join(driver_dir, 'module'))
            driver_comp = info['driver'].split('/')
            mod_driver_link = os.path.join(module_dir, 'drivers',
                '%s:%s' % (driver_comp[-3], driver_comp[-1]))
            if not os.path.islink(mod_driver_link):
                os.symlink(driver_dir, mod_driver_link)

    def _make_proc_modules(self):
        '''Create a dummy /proc/modules and set self.proc_modules.'''

        self.proc_modules = os.path.join(self.workdir, 'proc', 'modules')
        if not os.path.isdir(os.path.dirname(self.proc_modules)):
            os.mkdir(os.path.dirname(self.proc_modules))
        mods = set()
        for info in fake_sys.itervalues():
            try:
                mods.add(info['module'])
            except KeyError:
                pass

        f = open(self.proc_modules, 'w')
        for m in mods:
            f.write('%s 12345 0 - Live 0xdeadbeef\n' % m)
        f.close()

    def _make_modalias(self):
        '''Create a dummy modules.alias and set self.modaliases
        appropriately.'''

        # prepare one fake kernel modules.alias and an override directory
        self.modaliases = [
            os.path.join(self.workdir, 'kernelmods', 'modules.alias'),
            os.path.join(self.workdir, 'modalias-overrides'),
            '/nonexisting', # should not stumble over those
        ]
        os.mkdir(os.path.dirname(self.modaliases[0]))
        os.mkdir(self.modaliases[1])

        f = open(self.modaliases[0], 'w')
        f.write('# Aliases extracted from modules themselves.\n')
        for mod in sorted(fake_modinfo.keys()):
            aliases = fake_modinfo[mod].get('alias', [])
            if hasattr(aliases, 'isspace'):
                f.write('alias %s %s\n' % (aliases, mod))
            else:
                for a in aliases:
                    f.write('alias %s %s\n' % (a, mod))
        f.close()

    def _make_xorg_conf(self):
        '''Create a dummy xorg.conf and set self.xorg_conf_path appropriately.'''

        self.xorg_conf_path = os.path.join(self.workdir, 'xorg.conf')
        f = open(self.xorg_conf_path, 'w')
        f.write('''# xorg.conf (xorg X Window System server configuration file)

Section "InputDevice"
	Identifier	"Generic Keyboard"
	Driver		"kbd"
	Option		"CoreKeyboard"
	Option		"XkbRules"	"xorg"
	Option		"XkbModel"	"pc105"
	Option		"XkbLayout"	"us"
EndSection

Section "Device"
	Identifier	"Standard ice cream graphics"
	Driver		"vanilla"
EndSection

Section "Monitor"
	Identifier	"My Monitor"
	Option		"DPMS"
	HorizSync	30-70
	VertRefresh	50-160
EndSection

Section "Screen"
	Identifier	"Default Screen"
	Device		"Standard ice cream graphics"
	Monitor		"My Monitor"
	DefaultDepth	24
EndSection

Section "ServerLayout"
	Identifier	"Default Layout"
	Screen		"Default Screen"
	InputDevice	"Generic Keyboard"
EndSection
''')
        f.close()

    def _get_os_version(self):
        self.os_vendor = 'Foonux'
        self.os_version = '42'

    def set_backup_dir(self):
        self.backup_dir = os.path.join(self.workdir, 'backup')
        os.mkdir(self.backup_dir)

    def ignored_modules(self):
        return set(['dullstd'])

    def package_description(self, package):
        '''Return a tupe (short_description, long_description) for given
        package.
        
        This should raise a ValueError if the package is not available.'''

        for repo in self.repositories:
            try:
                return fake_pkginfo[repo][package]['description']
            except KeyError:
                continue
        raise ValueError('no such package')

    def is_package_free(self, package):
        '''Return if given package is free software.'''

        for repo in self.repositories:
            try:
                return fake_pkginfo[repo][package]['free']
            except KeyError:
                continue
        raise ValueError('no such package')

    def package_installed(self, package):
        '''Return if the given package is installed.'''

        return package in self.installed_packages

    def package_files(self, package):
        '''Return a list of files shipped by a package.
        
        This should raise a ValueError if the package is not installed.
        '''
        if self.package_installed(package):
            for repo in self.repositories:
                try:
                    return fake_pkginfo[repo][package]['files']
                except KeyError:
                    continue
        raise ValueError('package not installed')

    def install_package(self, package, progress_cb, repository=None,
            fingerprint=None):
        '''Install the given package.

        As this is called in the backend, this must happen noninteractively.
        For progress reporting, progress_cb(phase, current, total) is called
        regularly, with 'phase' being 'download' or 'install'. If the callback
        returns True, the installation is attempted to get cancelled (this
        will probably succeed in the 'download' phase, but not in 'install').
        Passes '-1' for current and/or total if time cannot be determined.

        If this succeeds, subsequent package_installed(package) calls must
        return True.

        If a repository URL is given, that repository is added to the system
        first. The format for repository is distribution specific. This function
        should also download/update the package index for this repository when
        adding it.
        .
        fingerprint, if not None, is a GPG-style fingerprint of that
        repository; if present, this method should also retrieve that GPG key
        from the keyservers, install it into the packaging system, and ensure
        that the repository is signed with that key.

        An unknown package should raise a ValueError. Any installation failure
        due to bad packages should be logged, but not raise an exception, as
        this would just crash the backend.
        '''
        if repository:
            if repository not in fake_pkginfo:
                raise SystemError('repository %s does not exist' % repository)
            if fingerprint and not fingerprint.startswith('0000 FFFF'):
                raise SystemError('invalid repository fingerprint')
            self.repositories.add(repository)

        for repo in self.repositories:
            if package in fake_pkginfo[repo]:
                break
        else:
            raise ValueError('no such package')

        if self.pending_install_remove_exception:
            e = self.pending_install_remove_exception
            self.pending_install_remove_exception = None
            raise SystemError(e)

        if self.next_package_install_fails:
            self.next_package_install_fails = False
        else:
            self.installed_packages.add(package)

        # bogus progress
        if progress_cb:
            progress_cb('download', 1, 2)
            time.sleep(0.2)
            progress_cb('download', 2, 2)
            time.sleep(0.2)
            progress_cb('install', 1, 3)
            time.sleep(0.2)
            progress_cb('install', 3, 3)

    def remove_package(self, package, progress_cb):
        '''Uninstall the given package.

        As this is called in the backend, this must happen noninteractively.
        For progress reporting, progress_cb(current, total) is called
        regularly. Passes '-1' for current and/or total if time cannot be
        determined.

        If this succeeds, subsequent package_installed(package) calls must
        return False.

        Any removal failure should be raised as a SystemError.
        '''
        if self.pending_install_remove_exception:
            e = self.pending_install_remove_exception
            self.pending_install_remove_exception = None
            raise SystemError(e)

        self.installed_packages.remove(package)

        # bogus progress
        if progress_cb:
            progress_cb(1, 2)
            time.sleep(0.2)
            progress_cb(2, 2)

    def repository_enabled(self, repository):
        '''Check if given repository is enabled.'''

        return repository in self.repositories

    def ui_help_available(self, ui):
        '''Return if help is available.

        This gets the current UI object passed, which can be used to determine
        whether GTK/KDE is used, etc.
        '''
        return self.help_available

    def ui_help(self, ui):
        '''The UI's help button was clicked.

        This should open a help HTML page or website, call yelp with an
        appropriate topic, etc. This gets the current UI object passed, which
        can be used to determine whether GTK/KDE is used, etc.
        '''
        self.help_called = True

    def current_xorg_video_abi(self):
        '''Return current X.org video ABI.
        
        This returns a static string for the test suite. Tests are done by
        dynamically implementing video_driver_abi().
        '''
        return 'X.org-video-1test'

#-------------------------------------------------------------------#

class AllAvailOSLib(OSLib):
    '''Test suite implementation of OSLib.

    This pretends that any module and package is always available and gives
    predictable and constant descriptions and states. It is mainly useful for
    testing arbitrary and unknown handlers.
    '''

    def __init__(self):
        self.workdir = tempfile.mkdtemp()

        OSLib.__init__(self)
        self.installed_packages = set()
        self.blacklisted_modules = set()

        atexit.register(shutil.rmtree, self.workdir)

        self._make_modinfo()
        self.xorg_conf_path = os.path.join(self.workdir, 'xorg.conf')
        self.module_blacklist_file = os.path.join(self.workdir, 
            'module-blacklist')

    def set_backup_dir(self):
        self.backup_dir = os.path.join(self.workdir, 'backup')
        os.mkdir(self.backup_dir)

    def package_description(self, package):
        '''Return a tuple (short_description, long_description) for a package.
        
        This should raise a ValueError if the package is not available.
        '''
        return (package + ' description', package + 'long description')

    def is_package_free(self, package):
        '''Return if given package is free software.'''

        return True

    def package_installed(self, package):
        '''Return if the given package is installed.'''

        return package in self.installed_packages

    def install_package(self, package, progress_cb, repository=None,
            fingerprint=None):
        '''Install the given package.'''

        self.installed_packages.add(package)

    def remove_package(self, package, progress_cb):
        '''Uninstall the given package.'''

        self.installed_packages.remove(package)

    def module_blacklisted(self, module):
        '''Check if a module is on the modprobe blacklist.'''

        return module in self.blacklisted_modules

    def blacklist_module(self, module, blacklist):
        '''Add or remove a kernel module from the modprobe blacklist.
        
        If blacklist is True, the module is blacklisted, otherwise it is
        removed from the blacklist.
        '''

        if blacklist:
            self.blacklisted_modules.add(module)
        else:
            try:
                self.blacklisted_modules.remove(module)
            except KeyError:
                pass

    def _make_modinfo(self):
        '''Create a dummy modinfo program which outputs dummy data
        and set self.modinfo_path.
        
        Note that this fake modinfo only supports one module argument, not
        several (as the original modinfo), and no options.'''

        os.mkdir(os.path.join(self.workdir, 'bin'))
        self.modinfo_path = os.path.join(self.workdir, 'bin', 'modinfo')
        mi = open(self.modinfo_path, 'w')
        mi.write('''#!/usr/bin/python
import sys

data = %s

if len(sys.argv) != 2:
    print >> sys.stderr, 'Usage: modinfo module'
    sys.exit(0)

m = sys.argv[1]
print '%%-16s%%s' %% ('filename:', '/lib/modules/%%s.ko' %% m)
print '%%-16s%%s' %% ('license:', 'GPL')
print '%%-16s%%s' %% ('description:', '%%s module' %% m)
''' % repr(fake_modinfo))
        mi.close()
        os.chmod(self.modinfo_path, 0o755)

#-------------------------------------------------------------------#

class TestDriverDB(DriverDB):
    '''Test suite implementation of DriverDB.
    
    This uses fake_db, but only the default system ID.'''

    # TODO: drop self.updated, use XMLRPCDB for that test
    def __init__(self):
        DriverDB.__init__(self)
        self.updated = False

    def _do_query(self, hwid):
        if not self.updated:
            return []

        return fake_db.get(hwid, {}).get(('', ''), {}).get(
            (OSLib.inst.os_vendor, OSLib.inst.os_version), [])

    def _do_update(self, hwids):
        '''Pretend that fake_db is acquired from a remote server.'''

        self.updated = True

#-------------------------------------------------------------------#

class TestUI(AbstractUI):
    def __init__(self):
        AbstractUI.__init__(self)
        self.error_stack = []
        self.confirm_response = None
        self.notification_stack = []
        self.main_loop_active = False
        self.cur_progress = [None, None, None] # (desc, size, total)
        self.cancel_progress = False # whether to cancel the next progress dialog at 30%

    def backend(self):
        if self._dbus_iface is None:
            import jockey.backend as b
            # use a local backend here for simplicity; D-BUS operation is
            # already exercised elsewhere in the test suite
            self._dbus_iface = b.Backend()
        return self._dbus_iface

    def convert_keybindings(self, str):
        return str

    def ui_init(self):
        pass

    def ui_show_main(self):
        pass

    def ui_main_loop(self):
        '''Main loop for the user interface.
        
        This should return if the user wants to quit the program, and return
        the exit code.'''

        self.main_loop_active = True
        return 0

    def ui_idle(self):
        pass

    def error_message(self, title, text):
        '''Show an error message box with given title and text.'''

        self.error_stack.append((title, text))

    def pop_error(self):
        '''Return the last error message (title, text) tuple.'''

        return self.error_stack.pop()

    def confirm_action(self, title, text, subtext = None, action=None):
        assert self.confirm_response is not None, 'must set confirm_response'

        self.last_confirm_title = title
        self.last_confirm_text = text
        self.last_confirm_subtext = subtext
        self.last_confirm_action = action

        r = self.confirm_response
        self.confirm_response = None

        return r

    def ui_notification(self, title, text):
        self.notification_stack.append((title, text))

    def pop_notification(self):
        '''Return the last notification (title, text) tuple.'''

        return self.notification_stack.pop()

    def ui_progress_start(self, title, description, total):
        '''Create a progress dialog.'''

        assert description
        self.cur_progress = [description, 0, total]

    def ui_progress_update(self, current, total):
        '''Update status of current progress dialog.
        
        current/total specify the number of steps done and total steps to
        do, or -1 if it cannot be determined. In this case the dialog should
        display an indeterminated progress bar (bouncing back and forth).

        This should return True to cancel, and False otherwise.
        '''
        assert self.cur_progress[0]
        assert self.cur_progress[1] is not None
        assert self.cur_progress[2] is not None
        assert (current > self.cur_progress[1]) or current == -1
        assert total == self.cur_progress[2]

        self.cur_progress[1] = current

        return self.cancel_progress and float(current)/total >= 0.3

    def ui_progress_finish(self):
        '''Close the current progress dialog.'''

        self.cancel_progress = False

#-------------------------------------------------------------------#

def xmlrpc_driverdb_query(proto_ver, proto_subver, request):
    '''XML-RPC server query() implementation.

    This conforms to protocol version 20080407/0, which is the only defined
    protocol version at the moment.

    Example:
    query('20080407', '0', {
          'components': ['modalias:pci:crap', 'printer:Canon_BJ2'],
          'system_vendor': 'Dell',
          'system_product': 'Latitude D430',
          'os_name': 'RedSock',
          'os_version': '2.0',
          'kernel_ver': '2.6.24-15-generic',
          'architecture': 'i686'}) =
      ('20080407', '0', {'modalias:pci:crap': [dr_crap1, dr_crap2], 'printer:Canon_BJ2': [dr_pr1]})
    '''
    if proto_ver != '20080407':
        return ('20080407', '0', {})

    result = {}
    for comp_id in request.get('components', []):
        (type, val) = comp_id.split(':', 1)
        try:
            hw_entry = fake_db.get(HardwareID(type, val), {})
            system_entry = hw_entry.get((request['system_vendor'],
                request['system_product']), hw_entry.get(('', ''), {}))
            drivers = system_entry.get((request['os_name'], request['os_version']), [])
        except KeyError:
            break # invalid request

        result[comp_id] = []

        for did in drivers:
            props = did.properties.copy()
            if 'driver_type' not in props and 'no_driver_type_tag' not in props:
                props['driver_type'] = 'kernel_module'
            if props.get('jockey_handler') == 'KernelModuleHandler':
                del props['jockey_handler']
            if 'description' not in props:
                if 'kernel_module' in props:
                    props['description'] = {'C': fake_modinfo[props['kernel_module']]['description']}
                else:
                    props['description'] = {'C': 'desc'}

            result[comp_id].append(props)

    return ('20080407', '0', result)

def xmlrpc_driverdb_query_bogus(proto_ver, proto_subver, request):
    '''XML-RPC server query() implementation with bogus protocol.'''

    return ('20070301', '2', {'modalias:pci:crap': ['bogus']})

def start_driverdb_server(correct_protocol=True):
    '''Create XML-RPC driver db server.

    This will listen on localhost:8080 and serve fake_db. This must be
    terminated with stop_driverdb_server().

    If correct_protocol is False, this will answer with a bogus protocol
    version.
    '''

    start_driverdb_server.pid = os.fork()
    if start_driverdb_server.pid == 0:
        try:
            s = SimpleXMLRPCServer(('localhost', 8080), logRequests=False)
            s.register_introspection_functions()
            if correct_protocol:
                s.register_function(xmlrpc_driverdb_query, 'query')
            else:
                s.register_function(xmlrpc_driverdb_query_bogus, 'query')
            s.serve_forever()
        except:
            sys.stderr.write('********** DEMO XML-RPC server failed: ***********\n')
            traceback.print_exc()
            os._exit(1)

    # wait until it is ready
    c = ServerProxy('http://localhost:8080')
    timeout = 100
    while timeout > 0:
        time.sleep(0.1)
        try:
            c.query('0', '0', {})
        except socket.error:
            timeout -= 1
            continue
        break
    if timeout == 0:
        raise SystemError('XML-RPC demo server did not start')

def stop_driverdb_server():
    '''Stop the XML-RPC driver db server.'''

    os.kill(start_driverdb_server.pid, signal.SIGTERM)
    os.wait()


#-------------------------------------------------------------------#
# TestOSLib consistency tests

class TestOSLibConsistencyTest(LogTestCase):
    def test_modinfo_output(self):
        '''test suite's modinfo output for known modules'''
        
        m = subprocess.Popen([OSLib.inst.modinfo_path, 'vanilla'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = m.communicate()
        self.assertEqual(err, '')
        self.assertEqual(out, '''alias:          pci:v00001001d*sv*sd*bc03sc*i*
description:    free module with available hardware, graphics card
filename:       /lib/modules/0.8.15/foo/vanilla.ko
license:        GPL
''')
        self.assertEqual(m.returncode, 0)

        m = subprocess.Popen([OSLib.inst.modinfo_path, 'chocolate'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = m.communicate()
        self.assertEqual(err, '')
        self.assertEqual(m.returncode, 0)
        self.assert_('chocolate.ko' in out)
        # both modaliases
        self.assert_('alias:          pci:v00001002d00000001sv*' in out)
        self.assert_('alias:          pci:v00001002d00000002sv*' in out)

    def test_modinfo_error(self):
        '''test suite's modinfo output for unknown modules and invalid invocation'''
        
        m = subprocess.Popen([OSLib.inst.modinfo_path, 'nonexisting'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = m.communicate()
        self.assertEqual(out, '')
        self.assert_('could not find module nonexisting' in err)
        self.assertEqual(m.returncode, 1)

        m = subprocess.Popen([OSLib.inst.modinfo_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = m.communicate()
        self.assertEqual(out, '')
        self.assert_('Usage' in err)
        self.assertEqual(m.returncode, 0)

    def test_modprobe(self):
        '''test suite's modprobe works'''

        # help output
        m = subprocess.Popen([OSLib.inst.modprobe_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = m.communicate()
        self.assertEqual(out, '')
        self.assert_('Usage' in err)
        self.assertEqual(m.returncode, 1)

        # invalid module
        m = subprocess.Popen([OSLib.inst.modprobe_path, 'nonexisting'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = m.communicate()
        self.assertEqual(out, '')
        self.assert_('FATAL' in err)
        self.assert_('nonexisting' in err)
        self.assertEqual(m.returncode, 1)

        # valid module
        orig_content = open(OSLib.inst.proc_modules).read()
        try:
            self.failIf('cherry' in orig_content)
            m = subprocess.Popen([OSLib.inst.modprobe_path, 'cherry'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = m.communicate()
            self.assertEqual(out, '')
            self.assertEqual(err, '')
            self.assertEqual(m.returncode, 0)
            self.assert_('cherry' in open(OSLib.inst.proc_modules).read())
        finally:
            open(OSLib.inst.proc_modules, 'w').write(orig_content)


    def test_sys_symlinks(self):
        '''all symlinks in fake /sys are valid'''

        for path, dirs, files in os.walk(os.path.join(OSLib.inst.workdir, 'sys')):
            for f in files+dirs:
                p = os.path.join(path, f)
                if os.path.islink(p):
                    rp = os.path.realpath(p)
                    self.assert_(os.path.exists(rp), 
                        'symbolic link %s -> %s is valid' % (p, rp))

    def test_module_aliases_file(self):
        '''module.aliases correctness'''

        self.assertEqual(open(os.path.join(OSLib.inst.workdir, 'kernelmods',
            'modules.alias')).read(), 
            '''# Aliases extracted from modules themselves.
alias pci:v0000EEEEd*sv*sd*bc02sc80i* cherry
alias pci:v00001002d00000001sv*bc*sc*i* chocolate
alias pci:v00001002d00000002sv*sd*bc*sc*i* chocolate
alias pci:v0000DEAFd*sv*sd*bc99sc*i* dullstd
alias fire:1.* firmwifi
alias dmi:foo[A-1]* foodmi
alias pci:v0000AAAAd000012*sv*sd*bc02sc*i* mint
alias pci:v00001001d*sv*sd*bc03sc*i* vanilla
alias pci:v00001001d00003D*sv*sd*bc03sc*i* vanilla3d
''')

    def test_proc_modules(self):
        '''/proc/modules correctness'''

        m = open(OSLib.inst.proc_modules).read()
        self.assertEqual(len(m.splitlines()), 2)
        self.assert_('dullstd' in m)
        self.assert_('vanilla' in m)
        self.failIf('vanilla3d' in m)
        self.failIf('cherry' in m)
        self.failIf('mint' in m)

    def test_packages(self):
        '''sandbox package/repository handling'''

        self.assertRaises(ValueError, OSLib.inst.package_description, 'nonexisting')
        self.assertEqual(OSLib.inst.package_installed('nonexisting'), False)

        self.assertEqual(OSLib.inst.package_description('mesa-vanilla'),
            fake_pkginfo['default']['mesa-vanilla']['description'])
        self.assertEqual(OSLib.inst.is_package_free('mesa-vanilla'), False)

        self.assertRaises(ValueError, OSLib.inst.package_description, 'foo-y1')
        self.assertEqual(OSLib.inst.package_installed('foo-y1'), False)
        self.assertEqual(OSLib.inst.repository_enabled('http://vaportech.com/x1'), False)

        # wrong fingerprint
        self.assertRaises(SystemError, OSLib.inst.install_package, 'foo-y1', None,
                'http://vaportech.com/x1', '0xDEADBEEF')
        self.assertEqual(OSLib.inst.repository_enabled('http://vaportech.com/x1'), False)

        OSLib.inst.install_package('foo-y1', None, 'http://vaportech.com/x1', None)
        self.assertEqual(OSLib.inst.repository_enabled('http://vaportech.com/x1'), True)

        self.assertEqual(OSLib.inst.package_description('foo-y1'),
            fake_pkginfo['http://vaportech.com/x1']['foo-y1']['description'])
        self.assertEqual(OSLib.inst.package_installed('foo-y1'), True)
        self.assertEqual(OSLib.inst.is_package_free('foo-y1'), True)

        # test exception raising
        OSLib.inst.pending_install_remove_exception = 'moo!'
        self.assertRaises(SystemError, OSLib.inst.install_package, 'foo-y1', None)
        OSLib.inst.install_package('foo-y1', None)
        OSLib.inst.pending_install_remove_exception = 'moo!'
        self.assertRaises(SystemError, OSLib.inst.remove_package, 'foo-y1', None)
        self.assertEqual(OSLib.inst.package_installed('foo-y1'), True)

        self.assertEqual(OSLib.inst.package_installed('foo-y1'), True)

        OSLib.inst.remove_package('foo-y1', None)
        self.assertEqual(OSLib.inst.package_installed('foo-y1'), False)

        self.assertEqual(OSLib.inst.package_installed('foo-y1'), False)
        self.assertEqual(OSLib.inst.package_description('mesa-vanilla'),
            fake_pkginfo['default']['mesa-vanilla']['description'])

        OSLib.inst.reset_packages()

#-------------------------------------------------------------------#
# Test XML-RPC consistency test

class TestXMLRPCDriverDBConsistency(unittest.TestCase):
    def setUp(self):
        start_driverdb_server()
        self.xmlrpc_client = ServerProxy('http://localhost:8080')

    def tearDown(self):
        stop_driverdb_server()

    def test_consistency(self):
        '''XML-RPC driver DB server answers are consistent with fake_db'''

        # TODO: kernel_ver, and architecture specific tests
        self.assertEqual(self.xmlrpc_client.query('20080407', '0', {
            'os_name': 'Foonux', 'os_version': '42', 'system_vendor': '',
            'system_product': '', 'components': [
                'modalias:pci:v00001001d00003D11sv01sd02bc03sc00i00',
                'modalias:dmi:123456']}),
            ['20080407', '0', {
                'modalias:pci:v00001001d00003D11sv01sd02bc03sc00i00': [
                    {'driver_type': 'kernel_module', 'jockey_handler':
                     'VanillaGfxHandler', 'description': {'C': 'desc'}}, 
                    {'driver_type': 'kernel_module', 'foobar':
                    'IHaveNoHandler', 'description': {'C': 'desc'}}],
                'modalias:dmi:123456': []}
            ]
        )

        self.assertEqual(self.xmlrpc_client.query('20080407', '0', {
            'os_name': 'RedSock', 'os_version': '2.0', 'system_vendor': '',
            'system_product': '', 'components': [
                'modalias:pci:v00001001d00003D11sv01sd02bc03sc00i00']}),
            ['20080407', '0', {
                'modalias:pci:v00001001d00003D11sv01sd02bc03sc00i00': [
                    {'driver_type': 'kernel_module', 'jockey_handler':
                     'Vanilla3DHandler', 'description': {'C': 'desc'},
                     'repository': 'http://nonfree.redsock.com/addons'}]
            }]
        )

        self.assertEqual(self.xmlrpc_client.query('20080407', '0', {
            'os_name': 'Foonux', 'os_version': '40', 'system_vendor': '',
            'system_product': '', 'components': [
                'modalias:pci:v00001001d00003D11sv01sd02bc03sc00i00',
                'modalias:othertype:foobar12']}),
            ['20080407', '0', {
                'modalias:pci:v00001001d00003D11sv01sd02bc03sc00i00': [],
                'modalias:othertype:foobar12': []}
            ]
        )

        self.assertEqual(self.xmlrpc_client.query('20080407', '0', {
            'os_name': 'Foonux', 'os_version': '42', 'system_vendor':
            'VaporTech Inc.', 'system_product': 'Virtualtop X-1', 
            'components': ['modalias:pci:v0000FFF0d00000001sv01sd01bc06sc01i00']}),
            ['20080407', '0', {
                'modalias:pci:v0000FFF0d00000001sv01sd01bc06sc01i00': [
                    {'driver_type': 'kernel_module', 'kernel_module':
                     'chocolate', 'description': {'C': 'VaporTech choc handler', 'de_DE':
                         'German description', 'cs': 'Czech description'},
                     'long_description': {'C': 'Multi\nline'},
                     'driver_vendor': 'VaporTech', 'package': 'spam-x1', 'repository':
                     'http://vaportech.com/x1', 'version': '1.1-foo42-vt3',
                     'fingerprint': '0000 FFFF 1111 EEEE 2222  DDDD 3333 CCCC 4444 BBBB'},
                    {'driver_type': 'kernel_module', 'jockey_handler':
                     'NoDetectMod', 'driver_vendor': 'White Hat',
                     'description': {'C': 'WhiteHat ndmod'}},
                    {'driver_type': 'kernel_module', 'jockey_handler':
                     'NoDetectMod', 'driver_vendor': 'Black Hat',
                     'description': {'C': 'BlackHat ndmod'}},
                    {'driver_type': 'kernel_module', 'kernel_module':
                     'mint', 'driver_vendor': 'UbuOne',
                     'description': {'C': 'UbuOne mintmod'}},
                    {'driver_type': 'kernel_module', 'kernel_module':
                     'mint', 'driver_vendor': 'UbunTwo',
                     'description': {'C': 'UbunTwo mintmod'},
                     'recommended': True},
                    {'driver_type': 'kernel_module', 'kernel_module':
                     'apple', 'driver_vendor': 'Apple', 'description':
                     {'C': 'Unknown local kmod'}, 'free': False, 
                     'license': 'Kills kittens', 'package': 'pretzel'},
                ]}
            ]
        )

    def test_invalid_query(self):
        '''XML-RPC driver DB server/client survive incomplete queries'''

        self.assertEqual(self.xmlrpc_client.query('20080407', '0', {}), 
            ['20080407', '0', {}])
        self.assertEqual(self.xmlrpc_client.query('20080407', '0', {
            'components': ['modalias:pci:foo']}),
            ['20080407', '0', {}])
        self.assertEqual(self.xmlrpc_client.query('20080407', '0', {
            'os_name': 'Foonux', 'components': ['modalias:pci:foo']}),
            ['20080407', '0', {}])

    def test_introspection(self):
        '''XML-RPC driver DB server supports expected methods'''

        self.assert_('query' in self.xmlrpc_client.system.listMethods())
        # methodSignature does not work with Python XML-RPC server


#-------------------------------------------------------------------#
# test handlers

h_avail_mod = '''
from jockey.handlers import KernelModuleHandler
class AvailMod(KernelModuleHandler):
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'vanilla',
            description='Test suite: available kernel module')
    def available(self):
        return True
'''

h_notavail_mod = '''
from jockey.handlers import KernelModuleHandler
class NotAvailMod(KernelModuleHandler):
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'chocolate',
            description='Test suite: non-available kernel module')
    def available(self):
        return False
'''

h_notavail_mint_mod = '''
from jockey.handlers import KernelModuleHandler
class NotAvailMod(KernelModuleHandler):
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'mint',
            description='Test suite: non-available kernel module')
    def available(self):
        return False
'''

h_nodetectmod = '''
class NoDetectMod(jockey.handlers.KernelModuleHandler):
    def __init__(self, ui):
        jockey.handlers.KernelModuleHandler.__init__(self, ui, 'spam',
            description='Test suite: non-detectable kernel module')
'''


# complete .py file contents with above three handlers
h_availability_py = 'import jockey.handlers\n%s\n%s\n%s\n' % (
    h_avail_mod, h_notavail_mod, h_nodetectmod)

h_nochangemod = '''
class NoChangeMod(jockey.handlers.KernelModuleHandler):
    def __init__(self, ui):
        jockey.handlers.KernelModuleHandler.__init__(self, ui, 'vanilla')
    def available(self):
        return True
    def can_change(self):
        return 'I must live'
'''

# custom handler for ignored kmod
h_ignored_custom_mod = '''
from jockey.handlers import KernelModuleHandler
class LessDullMod(KernelModuleHandler):
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'dullstd',
            description='Test suite: custom handler for dullstd (ignored kmod)')
'''

h_auto_install_mod = '''
from jockey.handlers import KernelModuleHandler
class AutoInstallHandler(KernelModuleHandler):
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'vanilla',
            description='Test suite: automatically installed handler')
        self._auto_install = True
    def available(self):
        return True
'''

h_privateclass_py = '''
import jockey.handlers

class _MyHandlerBase(jockey.handlers.KernelModuleHandler):
    def __init__(self, ui, param):
        jockey.handlers.KernelModuleHandler.__init__(self, ui, 'spam',
            description='Test suite: private base class')
        self.param = param
    def available(self):
        return True

class MyHandler(_MyHandlerBase):
    def __init__(self, ui):
        _MyHandlerBase.__init__(self, ui, 'foo')
'''

#-------------------------------------------------------------------#
# other globals

log = None
