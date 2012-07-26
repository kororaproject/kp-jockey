# -*- coding: UTF-8 -*-
# (c) 2007 Canonical Ltd.
# (c) 2011 Chris Smart <chris@kororaa.org>
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

'''Encapsulate operations which are Linux distribution specific.'''

import fcntl, os, subprocess, sys, logging, re, tempfile, time, shutil
from glob import glob

import yum

class OSLib:
    '''Encapsulation of operating system/Linux distribution specific operations.'''

    # global default instance
    inst = None

    def __init__(self, client_only=False, target_kernel=None):
        '''Set default paths and load the module blacklist.
        
        Distributors might want to override some default paths.
        If client_only is True, this only initializes functionality which is
        needed by clients, and which can be done without special privileges.

        If target_kernel is given, it is used instead of the default
        os.uname()[2]. This is primarily useful for distribution installers
        where the target system kernel differs from the installer kernel.
        '''
        
        # create an instance of yum
        self._yum = yum.YumBase()
        
        # relevant stuff for clients and backend
        self._get_os_version()

        # /sys/ path; the main purpose of changing this is for test
        # suites, but some vendors might have /sys in a nonstandard place
        self.sys_dir = '/sys'

        if client_only:
            return

        # below follows stuff which is only necessary for the backend

        # default paths

        # path to a modprobe.d configuration file where kernel modules are
        # enabled and disabled with blacklisting
        self.module_blacklist_file = '/etc/modprobe.d/blacklist.conf'

        # path to modinfo binary
        self.modinfo_path = '/sbin/modinfo'

        # path to modprobe binary
        self.modprobe_path = '/sbin/modprobe'

        # path to kernel's list of loaded modules
        self.proc_modules = '/proc/modules'

        # default path to custom handlers
        self.handler_dir = '/usr/share/jockey/handlers'

        # default paths to modalias files (directory entries will consider all
        # files in them)
        self.modaliases = [
        #    '/lib/modules/%s/modules.alias' % os.uname()[2],
            '/usr/share/jockey/modaliases/',
        ]

        # path to X.org configuration file
        self.xorg_conf_path = '/etc/X11/xorg.conf'

        self.set_backup_dir()

        # cache file for previously seen/newly used handlers lists (for --check)
        self.check_cache = os.path.join(self.backup_dir, 'check')

        self._load_module_blacklist()

        # Possible paths of a file with a set of SSL certificates which are
        # considered trustworthy. The first one that exists will be used.
        # This is used for downloading GPG key fingerprints for
        # openprinting.org driver packages.
        self.ssl_cert_file_paths = [
                # Fedora use the ca-certificates package:
                '/etc/ssl/certs/ca-bundle.crt'
                ]

        # default GPG key server
        # this is the generally recommended DNS round-robin, but usually very
        # slow:
        #self.gpg_key_server = 'keys.gnupg.net'
        self.gpg_key_server = 'hkp://subkeys.pgp.net'

        if target_kernel:
            self.target_kernel = target_kernel
        else:
            self.target_kernel = os.uname()[2]

        # Package which provides include files for the currently running
        # kernel.  If the system ensures that kernel headers are always
        # available, or being pulled in via dependencies (and there are not
        # multiple kernel flavors), it is ok to set this to "None". This should
        # use self.target_kernel instead of os.uname()[2].
        self.kernel_header_package = None

    # 
    # The following package related functions use Yum; if that does not
    # work for your distribution, they must be reimplemented
    #

    def is_package_free(self, package):
        '''Return if given package is free software.'''

        pkg = self._yum.pkgSack.returnNewestByName(package)[0]
        license = pkg.returnSimple('license')
        if license:
            license.lower().startswith('gpl') or \
                license.lower() in ('free', 'bsd', 'mpl')
        else:
            raise ValueError('package %s does not exist' % package)

    def package_installed(self, package):
        '''Return if the given package is installed.'''
        return self._yum.isPackageInstalled(package)

    def package_description(self, package):
        '''Return a tuple (short_description, long_description) for a package.
        
        This should raise a ValueError if the package is not available.
        '''
        try:
            pkg = self._yum.pkgSack.returnNewestByName(package)[0]
            return (pkg.returnSimple('summary'), pkg.returnSimple('description'))
        except yum.Errors.PackageSackError:
            raise ValueError('package %s does not exist' % package)

    def package_files(self, package):
        '''Return a list of files shipped by a package.
        
        This should raise a ValueError if the package is not installed.
        '''
        try:
            pkg = self._yum.rpmdb.returnNewestByName(package)[0]
            return pkg.filelist
        except yum.Errors.PackageSackError:
            raise ValueError('package %s is not installed' % package)

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
        should be raised as a SystemError.
        '''
        if repository or fingerprint:
            raise NotImplementedError('Yum default implementation does not currently support repositories or fingerprints')

        # this will check if the package exists
        self.package_description(package)
        
        try:
            pkg = self._yum.pkgSack.returnNewestByName(package)[0]
            self._yum.install(pkg)
            self._yum.buildTransaction()
            self._yum.processTransaction()
        except Exception, error:
            raise SystemError('package %s failed to install: %s' % (package, error))
            
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
        try:
            pkg = self._yum.rpmdb.returnNewestByName(package)[0]
            self._yum.remove(pkg)
            self._yum.buildTransaction()
            self._yum.processTransaction()
        except Exception, error:
            raise SystemError('package %s failed to remove: %s' % (package, error))

    def has_repositories(self):
        '''Check if package repositories are available.

        This might not be the case after a fresh installation, when package
        indexes haven't been downloaded yet.
        '''
        return bool(self._yum.repos.listEnabled())

    def update_repository_indexes(self, progress_cb):
        '''Download package repository indexes.

        Return True on success, False otherwise.

        As this is called in the backend, this must happen noninteractively.
        For progress reporting, progress_cb(current, total) is called
        regularly. Passes '-1' for current and/or total if time cannot be
        determined.
        '''
        result = False
        try:
            self._yum.repos.populateSack('all', 'metadata')
            result = self.has_repositories()
        except Errors.RepoError:
            pass
        return result

    def packaging_system(self):
        '''Return packaging system.

        Currently defined values: apt, yum
        '''
        if os.path.exists('/etc/yum.conf'):
            return 'yum'
        elif os.path.exists('/etc/apt/sources.list') or \
            os.path.exists('/etc/apt/sources.list.d'):
            return 'apt'

        raise NotImplementedError('local packaging system is unknown')

    def import_gpg_key(self, keyring, fingerprint):
        '''Download and install a GPG key identified by fingerprint.

        This verifies that the fingerprint matches, and if so, installs it into
        the given keyring file (will be created if it does not exist).

        Raise a SystemError if anything goes wrong.
        '''
        if fingerprint in self._gpg_keyring_fingerprints(keyring):
            return

        # gpg likes to write trustdb and temporary files, so create a temporary
        # home directory
        keyid = fingerprint.replace(' ', '')[-8:]
        gpghome = tempfile.mkdtemp()
        default_keyring = os.path.join(gpghome, 'pubring.gpg')
        try:
            # we first import into a temporary keyring, as we need to verify
            # the fingerprint
            gpg = subprocess.Popen(['gpg', '--homedir', gpghome,
                '--no-default-keyring', '--primary-keyring', default_keyring,
                '--keyserver', self.gpg_key_server, '--recv-key', keyid], 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                env={'PATH': os.environ.get('PATH', ''), 
                     'http_proxy': os.environ.get('http_proxy', '')})
            (out, err) = gpg.communicate()

            if fingerprint not in self._gpg_keyring_fingerprints(default_keyring):
                raise SystemError('gpg failed to import key: ' + err)

            # now move over to the actual keyring; for multiple matches of the
            # same key ID it would be great to be able to select the one that
            # we want, but unfortunately the GPG command line doesn't really
            # allow that; fortunately key ID conflicts are very rare.
            gpg = subprocess.Popen(['gpg', '--homedir', gpghome,
                '--no-default-keyring', '--primary-keyring', keyring,
                '--import', default_keyring], 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={'PATH': os.environ.get('PATH', '')})
            (out, err) = gpg.communicate()

            if fingerprint not in self._gpg_keyring_fingerprints(default_keyring):
                raise SystemError('gpg failed to import key: ' + err)

            logging.debug('import_gpg_key(): Successfully imported key' + keyid)
        except OSError as e:
            raise SystemError('failed to call gpg: ' + str(e))
        finally:
            shutil.rmtree(gpghome)

    def _gpg_keyring_fingerprints(self, keyring):
        '''Return list of fingerprints in given keyring'''

        # gpg likes to write trustdb and temporary files, so create a temporary
        # home directory
        gpghome = tempfile.mkdtemp()
        try:
            result = []
            gpg = subprocess.Popen(['gpg', '--homedir', gpghome,
                '--no-default-keyring', '--primary-keyring', keyring,
                '--fingerprint'], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env={})
            (out, err) = gpg.communicate()
            if gpg.returncode != 0:
                logging.error('failed to call gpg for reading fingerprints: ' + err)
                return []

            for l in out.splitlines():
                if 'fingerprint =' in l:
                    result.append(l.split('=')[1].strip())
            return result
        except OSError as e:
            logging.error('failed to call gpg: ' + str(e))
            return []
        finally:
            shutil.rmtree(gpghome)

    # 
    # The following functions MUST be implemented by distributors
    # Note that apt and yum PackageKit backends currently do not implement
    # RepoSetData(), so those need to remain package system specific
    #

    def repository_enabled(self, repository):
        '''Check if given repository is enabled.'''
        return repository in [repo.id for repo in self._yum.repos.listEnabled()]

    def ui_help_available(self, ui):
        '''Return if help is available.

        This gets the current UI object passed, which can be used to determine
        whether GTK/KDE is used, etc.
        '''
        return False

    def ui_help(self, ui):
        '''The UI's help button was clicked.

        This should open a help HTML page or website, call yelp with an
        appropriate topic, etc. This gets the current UI object passed, which
        can be used to determine whether GTK/KDE is used, etc.
        '''
        pass

    # 
    # The following functions have a reasonable default implementation for
    # Linux, but can be tweaked by distributors
    #

    def set_backup_dir(self):
        '''Setup self.backup_dir, directory where backup files are stored.
        
        This is used for old xorg.conf, DriverDB caches, etc.
        '''
        self.backup_dir = '/var/cache/jockey'
        if not os.path.isdir(self.backup_dir):
            try:
                os.makedirs(self.backup_dir)
            except OSError as e:
                logging.error('Could not create %s: %s, using temporary '
                    'directory; all your caches will be lost!',
                    self.backup_dir, str(e))
                self.backup_dir = tempfile.mkdtemp(prefix='jockey_cache')

    def ignored_modules(self):
        '''Return a set of kernel modules which should be ignored.

        This particularly effects free kernel modules which are shipped by the
        OS vendor by default, and thus should not be controlled with this
        program.  Since this will include the large majority of existing kernel
        modules, implementing this is also important for speed reasons; without
        it, detecting existing modules will take quite long.
        
        Note that modules which are ignored here, but covered by a custom
        handler will still be considered.
        '''
        return set()

    def module_blacklisted(self, module):
        '''Check if a module is on the modprobe blacklist.'''

        return module in self._module_blacklist or \
            module in self._module_blacklist_system

    def blacklist_module(self, module, blacklist):
        '''Add or remove a kernel module from the modprobe blacklist.
        
        If blacklist is True, the module is blacklisted, otherwise it is
        removed from the blacklist.
        '''
        if blacklist:
            self._module_blacklist.add(module)
        else:
            try:
                self._module_blacklist.remove(module)
            except KeyError:
                return # no need to save the blacklist

        self._save_module_blacklist()

    def _load_module_blacklist(self):
        '''Initialize self._module_blacklist{,_system}.'''

        self._module_blacklist = set()
        self._module_blacklist_system = set()

        self._read_blacklist_file(self.module_blacklist_file, self._module_blacklist)

        # read other blacklist files (which we will not touch, but evaluate)
        for f in glob('%s/blacklist*' % os.path.dirname(self.module_blacklist_file)):
            if f != self.module_blacklist_file:
                self._read_blacklist_file(f, self._module_blacklist_system)

    @classmethod
    def _read_blacklist_file(klass, path, blacklist_set):
        '''Read a blacklist file and add modules to blacklist_set.'''

        try:
            f = open(path)
        except IOError:
            return

        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            for line in f:
                # strip off comments
                line = line[:line.find('#')].strip()

                if not line.startswith('blacklist'):
                    continue

                module = line[len('blacklist'):].strip()
                if module:
                    blacklist_set.add(module)
        finally:
            f.close()

    def _save_module_blacklist(self):
        '''Save module blacklist.'''

        if len(self._module_blacklist) == 0 and \
            os.path.exists(self.module_blacklist_file):
                os.unlink(self.module_blacklist_file)
                return

        os.umask(0o22)
        # create directory if it does not exist
        d = os.path.dirname(self.module_blacklist_file)
        if not os.path.exists(d):
            os.makedirs(d)

        f = open(self.module_blacklist_file, 'w')
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            for module in sorted(self._module_blacklist):
                print >> f, 'blacklist', module
        finally:
            f.close()

    def _get_os_version(self):
        '''Initialize self.os_vendor and self.os_version.

        This defaults to reading the values from lsb_release.
        '''
        p = subprocess.Popen(['lsb_release', '-si'], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=True)
        self.os_vendor = p.communicate()[0].strip()
        p = subprocess.Popen(['lsb_release', '-sr'], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=True)
        self.os_version = p.communicate()[0].strip()
        assert p.returncode == 0

    def get_system_vendor_product(self):
        '''Return (vendor, product) of the system hardware.

        Either or both can be '' if they cannot be determined.

        The default implementation queries sysfs.
        '''
        try:
            vendor = open(os.path.join(self.sys_dir,
                'class', 'dmi', 'id', 'sys_vendor')).read().strip()
        except IOError:
            vendor = ''

        try:
            product = open(os.path.join(self.sys_dir,
                'class', 'dmi', 'id', 'product_name')).read().strip()
        except IOError:
            product = ''

        return (vendor, product)

    def notify_reboot_required(self):
        '''Notify the system that a reboot is required.

        This can be used as an extra indication when installing a driver which
        needs a reboot to get active.

        The default implementation does nothing.
        '''
        pass

    def package_header_modaliases(self):
        '''Get modalias map from package headers.

        Driver packages may declare the modaliases that they support in a
        package header field, so that they do not need to have a separate
        modalias file list already installed. The map must have the following
        structure: package_name -> module_name -> [list of modaliases]

        If this is not supported, simply return an empty dictionary here.
        '''
        return {}

    def ssl_cert_file(self):
        '''Get file with trusted SSL certificates.
        
        This is used for downloading GPG key fingerprints for
        openprinting.org driver packages.

        Return None if no certificates file is available.
        '''
        for f in self.ssl_cert_file_paths:
            if os.path.exists(f):
                return f

        return None

    @classmethod
    def has_defaultroute(klass):
        '''Return if there is a default route.

        This is a reasonable indicator that online tests can be run.
        '''
        if klass._has_defaultroute_cache is None:
            klass._has_defaultroute_cache = False
            route = subprocess.Popen(['/sbin/route', '-n'],
                stdout=subprocess.PIPE)
            for l in route.stdout:
                if l.startswith('0.0.0.0 '):
                    klass._has_defaultroute_cache = True
            route.wait()

        return klass._has_defaultroute_cache

    _has_defaultroute_cache = None

    def current_xorg_video_abi(self):
        '''Return current X.org video ABI.

        For an X.org video driver to actually work it must be built against the
        currently used X.org driver ABI, otherwise it will cause crashes. This
        method returns the currently expected video driver ABI from the X
        server. If it is not None, it must match video_driver_abi() of a driver
        package for this driver to be offered for installation.
        
        If this returns None, ABI checking is disabled.
        '''
        return None

    def video_driver_abi(self, package):
        '''Return video ABI for an X.org driver package.

        For an X.org video driver to actually work it must be built against the
        currently used X.org driver ABI, otherwise it will cause crashes. This
        method returns the video ABI for a driver package. If it is not None,
        it must match current_xorg_video_abi() for this driver to be offered
        for installation.
        
        If this returns None, ABI checking is disabled.
        '''
        return None
