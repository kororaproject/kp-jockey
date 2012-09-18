# -*- coding: UTF-8 -*-

'''oslib tests'''

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

import unittest, os, tempfile, shutil, subprocess

from jockey.oslib import OSLib
import sandbox
import httpd

import jockey.detection

# fingerprint of tests/data/pubring.gpg
test_gpg_fp = '4EF8 3174 F985 6BD6 0E8D  584C 1A2E C5F3 E6B6 0077'

class OSLibTest(sandbox.LogTestCase):
    '''OSLib tests'''

    def setUp(self):
        (fd, self.tempfile) = tempfile.mkstemp()
        os.close(fd)

    def tearDown(self):
        os.unlink(self.tempfile)

    def test_module_blacklisting(self):
        '''module_blacklisted() and blacklist_module()'''

        for m in sandbox.fake_modinfo:
            self.failIf(OSLib.inst.module_blacklisted(m))

            # remove nonexisting entry
            OSLib.inst.blacklist_module(m, False)
            self.failIf(OSLib.inst.module_blacklisted(m))

            # double addition
            OSLib.inst.blacklist_module(m, True)
            self.assert_(OSLib.inst.module_blacklisted(m))
            OSLib.inst.blacklist_module(m, True)
            self.assert_(OSLib.inst.module_blacklisted(m))

        self.assertEqual(open(OSLib.inst.module_blacklist_file).read(), 
            ''.join(['blacklist %s\n' % m for m in sorted(sandbox.fake_modinfo.keys())]))

        # file is removed once it becomes empty
        for m in sandbox.fake_modinfo:
            OSLib.inst.blacklist_module(m, False)
            self.failIf(OSLib.inst.module_blacklisted(m))

        self.failIf(os.path.exists(OSLib.inst.module_blacklist_file))

        # directory gets created if it does not exist
        os.rmdir(os.path.dirname(OSLib.inst.module_blacklist_file))
        OSLib.inst.blacklist_module('vanilla', True)
        self.assert_(OSLib.inst.module_blacklisted('vanilla'))
        OSLib.inst.blacklist_module('vanilla', False)
        self.failIf(os.path.exists(OSLib.inst.module_blacklist_file))

    def test_module_blacklist_load(self):
        '''module blacklist loading.'''

        f = open(OSLib.inst.module_blacklist_file, 'w')
        try:
            f.write('''blacklist vanilla
# FOO BAR

 blacklist  cherry # we do not like red fruits
# blacklist mint
''')
            f.close()

            OSLib.inst._load_module_blacklist()

            self.assert_(OSLib.inst.module_blacklisted('vanilla'))
            self.assert_(OSLib.inst.module_blacklisted('cherry'))
            self.failIf(OSLib.inst.module_blacklisted('chocolate'))
            self.failIf(OSLib.inst.module_blacklisted('mint'))
            self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))
        finally:
            os.unlink(OSLib.inst.module_blacklist_file)
            OSLib.inst._load_module_blacklist()

    def test_module_blacklist_load_thirdparty(self):
        '''module blacklist loading of other files in modprobe.d/.'''

        path = os.path.join(os.path.dirname(OSLib.inst.module_blacklist_file),
            'blacklist-custom')
        f = open(path, 'w')
        try:
            f.write('''blacklist vanilla
# FOO BAR

 blacklist  cherry # we do not like red fruits
# blacklist mint
''')
            f.close()

            OSLib.inst._load_module_blacklist()

            self.assert_(OSLib.inst.module_blacklisted('vanilla'))
            self.assert_(OSLib.inst.module_blacklisted('cherry'))
            self.failIf(OSLib.inst.module_blacklisted('chocolate'))
            self.failIf(OSLib.inst.module_blacklisted('mint'))
            self.failIf(OSLib.inst.module_blacklisted('vanilla3d'))
        finally:
            os.unlink(path)
            OSLib.inst._load_module_blacklist()

    def test_get_system_vendor_product(self):
        '''get_system_vendor_product()'''

        # vendor/product name
        self.assertEqual(OSLib.inst.get_system_vendor_product(), 
                ('VaporTech Inc.', 'Virtualtop X-1'))

        # without vendor/product name
        OSLib.inst.set_dmi(None, None)
        self.assertEqual(OSLib.inst.get_system_vendor_product(), ('', ''))

        # vendor name only
        OSLib.inst.set_dmi('VaporTech Inc.', None)
        self.assertEqual(OSLib.inst.get_system_vendor_product(), 
            ('VaporTech Inc.', ''))

        # actual system's implementation is a string
        v, p = OSLib(client_only=True).get_system_vendor_product()
        self.assert_(hasattr(v, 'startswith'))
        self.assert_(hasattr(p, 'startswith'))

    def test_package_query(self):
        '''package querying'''

        # use real OSLib here, not test suite's fake implementation
        o = OSLib()

        self.assertEqual(o.package_installed('coreutils'), True)
        self.assertEqual(o.package_installed('nonexisting'), False)

        self.assertEqual(o.is_package_free('coreutils'), True)
        self.assertRaises(ValueError, o.is_package_free, 'nonexisting')

        (short, long) = o.package_description('bash')
        self.assert_('sh' in short.lower())
        self.assert_('shell' in long) 
        self.failIf('size:' in long) 
        self.assertRaises(ValueError, o.package_description, 'nonexisting')

        self.assertRaises(ValueError, o.package_files, 'nonexisting')
        coreutils_files = o.package_files('coreutils')
        self.assert_('/bin/cat' in coreutils_files)
        self.assert_('/bin/tail' in coreutils_files or 
            '/usr/bin/tail' in coreutils_files)

    def test_package_install(self):
        '''package installation/removal

        This will just do some very shallow tests if this is not run as root.
        '''
        # test package; this is most likely not installed yet (test suite will
        # abort if it is)
        test_package = 'lrzsz'

        # use real OSLib here, not test suite's fake implementation
        o = OSLib()

        self.assertRaises(ValueError, o.install_package, 'nonexisting', None)
        # this should not crash, since it is not installed
        o.remove_package('nonexisting', None)

        if os.getuid() != 0:
            return

        self.failIf(o.package_installed(test_package), 
            '%s must not be installed for this test' % test_package)

        # test without progress reporting
        o.install_package(test_package, None)
        self.assert_(o.package_installed(test_package))
        o.remove_package(test_package, None)
        self.failIf(o.package_installed(test_package))

    def test_has_repositories(self):
        '''has_repositories()

        This is only a shallow test that the function works. We assume that we
        have repositories in the test environment for now.
        '''
        o = OSLib()
        self.assertEqual(o.has_repositories(), True)

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_ssl_cert_file(self):
        '''ssl_cert_file()

        This uses a known-good URL from an Epson printer driver to ensure that
        the returned file contains useful certificates. Skipped if no
        SSL cert file is available.
        '''

        cert = OSLib().ssl_cert_file()
        if not cert:
            return self.skipTest('not available]')

        fp = jockey.detection.download_gpg_fingerprint(
                'https://linux.avasys.jp/drivers/lsb/epson-inkjet/key/fingerprint')
        self.assertNotEqual(fp, None)

    def test_import_gpg_key_valid(self):
        '''import_gpg_key() for valid fingerprint'''

        o = OSLib()
        o.gpg_key_server = 'localhost'
        self._start_keyserver()
        try:
            o.import_gpg_key(self.tempfile, test_gpg_fp)
        finally:
            self._stop_keyserver()
        self.assertEqual(o._gpg_keyring_fingerprints(self.tempfile),
                [test_gpg_fp])

    def test_import_gpg_key_invalid(self):
        '''import_gpg_key() for invalid fingerprint'''

        o = OSLib()
        o.gpg_key_server = 'localhost'
        self._start_keyserver()
        try:
            self.assertRaises(SystemError, o.import_gpg_key, self.tempfile,
                    test_gpg_fp.replace('4', '5')) 
        finally:
            self._stop_keyserver()

        self.assertEqual(o._gpg_keyring_fingerprints(self.tempfile), [])

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_import_gpg_key_multimatch(self):
        '''import_gpg_key() for multiple key ID matches'''

        o = OSLib()

        # there are two 0xDEADBEEF ID keys
        fp = '5425 931B 5B99 C58B 40BD  CE87 7AC1 3FB2 DEAD BEEF'
        o.import_gpg_key(self.tempfile, fp)
        self.assert_(fp in o._gpg_keyring_fingerprints(self.tempfile))

    def test_import_gpg_key_no_program(self):
        '''import_gpg_key() for unavailable gpg'''

        o = OSLib()
        orig_path = os.environ.get('PATH', '')
        try:
            os.environ['PATH'] = ''
            fp = '3BDC 0482 4EA8 1277 AE46  EA72 F988 25AC 26B4 7B9F'
            self.assertRaises(SystemError, o.import_gpg_key, self.tempfile, fp)
        finally:
            os.environ['PATH'] = orig_path
        self.assertEqual(o._gpg_keyring_fingerprints(self.tempfile), [])

    #
    # Helper methods
    #

    @classmethod
    def _start_keyserver(klass):
        '''Run a keyserver on localhost (just serves the test suite key).'''

        dir = os.path.join(OSLib.inst.workdir, 'pks')
        os.mkdir(dir, 0o700)
        # quiesce a message from gpg
        open(os.path.join(dir, 'secring.gpg'), 'w').close()
        lookup = open(os.path.join(dir, 'lookup'), 'w')
        assert subprocess.call(['gpg', '--homedir', dir, '--no-default-keyring',
            '--primary-keyring', os.path.join(os.path.dirname(__file__), 'data/pubring.gpg'),
            '--export', '-a'], stdout=lookup) == 0
        httpd.start(11371, OSLib.inst.workdir)

    @classmethod
    def _stop_keyserver(klass):
        '''Stop the keyserver.'''

        httpd.stop()
        shutil.rmtree(os.path.join(OSLib.inst.workdir, 'pks'))

