# -*- coding: UTF-8 -*-

'''handler tests'''

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

import unittest, sys, os.path, re, subprocess, shutil

from jockey.oslib import OSLib
import jockey.handlers, jockey.backend
from jockey.xorg_driver import XorgDriverHandler

import sandbox

class TestAutoInstallHandler(jockey.handlers.Handler):

    def __init__(self, backend, name):
        jockey.handlers.Handler.__init__(self, backend, name, 
            'hardcoded auto-install handler')
        self._auto_install = True

class TestFirmwareHandler(jockey.handlers.FirmwareHandler):

    def __init__(self, backend, free=False):
        self.destfile = os.path.join(OSLib.inst.workdir, 'lib', 'firmware',
            'test.bin')
        jockey.handlers.FirmwareHandler.__init__(self, backend,
            'mint', self.destfile, url='file:///bin/cat', free=free)

    def enable(self):
        # TODO: FirmwareHandler is currently not really implemented
        #jockey.handlers.FirmwareHandler.enable(self)
        jockey.handlers.KernelModuleHandler.enable(self)

        d = os.path.dirname(self.destfile)
        if not os.path.isdir(d):
            os.makedirs(d)
        f = open(self.destfile, 'w')
        f.write(open(self.firmware_file).read())
        f.close()

        return jockey.handlers.KernelModuleHandler.rebind(self.module)

    def disable(self):
        if os.path.isfile(self.destfile):
            os.unlink(self.destfile)
        return jockey.handlers.KernelModuleHandler.disable(self)

class HandlerTest(sandbox.LogTestCase):

    def setUp(self):
        '''Provide a Backend instance for getting install_package etc. and save/restore
        /proc/modules, module blacklist, installed packages, and xorg.conf.
        '''
        self.backend = jockey.backend.Backend()
        OSLib.inst._make_xorg_conf()

    def tearDown(self):
        '''Undo changes to the sandbox.'''

        try:
            os.unlink(OSLib.inst.module_blacklist_file)
        except OSError:
            pass
        for f in os.listdir(OSLib.inst.backup_dir):
            os.unlink(os.path.join(OSLib.inst.backup_dir, f))
        OSLib.inst._load_module_blacklist()

        OSLib.inst.reset_packages()
        OSLib.inst._make_proc_modules()
        jockey.handlers.KernelModuleHandler.read_loaded_modules()
        auto_d = os.path.join(OSLib.inst.handler_dir, 'autoinstall.d')
        if os.path.isdir(auto_d):
            shutil.rmtree(auto_d)

    def test_basic(self):
        '''abstract Handler'''

        # no description, no rationale
        h = jockey.handlers.Handler(self.backend, 'shiny driver')
        self.assertEqual(h.name(), 'shiny driver')
        self.assertEqual(h.description(), None)
        self.assertEqual(h.id(), 'Handler:shiny driver')
        self.assertEqual(h.rationale(), None)
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.assertEqual(h.announce, True)

        # description and rationale
        h = jockey.handlers.Handler(self.backend, 'shiny driver', 
            'I provide bling', rationale='I am important!')
        self.assertEqual(h.rationale(), 'I am important!')
        self.assertEqual(h.description(), 'I provide bling')

        # vendor
        h.driver_vendor = 'Foo Bar'
        self.assertEqual(h.id(), 'Handler:shiny driver:Foo_Bar')

        # free
        self.assertRaises(NotImplementedError, h.free)
        h._free = False
        self.assertEqual(h.free(), False)

    def test_module_loaded(self):
        '''Handler.module_loaded()'''

        self.failIf(jockey.handlers.KernelModuleHandler.module_loaded('spam'))
        self.assertEqual(subprocess.call([OSLib.inst.modprobe_path, 'spam']), 0)
        # result is still cached
        self.failIf(jockey.handlers.KernelModuleHandler.module_loaded('spam'))
        # kill cache and retry
        jockey.handlers.KernelModuleHandler._loaded_modules = None
        self.assert_(jockey.handlers.KernelModuleHandler.module_loaded('spam'))

    def test_kmod_free(self):
        '''KernelModuleHandler: free, no description, used'''

        h = jockey.handlers.KernelModuleHandler(self.backend, 'vanilla')
        self.assertEqual(h.name(), sandbox.fake_modinfo['vanilla']['description'])
        self.assertEqual(h.id(), 'kmod:vanilla')
        self.assertEqual(str(h), 'kmod:vanilla([KernelModuleHandler, free, enabled] '
            'free module with available hardware, graphics card)')
        self.assertEqual(h.description(), None)
        self.assertEqual(h.rationale(), None) # free
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)

        self.assert_(h.free())
        self.assert_(h.enabled())
        self.assertEqual(h.recommended(), False)
        self.assert_(h.used())
        self.assertEqual(h.available(), None)
        
        # vendor
        h.driver_vendor = 'Foo Bar'
        self.assertEqual(h.id(), 'kmod:vanilla:Foo_Bar')

    def test_kmod_free_otherlicenses(self):
        '''KernelModuleHandler: freeness of various licenses'''

        self.assert_(jockey.handlers.KernelModuleHandler(self.backend,
            'chocolate').free(), 'BSD is free')
        self.failIf(jockey.handlers.KernelModuleHandler(self.backend,
            'cherry').free(), '"evil" is nonfree')
        self.assert_(jockey.handlers.KernelModuleHandler(self.backend,
            'spam').free(), 'GPL v2 is free')

    def test_kmod_nonfree(self):
        '''KernelModuleHandler: nonfree, custom description, unused'''

        h = jockey.handlers.KernelModuleHandler(self.backend, 'cherry',
            description='you want me')
        self.assertEqual(h.name(), sandbox.fake_modinfo['cherry']['description'])
        self.assertEqual(h.id(), 'kmod:cherry')
        self.assertEqual(str(h), 'kmod:cherry([KernelModuleHandler, nonfree, enabled] '
            'nonfree module with nonavailable hardware, wifi)')
        self.assertEqual(h.description(), 'you want me')
        self.assertEqual(h.rationale(), None)
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)

        self.failIf(h.free())
        self.assert_(h.enabled())
        self.assertEqual(h.recommended(), False)
        self.failIf(h.used())
        self.assertEqual(h.available(), None)

        # enabling it should modprobe
        h.enable()
        self.assert_(h.used())

    def test_kmod_customdesc(self):
        '''KernelModuleHandler: custom name and rationale'''

        h = jockey.handlers.KernelModuleHandler(self.backend, 'cherry',
            name='fruitz', rationale='goood')
        self.assertEqual(h.name(), 'fruitz')
        self.assertEqual(h.id(), 'kmod:cherry')
        self.assertEqual(h.rationale(), 'goood')

    def test_kmod_enabling(self):
        '''KernelModuleHandler: enabling and disabling'''

        self.failIf(OSLib.inst.module_blacklisted('vanilla'))

        h = jockey.handlers.KernelModuleHandler(self.backend, 'vanilla')
        h.disable()
        self.assert_(h.changed())
        self.assert_(OSLib.inst.module_blacklisted('vanilla'))
        h.disable()
        self.assert_(h.changed())
        self.assert_(OSLib.inst.module_blacklisted('vanilla'))
        self.assert_(h.enable())
        self.assert_(h.changed())
        self.failIf(OSLib.inst.module_blacklisted('vanilla'))
        driver_dir = os.path.join(OSLib.inst.sys_dir, 'module', 'vanilla',
            'drivers', 'pci:vanilla')
        self.assert_(os.path.isfile(os.path.join(driver_dir, 'unbind')))
        self.assert_(os.path.isfile(os.path.join(driver_dir, 'bind')))

    def test_kmod_package(self):
        '''KernelModuleHandler: third-party package'''

        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        h = jockey.handlers.KernelModuleHandler(self.backend,
            'vanilla3d', rationale='Get full graphics acceleration speed')
        h.package = 'mesa-vanilla'

        self.assertEqual(h.name(), sandbox.fake_modinfo['vanilla3d']['description'])
        self.assertEqual(h.id(), 'kmod:vanilla3d')
        self.assertEqual(h.description(),  OSLib.inst.package_description('mesa-vanilla')[1])
        self.assertEqual(h.rationale(), 'Get full graphics acceleration speed')
        self.failIf(h.free())
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.failIf(h.enabled())
        self.assertEqual(h.available(), None)

        h.enable()
        self.assert_(h.changed())
        self.assert_(h.enabled())
        self.assert_(OSLib.inst.package_installed('mesa-vanilla')) 
        self.failIf(OSLib.inst.package_installed('linux-dev')) 
        self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))

        h.disable()
        self.assert_(h.changed())
        self.failIf(h.enabled())
        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        self.assert_(OSLib.inst.module_blacklisted('vanilla3d'))

        # vendor
        h.driver_vendor = 'Foo Bar'
        self.assertEqual(h.id(), 'kmod:vanilla3d:Foo_Bar')

        # unavailable package
        h.package = 'nonexisting'
        self.assertEqual(h.available(), False)

    def test_kmod_package_kernelheaders(self):
        '''KernelModuleHandler: package needing kernel headers'''

        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        h = jockey.handlers.KernelModuleHandler(self.backend,
            'vanilla3d', rationale='Get full graphics acceleration speed')
        h.package = 'mesa-vanilla'
        h.needs_kernel_headers = True

        h.enable()
        self.assert_(h.changed())
        self.assert_(h.enabled())
        self.assert_(OSLib.inst.package_installed('mesa-vanilla')) 
        self.assert_(OSLib.inst.package_installed('linux-dev')) 
        self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))

    def test_kmod_package_used(self):
        '''KernelModuleHandler: used() with third-party packages'''

        assert jockey.handlers.KernelModuleHandler.module_loaded('vanilla')
        assert not OSLib.inst.package_installed('mesa-vanilla')
        h = jockey.handlers.KernelModuleHandler(self.backend, 'vanilla')
        # no package, module loaded -> used
        self.assert_(h.used())
        # uninstalled package -> not used
        h.package = 'mesa-vanilla'
        self.failIf(h.used())
        OSLib.inst.install_package('mesa-vanilla', None)
        # installed package -> used
        self.assert_(h.used())

    def test_kmod_unknown(self):
        '''KernelModuleHandler: not available locally'''

        h = jockey.handlers.KernelModuleHandler(self.backend, 'apple',
            name='Apple kmod')
        h._free = True
        self.assertEqual(h.name(), 'Apple kmod')
        self.assertEqual(h.id(), 'kmod:apple')
        self.assertEqual(str(h), 'kmod:apple([KernelModuleHandler, free, disabled] Apple kmod)')
        self.assertEqual(h.description(), None)
        self.assertEqual(h.rationale(), None) # free
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.assert_(h.free())
        self.failIf(h.enabled())
        self.failIf(h.used())

    def test_group(self):
        '''HandlerGroup'''

        h = jockey.handlers.HandlerGroup(self.backend, 'graphics drivers', 'gfxdrv')

        # empty group
        self.assert_(h.free())
        self.assert_(h.enabled())
        self.failIf(h.used())
        self.failIf(h.available())
        self.failIf(h.changed())

        # add a free driver
        h.add(jockey.handlers.KernelModuleHandler(self.backend, 'vanilla'))
        self.assertEqual(h.name(), 'graphics drivers')
        self.assertEqual(h.id(), 'gfxdrv')
        self.assertEqual(h.description(), None)
        self.assertEqual(h.rationale(), None)
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.assert_(h.free())
        self.assert_(h.enabled())
        self.assert_(h.used())
        self.assertEqual(h.available(), None)

        # add a nonfree driver
        h.add(jockey.handlers.KernelModuleHandler(self.backend, 'vanilla3d'))
        self.assertEqual(h.name(), 'graphics drivers')

        self.assertEqual(h.rationale(), None)
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.failIf(h.free()) # subset nonfree -> group nonfree
        self.assert_(h.enabled()) # both modules are enabled by default
        self.assert_(h.used()) # vanilla is used by default, ORed
        self.assertEqual(h.available(), None)

        self.failIf(OSLib.inst.module_blacklisted('vanilla'))
        self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))
        self.assert_(jockey.handlers.KernelModuleHandler.module_loaded('vanilla'))
        self.failIf(jockey.handlers.KernelModuleHandler.module_loaded('vanilla3d'))

        h.enable()
        self.assert_(h.enabled())
        self.assert_(h.changed())
        self.assert_(jockey.handlers.KernelModuleHandler.module_loaded('vanilla'))
        self.assert_(jockey.handlers.KernelModuleHandler.module_loaded('vanilla3d'))

        h.disable()
        self.failIf(h.enabled())
        self.assert_(h.changed())
        self.assert_(OSLib.inst.module_blacklisted('vanilla'))
        self.assert_(OSLib.inst.module_blacklisted('vanilla3d'))

        # add available handler
        self.assertEqual(h.available(), None)
        names = {}
        exec(sandbox.h_availability_py, names)
        h.add (names['AvailMod'](self.backend))
        self.assertEqual(h.available(), True)

        # all unavailable -> group unavailable
        na_grp = jockey.handlers.HandlerGroup(self.backend, 'N/A group', 'nagrp')
        na_grp.add(names['NotAvailMod'](self.backend))
        self.assertEqual(na_grp.available(), False)

        # add unchangeable handler
        self.assertEqual(h.can_change(), None)
        names = {}
        exec('import jockey.handlers\n' + sandbox.h_nochangemod, names)
        h.add (names['NoChangeMod'](self.backend))
        self.assertNotEqual(h.can_change(), None)

    def test_driverpackage(self):
        '''handler with package: default name and rationale'''

        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        h = jockey.handlers.Handler(self.backend, None,
            rationale='Get full graphics acceleration speed')
        h.package = 'mesa-vanilla'

        self.assertEqual(h.name(),  OSLib.inst.package_description('mesa-vanilla')[0])
        self.assertEqual(h.id(), 'pkg:mesa-vanilla')
        self.assertEqual(h.description(),  OSLib.inst.package_description('mesa-vanilla')[1])
        self.assertEqual(h.rationale(), 'Get full graphics acceleration speed')
        self.failIf(h.free())
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.failIf(h.enabled())
        self.assertEqual(h.available(), None)

        self.assert_(h.enable())
        self.assert_(h.changed())
        self.assert_(h.enabled())
        self.assert_(OSLib.inst.package_installed('mesa-vanilla')) 

        h.disable()
        self.assert_(h.changed())
        self.failIf(h.enabled())
        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 

        # vendor
        h.driver_vendor = 'Foo Bar'
        self.assertEqual(h.id(), 'pkg:mesa-vanilla:Foo_Bar')

    def test_driverpackage_customdesc(self):
        '''handler with package: custom name and rationale'''

        self.failIf(OSLib.inst.package_installed('mesa-vanilla'))
        h = jockey.handlers.Handler(self.backend, 'VanillaName', 'VanillaDesc')
        h.package = 'mesa-vanilla'

        self.assertEqual(h.name(), 'VanillaName')
        self.assertEqual(h.id(), 'pkg:mesa-vanilla')
        self.assertEqual(h.description(), 'VanillaDesc')
        self.assertEqual(h.rationale(), None)
        self.assertEqual(h.free(), False)
        self.failIf(h.free())
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.failIf(h.enabled())
        self.assertEqual(h.available(), None)

    def test_driverpackage_failedinstall(self):
        '''handler with package: package installation fails'''

        self.failIf(OSLib.inst.package_installed('mesa-vanilla'))
        h = jockey.handlers.Handler(self.backend, 'VanillaName', 'VanillaDesc')
        h.package = 'mesa-vanilla'

        OSLib.inst.next_package_install_fails = True
        self.assert_(h.enable())
        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        self.failIf(h.enabled())
        self.failIf(h.changed())

    def test_driverpackage_nonexisting(self):
        '''handler with package: nonexisting package'''

        # cannot get package name/description/freeness
        h = jockey.handlers.Handler(self.backend, None)
        h.package = 'unknownpackage'
        self.assertRaises(ValueError, h.name)

        h = jockey.handlers.Handler(self.backend, name='testunknown', description='TestUnknown',
            rationale='Unknown?')
        h.package = 'unknownpackage'
        h._free = True

        self.assertEqual(h.name(), 'testunknown')
        self.assertEqual(h.id(), 'pkg:unknownpackage')
        self.assertEqual(h.description(), 'TestUnknown')
        self.assertEqual(h.rationale(), 'Unknown?')
        self.assertEqual(h.free(), True)
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.failIf(h.enabled())
        self.assertEqual(h.available(), False)

    def test_driverpackage_extrepo(self):
        '''handler with package: external repository'''

        self.failIf(OSLib.inst.package_installed('foo-y1')) 
        h = jockey.handlers.Handler(self.backend, None)
        h.package = 'foo-y1'
        h.repository = 'http://vaportech.com/x1'
        h.driver_vendor = 'VaporTech'
        self.assertEqual(h.id(), 'pkg:foo-y1:VaporTech')

        self.failIf(h.changed())
        self.failIf(h.enabled())
        self.assertEqual(h.available(), None)

        self.assert_(h.enable())
        self.assert_(h.changed())
        self.assert_(h.enabled())
        self.assert_(OSLib.inst.package_installed('foo-y1')) 

        h.disable()
        self.assert_(h.changed())
        self.failIf(h.enabled())
        self.failIf(OSLib.inst.package_installed('foo-y1')) 

    def test_xorg_driver_nomodules(self):
        '''XorgDriverHandler with no default Modules xorg.conf section'''
        
        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        orig_xorg_conf = open(OSLib.inst.xorg_conf_path).read()

        self.assertEqual(h.name(), 'Vanilla accelerated graphics driver')
        self.assertEqual(h.id(), 'xorg:vanilla3d')
        self.assertEqual(h.description(),  OSLib.inst.package_description('mesa-vanilla')[1])
        self.assertEqual(h.rationale(), None)
        self.failIf(h.free())
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.failIf(h.enabled())
        self.failIf(h.used())
        self.assertEqual(h.available(), None)
        self.failIf(h.enables_composite())

        self.failIf(h.enable())
        self.assert_(h.changed())
        self.failIf(h.used()) # X.org needs to be restarted for this to work
        self.assert_(h.enabled())
        self.assert_(OSLib.inst.package_installed('mesa-vanilla')) 
        self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))

        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # driver should be used when loading the module (done in enable()) and
        # starting jockey again
        h2 = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')
        self.assert_(h2.enabled())
        self.assert_(h2.used())

        self.failIf(h.disable())
        self.assert_(h.changed())
        self.failIf(h.enabled())
        self.failIf(h.used()) # wasn't used after enabling
        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        self.assert_(OSLib.inst.module_blacklisted('vanilla3d'))

        # restores original backup
        self.assertEqual(open(OSLib.inst.xorg_conf_path).read(), orig_xorg_conf)

        # vendor
        h.driver_vendor = 'Foo Bar'
        self.assertEqual(h.id(), 'xorg:vanilla3d:Foo_Bar')

    def test_xorg_driver_nobackup(self):
        '''XorgDriverHandler with no xorg.conf backup'''
        
        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        self.failIf(h.enable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # unlink backup file
        os.unlink(os.path.join(OSLib.inst.backup_dir, 'v3d.oldconf'))

        self.failIf(h.disable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.failIf('SuperSpeed' in conf)
        self.failIf(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        # modules which were explicitly disabled should be removed
        self.failIf(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))
    
    def test_xorg_driver_existing_proprietary(self):
        '''XorgDriverHandler backup with the proprietary driver already in xorg.conf'''
        
        f = open(OSLib.inst.xorg_conf_path, 'a')
        print >> f, '''
Section "Device"
        Identifier "Graphics card 1"
        Driver "via"
EndSection

Section "Device"
        Identifier "Graphics card 2"
        Driver "v3d"
EndSection
'''
        f.close()
        
        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        self.failIf(h.enable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*driver\s*"via"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # no backup file should have been created
        self.failIf(os.path.isfile(os.path.join(OSLib.inst.backup_dir, 'v3d.oldconf')))
    
        # disabling should restore xorg.conf
        self.failIf(h.disable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*driver\s*"via"\s*$', conf, re.I|re.M))

    def test_xorg_driver_enable_all_no_serverlayout(self):
        '''XorgDriverHandler enable the proprietary driver without ServerLayout in xorg.conf'''
        
        os.unlink(OSLib.inst.xorg_conf_path)
        
        f = open(OSLib.inst.xorg_conf_path, 'a')
        print >> f, '''
Section "Device"
        Identifier "Graphics card 1"
        Driver "via"
EndSection

Section "Device"
        Identifier "Graphics card 2"
        Driver "via"
EndSection
'''
        f.close()
        
        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        # all drivers will be changed
        self.failIf(h.enable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*driver\s*"via"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # backup file should have been created
        self.assert_(os.path.isfile(os.path.join(OSLib.inst.backup_dir, 'v3d.oldconf')))
    
        # disabling should restore xorg.conf
        self.failIf(h.disable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.failIf(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*driver\s*"via"\s*$', conf, re.I|re.M))

    def test_xorg_driver_enable_all_one_serverlayout(self):
        '''XorgDriverHandler enable the proprietary driver with one ServerLayout in xorg.conf'''
        
        os.unlink(OSLib.inst.xorg_conf_path)
        
        f = open(OSLib.inst.xorg_conf_path, 'a')
        print >> f, '''
Section "Device"
        Identifier "Graphics card 1"
        Driver "via"
EndSection

Section "Device"
        Identifier "Graphics card 2"
        Driver "via"
EndSection

Section "Screen"
        Identifier "Screen 1"
        Device "Graphics card 1"
EndSection

Section "Screen"
        Identifier "Screen 2"
        Device "Graphics card 2"
EndSection

Section "ServerLayout"
        Identifier "Another Layout"
        Screen "Screen 2"
EndSection
'''
        f.close()
        
        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')
        
        # only the 2nd device section should have the driver changed
        self.failIf(h.enable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*driver\s*"via"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # backup file should have been created
        self.assert_(os.path.isfile(os.path.join(OSLib.inst.backup_dir, 'v3d.oldconf')))
    
        # disabling should restore xorg.conf
        self.failIf(h.disable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.failIf(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*driver\s*"via"\s*$', conf, re.I|re.M))

    def test_xorg_driver_enable_all_more_serverlayouts(self):
        '''XorgDriverHandler enable the proprietary driver with more ServerLayouts in xorg.conf'''
        
        os.unlink(OSLib.inst.xorg_conf_path)
        
        f = open(OSLib.inst.xorg_conf_path, 'a')
        print >> f, '''
Section "Device"
        Identifier "Graphics card 1"
        Driver "via"
EndSection

Section "Device"
        Identifier "Graphics card 2"
        Driver "via"
EndSection

Section "Screen"
        Identifier "Screen 1"
        Device "Graphics card 1"
EndSection

Section "Screen"
        Identifier "Screen 2"
        Device "Graphics card 2"
EndSection

Section "ServerLayout"
        Identifier "Default Layout"
        Option "Whatever"
        Screen "Screen 1" 0 0
        Screen "Screen 2" RightOf "Screen 1"
EndSection

Section "ServerLayout"
        Identifier "Another Layout"
        Option "Whatever"
        Screen "Screen 2" 0 0
EndSection

Section "ServerFlags"
        Option "DefaultServerLayout" "Another Layout"
EndSection
'''
        f.close()
        
        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        # the 2nd serverlayout is used, therefore only the 2nd device section must be
        # changed
        self.failIf(h.enable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*driver\s*"via"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # backup file should have been created
        self.assert_(os.path.isfile(os.path.join(OSLib.inst.backup_dir, 'v3d.oldconf')))
    
        # disabling should restore xorg.conf
        self.failIf(h.disable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.failIf(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*driver\s*"via"\s*$', conf, re.I|re.M))

    def test_xorg_driver_modules(self):
        '''XorgDriverHandler with default Modules xorg.conf section'''

        # append a Module section
        f = open(OSLib.inst.xorg_conf_path, 'a')
        print >> f, '''
Section "Module"
        Load            "dri"
        SubSection "extmod"
                Option          "omit xfree86-dga"
        EndSubSection
        Load            "foo"
EndSection
'''
        f.close()

        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        self.assertEqual(h.name(), 'Vanilla accelerated graphics driver')
        self.assertEqual(h.description(),  OSLib.inst.package_description('mesa-vanilla')[1])
        self.assertEqual(h.rationale(), None)
        self.failIf(h.free())
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)
        self.failIf(h.enabled())
        self.assertEqual(h.available(), None)

        self.failIf(h.enable())
        self.assert_(h.changed())
        self.assert_(h.enabled())
        self.assert_(OSLib.inst.package_installed('mesa-vanilla')) 
        self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))

        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"foo"\s*$', conf, re.I|re.M))

        # unlink backup file
        os.unlink(os.path.join(OSLib.inst.backup_dir, 'v3d.oldconf'))

        # should restore module dri, drop glx and remove dri2
        self.failIf(h.disable())
        self.assert_(h.changed())
        self.failIf(h.enabled())
        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        self.assert_(OSLib.inst.module_blacklisted('vanilla3d'))

        conf = open(OSLib.inst.xorg_conf_path).read()
        self.failIf(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"foo"\s*$', conf, re.I|re.M))

    def test_xorg_driver_no_xorgconf(self):
        '''XorgDriverHandler without a default xorg.conf'''

        os.unlink(OSLib.inst.xorg_conf_path)

        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        self.failIf(h.free())
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None) # should create an xorg.conf from scratch
        self.failIf(h.enabled())
        self.assertEqual(h.available(), None)

        self.failIf(h.enable())
        self.assert_(h.changed())
        self.assert_(h.enabled())
        self.assert_(OSLib.inst.package_installed('mesa-vanilla')) 
        self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))

        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"v3d"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # should remove xorg.conf again
        self.failIf(h.disable())
        self.assert_(h.changed())
        self.failIf(h.enabled())
        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        self.assert_(OSLib.inst.module_blacklisted('vanilla3d'))
        self.failIf(os.path.exists(OSLib.inst.xorg_conf_path))

    def test_xorg_driver_no_xorgconf_nodriver(self):
        '''XorgDriverHandler without a default xorg.conf and no explicit "Driver"'''

        os.unlink(OSLib.inst.xorg_conf_path)

        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', None,
            None, extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'],
            name='Vanilla accelerated graphics driver')

        self.failIf(h.free())
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None) # should create an xorg.conf from scratch
        self.failIf(h.enabled())
        self.assertEqual(h.available(), None)

        self.failIf(h.enable())
        self.assert_(h.changed())
        self.assert_(h.enabled())
        self.assert_(OSLib.inst.package_installed('mesa-vanilla')) 
        self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))

        conf = open(OSLib.inst.xorg_conf_path).read()
        self.failIf(re.search('^\s*driver', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # should remove xorg.conf again
        self.failIf(h.disable())
        self.assert_(h.changed())
        self.failIf(h.enabled())
        self.failIf(OSLib.inst.package_installed('mesa-vanilla')) 
        self.assert_(OSLib.inst.module_blacklisted('vanilla3d'))
        self.failIf(os.path.exists(OSLib.inst.xorg_conf_path))

    def test_xorg_driver_nobackup_nodriver(self):
        '''XorgDriverHandler with no xorg.conf backup and no explicit "Driver"'''
        
        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', None,
            None, extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        self.failIf(h.enable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        # should keep the "Driver" as it was before
        self.assert_(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*option\s*"SuperSpeed"\s*"true"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.failIf(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))

        # unlink backup file
        os.unlink(os.path.join(OSLib.inst.backup_dir, 'mesa-vanilla.oldconf'))

        self.failIf(h.disable())
        conf = open(OSLib.inst.xorg_conf_path).read()
        self.assert_(re.search('^\s*driver\s*"vanilla"\s*$', conf, re.I|re.M))
        self.failIf('SuperSpeed' in conf)
        self.failIf(re.search('^\s*load\s*"glx"\s*$', conf, re.I|re.M))
        # modules which were explicitly disabled should be removed
        self.failIf(re.search('^\s*disable\s*"dri2"\s*$', conf, re.I|re.M))
        self.assert_(re.search('^\s*load\s*"dri"\s*$', conf, re.I|re.M))
    
    def test_xorg_invalid_conf(self):
        '''XorgDriverHandler with invalid xorg.conf'''

        # append some breakage
        f = open(OSLib.inst.xorg_conf_path, 'a')
        print >> f, '''
EndSection

Section "Module"
EndSection
'''
        f.close()

        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', extra_conf_options={'SuperSpeed': 'true'}, 
            add_modules=['glx'], disable_modules=['dri2'], remove_modules=['dri'],
            name='Vanilla accelerated graphics driver')

        self.assertEqual(h.name(), 'Vanilla accelerated graphics driver')
        self.assertEqual(h.description(),  OSLib.inst.package_description('mesa-vanilla')[1])
        self.assertEqual(h.rationale(), None)
        self.failIf(h.free())
        self.failIf(h.changed())
        self.assert_('xorg.conf is invalid' in h.can_change())
        self.failIf(h.enabled())
        self.assertEqual(h.available(), None)

        self.failIf(h.enable())
        self.failIf(h.changed())
        self.failIf(h.enabled())
        self.failIf(h.disable())
        self.failIf(h.changed())
        self.failIf(h.enabled())

    def test_xorg_driver_abi_checking(self):
        '''XorgDriverHandler ABI checking'''

        h = XorgDriverHandler(self.backend, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla', name='Vanilla accelerated graphics driver')

        # our TestOSLib doesn't define video_driver_abi(), so should be
        # available by default
        self.assertNotEqual(h.available(), False)

        orig_video_driver_abi = OSLib.inst.video_driver_abi
        try:
            # should be available for matching ABI
            OSLib.inst.video_driver_abi = lambda pkg: OSLib.inst.current_xorg_video_abi()
            self.assertNotEqual(h.available(), False)

            # should not be available for nonmatching ABI
            OSLib.inst.video_driver_abi = lambda pkg: 'otherabi'
            self.assertEqual(h.available(), False)
        finally:
            OSLib.inst.video_driver_abi = orig_video_driver_abi

    def test_xorg_driver_loaded_drivers(self):
        '''XorgDriverHandler.loaded_drivers()'''

        # system one
        drivers = XorgDriverHandler.loaded_drivers()
        self.assertEqual(type(drivers), type(set()))
        if 'DISPLAY' in os.environ:
            self.assertGreaterEqual(len(drivers), 1)

        # synthetic
        with open(os.path.join(OSLib.inst.workdir, 'Xorg.1.log'), 'w') as f:
            f.write('''X.Org X Server 1.10.4
[    14.451] (II) LoadModule: "intel"
[    14.452] (II) Loading /usr/lib/xorg/modules/drivers/intel_drv.so
[    14.459] (II) LoadModule: "vesa"
[    14.459] (II) Loading /usr/lib/xorg/modules/drivers/vesa_drv.so
[    14.452] (II) Loading /usr/lib/xorg/modules/drivers/intel_drv.so
''')
        self.assertEqual(XorgDriverHandler.loaded_drivers(OSLib.inst.workdir),
                set(['intel', 'vesa']))

    def test_firmware_handler(self):
        '''standard FirmwareHandler'''

        h = jockey.handlers.FirmwareHandler(self.backend, 'vanilla', '/foo')

        self.failIf(h.free())
        self.assertEqual(h.name(), sandbox.fake_modinfo['vanilla']['description'])
        self.assertEqual(h.id(), 'firmware:vanilla')
        self.assertEqual(str(h), 'firmware:vanilla([FirmwareHandler, nonfree, disabled] '
            'free module with available hardware, graphics card)')
        self.assertEqual(h.description(), None)
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)

        self.failIf(h.enabled())
        self.failIf(h.used())
        self.assertEqual(h.available(), None)

        # defined free
        h = jockey.handlers.FirmwareHandler(self.backend, 'vanilla', '/foo',
            free=True)
        self.assert_(h.free())
        # get freeness from kmod
        h = jockey.handlers.FirmwareHandler(self.backend, 'vanilla', '/foo',
            free=None)
        self.assert_(h.free())
        h = jockey.handlers.FirmwareHandler(self.backend, 'vanilla3d', '/foo',
            free=None)
        self.failIf(h.free())

        # vendor
        h.driver_vendor = 'Foo Bar'
        self.assertEqual(h.id(), 'firmware:vanilla3d:Foo_Bar')

    def test_testfirmware_handler(self):
        '''TestFirmwareHandler'''

        h = TestFirmwareHandler(self.backend)
        self.assertEqual(h.name(), sandbox.fake_modinfo['mint']['description'])
        self.assertEqual(h.id(), 'firmware:mint')
        self.assertEqual(str(h), 'firmware:mint([TestFirmwareHandler, nonfree, disabled] '
            'nonfree module with available hardware, wifi)')
        self.assertEqual(h.description(), None)
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)

        self.failIf(h.free())
        self.failIf(h.enabled())
        self.failIf(h.used())
        self.assertEqual(h.available(), None)

        # TODO: FirmwareHandler is not currenty implemented
        #self.assert_(h.enable())
        #self.assert_(h.changed())
        #self.assert_(h.enabled())
        #self.assert_(h.used())

        #h.disable()
        #self.assert_(h.changed())
        #self.failIf(h.enabled())
        #self.failIf(h.used())

    def test_firmware_handler_free(self):
        '''standard FirmwareHandler, forced to free'''

        h = TestFirmwareHandler(self.backend, free='1')
        self.assertEqual(h.name(), sandbox.fake_modinfo['mint']['description'])
        self.assertEqual(h.id(), 'firmware:mint')
        self.assert_(h.free())
        self.assertEqual(str(h), 'firmware:mint([TestFirmwareHandler, free, disabled] '
            'nonfree module with available hardware, wifi)')
        self.assertEqual(h.description(), None)

    def test_printer_handler_basic(self):
        '''PrinterDriverHandler'''

        # no description, no rationale
        h = jockey.handlers.PrinterDriverHandler(self.backend, 'shiny driver')
        self.assertEqual(h.name(), 'shiny driver')
        self.assertEqual(h.description(), None)
        self.assertEqual(h.id(), 'printer:shiny driver')
        self.assertEqual(h.rationale(), None)
        self.failIf(h.changed())
        self.assertEqual(h.can_change(), None)

    def test_auto_install_hardcoded(self):
        '''Handler auto-installed with hardcoded flag'''

        h = jockey.handlers.Handler(self.backend, 'autotest')
        self.assertEqual(h.auto_install(), False)
        h = TestAutoInstallHandler(self.backend, 'autotest')
        self.assertEqual(h.auto_install(), True)

    def test_auto_install_flagfile(self):
        '''Handler auto-installed with autoinstall.d/ file'''

        d = os.path.join(OSLib.inst.handler_dir, 'autoinstall.d')
        os.mkdir(d)
        f = open(os.path.join(d, 'Handler:autotest'), 'w')
        f.close()
        h = jockey.handlers.Handler(self.backend, 'autotest')
        self.assertEqual(h.auto_install(), True)

