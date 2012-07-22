# -*- coding: UTF-8 -*-
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

'''Encapsulate operations which are Linux distribution specific.'''

import fcntl, os, subprocess, sys, logging, re, tempfile, time, shutil
from glob import glob

# global variables
akmods_enabled = False

class OSLib:
    '''Encapsulation of operating system/Linux distribution specific operations.'''

    # global default instance
    inst = None

    global akmods_enabled
    #logging.debug('class akmod status: %s', akmods_enabled)
    print("class akmod status: %s" % akmods_enabled)

    def __init__(self, client_only=False, target_kernel=None):
        '''Set default paths and load the module blacklist.

        Distributors might want to override some default paths.
        If client_only is True, this only initializes functionality which is
        needed by clients, and which can be done without special privileges.

        If target_kernel is given, it is used instead of the default
        os.uname()[2]. This is primarily useful for distribution installers
        where the target system kernel differs from the installer kernel.
        '''

        global akmods_enabled
        logging.debug('init akmod status pre-config: %s', akmods_enabled)

        self.remove_pkg_queue = set()

        # relevant stuff for clients and backend
        self._get_os_version()

        # location of config file
        self.config_file = '/etc/jockey.conf'

        # /sys/ path; the main purpose of changing this is for test
        # suites, but some vendors might have /sys in a nonstandard place
        self.sys_dir = '/sys'

        if client_only:
            return

        # below follows stuff which is only necessary for the backend

        # default paths

        # path to a modprobe.d configuration file where kernel modules are
        # enabled and disabled with blacklisting
        self.module_blacklist_file = '/etc/modprobe.d/blacklist-local.conf'

        # path to modinfo binary
        self.modinfo_path = '/sbin/modinfo'

        # path to modprobe binary
        self.modprobe_path = '/sbin/modprobe'

        # path to kernel's list of loaded modules
        self.proc_modules = '/proc/modules'

        # default path to custom handlers
        self.handler_dir = '/usr/share/jockey/handlers'

        if target_kernel:
            self.target_kernel = target_kernel
        else:
            self.target_kernel = os.uname()[2]

        # default paths to modalias files (directory entries will consider all
        # files in them)

        # set akmod support to disabled by default, enabled below after reading config file
        #self.akmods_enabled = False

        # Enable akmods if set in config, else check PAE, fallback to kmod
        conf_file = open(self.config_file)

        for line in conf_file:
            if "akmods=true" in line.lower():
                alias_dir = '-akmods'
                akmods_enabled = True
            elif re.search('.*PAE.*', self.target_kernel):
                alias_dir = '-PAE'
            else:
                alias_dir = ''

        conf_file.close()

        logging.debug('init akmod status post-config: %s', akmods_enabled)

        self.modaliases = [
            '/usr/share/jockey/modaliases%s/' % alias_dir,
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
                # Debian/Ubuntu use the ca-certificates package:
                '/etc/ssl/certs/ca-certificates.crt'
                ]

        # default GPG key server
        # this is the generally recommended DNS round-robin, but usually very
        # slow:
        #self.gpg_key_server = 'keys.gnupg.net'
        self.gpg_key_server = 'hkp://keyserver.ubuntu.com:80'

        # Package which provides include files for the currently running
        # kernel.  If the system ensures that kernel headers are always
        # available, or being pulled in via dependencies (and there are not
        # multiple kernel flavors), it is ok to set this to "None". This should
        # use self.target_kernel instead of os.uname()[2].
        self.kernel_header_package = None

    #
    # The following functions are Fedora specific
    #

    def build_kmod(self, progress_cb, phase):
        '''Build kmod package.'''

        phase = phase
        err = ''

        progress_cb(phase, -1, -1)

        logging.debug('\n\n\nbuild_kmod\n\n\n')
        time.sleep(30)

        kernel_version = os.uname()[2]
        akmods = subprocess.Popen(['/usr/sbin/akmods', '--kernels', kernel_version],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        err += akmods.stderr.read()

        if akmods.wait() != 0:
            logging.error('Failed to build kmod: %s' % (err))
        else:
            logging.debug('Successfully built kmod for kernel %s' % kernel_version)


    def rebuild_initramfs(self, progress_cb, phase):
        '''Rebuild the initramfs.'''

        phase = phase
        err = ''

        if progress_cb and phase == "remove":
            progress_cb(-1, -1)
        else:
            progress_cb(phase, -1, -1)

        logging.debug('\n\n\nbuild_initramfs\n\n\n')
        time.sleep(30)

        dracut = subprocess.Popen(['/sbin/dracut', '--force', '-v'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        err += dracut.stderr.read()

        if dracut.wait() != 0:
            logging.error('Failed to rebuild initramfs: %s' % (err))
        else:
            logging.debug('Successfully rebuilt initramfs')

    #
    # The following package related functions use PackageKit; if that does not
    # work for your distribution, they must be reimplemented
    #

    def is_package_free(self, package):
        '''Return if given package is free software.'''

        pkcon = subprocess.Popen(['pkcon', '--filter=newest',
            'get-details', package], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # we send an "1" to select package if several versions
        # are available (--filter is broken in at least Fedora 10)
        out = pkcon.communicate('1\n')[0]
        m = re.search("^\s*license:\s*'?(.*)'?$", out, re.M)
        if m:
            # TODO: check more licenses here
            return m.group(1).lower().startswith('gpl') or \
                m.group(1).lower() in ('free', 'bsd', 'mpl')
        else:
            raise ValueError('package %s does not exist' % package)

    def package_installed(self, package):
        '''Return if the given package is installed.'''

        pkcon = subprocess.Popen(['pkcon', 'resolve', package],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = pkcon.communicate()[0]
        return pkcon.returncode == 0 and '\ninstalled ' in out.lower()

    def package_description(self, package):
        '''Return a tuple (short_description, long_description) for a package.

        This should raise a ValueError if the package is not available.
        '''
        pkcon = subprocess.Popen(['pkcon', '--filter=newest',
            'get-details', package], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # we send an "1" to select package if several versions
        # are available (--filter is broken in at least Fedora 10)
        out = pkcon.communicate('1\n')[0]
        m = re.search("^\s*description:\s*'?(.*?)'?^\s+", out, re.M | re.S)
        if m:
            # TODO: short description (not accessible with pkcon)
            return (package, m.group(1).replace('\n', ''))
        else:
            raise ValueError('package %s does not exist' % package)

    def package_files(self, package):
        '''Return a list of files shipped by a package.

        This should raise a ValueError if the package is not installed.
        '''
        pkcon = subprocess.Popen(['pkcon', '--filter=installed',
            'get-files', package], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # we send an "1" to select package if several versions
        # are available (--filter is broken in at least Fedora 10)
        out = pkcon.communicate('1\n')[0]
        if pkcon.returncode == 0 and '\n  ' in out:
            return [l.strip() for l in out.splitlines() if l.startswith('  ')]
        else:
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
        due to bad packages should be logged, but not raise an exception, as
        this would just crash the backend.
        '''

        global akmods_enabled
        logging.debug('install_package akmod status: %s', akmods_enabled)
        print("install_package akmod status: %s" % akmods_enabled)

        if repository or fingerprint:
            raise NotImplementedError('PackageKit default implementation does not currently support repositories or fingerprints')

        # this will check if the package exists
        self.package_description(package)

        pkcon = subprocess.Popen(['pkcon', 'install', '--plain', '-y', package],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        # we send an "1" to select package if several versions
        # are available
        print >>pkcon.stdin, "1\n"

        re_progress = re.compile('Percentage:\t(\d+)')

        phase = None
        err = line = ''
        fail = False
        while pkcon.poll() == None or line != '':
            line = pkcon.stdout.readline()
            if fail:
                err += line
            if 'Downloading packages' in line:
                phase = 'download'
            elif 'Testing changes' in line or 'Installing packages' in line:
                phase = 'install'
            elif progress_cb and 'Percentage' in line:
                m = re_progress.search(line)
                if m and phase:
                    progress_cb(phase, int(m.group(1)), 100)
                else:
                    progress_cb(phase or 'download', -1, -1)
            elif 'WARNING' in line:
                fail = True
            elif 'transaction-error' in line or 'failed:' in line:
                err += line

        err += pkcon.stderr.read()
        if pkcon.wait() != 0 or not self.package_installed(package):
            logging.error('package %s failed to install: %s' % (package, err))


        if akmods_enabled:
          self.build_kmod(progress_cb, phase)

        self.rebuild_initramfs(progress_cb, phase)

    def queue_packages_for_removal(self, packages):
        self.remove_pkg_queue.update(packages)

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
        progress_cb(0, 100)
        pkcon = subprocess.Popen(['pkcon', '--plain', '--filter=installed',
                                  'search', 'name', package],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        re_packages = re.compile("Installed\s+([\w:.-]+)-([\w:.]+)-([\w:.]+)")

        driver_packages = { package }
        driver_packages.update(self.remove_pkg_queue)
        self.remove_pkg_queue.clear()

        err = line = ''
        fail = False
        while pkcon.poll() == None or line != '':
            line = pkcon.stdout.readline()
            if fail:
                err += line
            if 'Installed' in line:
                m = re_packages.search(line)
                if m:
                    driver_packages.add(m.group(1))
                else:
                    logging.error('Cannot extract the package name from %s' % line)
            elif 'WARNING' in line:
                fail = True
            elif 'transaction-error' in line or 'failed:' in line:
                err += line

        err += pkcon.stderr.read()
        pkcon.wait()

        progress_start = 100
        progress_total = 100 + 100 * len(driver_packages)

        logging.debug('Removing packages: %s' % driver_packages)
        for pkg in driver_packages:
            progress_cb(progress_start, progress_total)
            self.remove_single_package(pkg, progress_cb, progress_start,
                progress_total)
            progress_start += 100

        if self.package_installed(package):
            raise SystemError('package %s failed to remove: %s' % (package, err))

        self.rebuild_initramfs(progress_cb, "remove")

    def remove_single_package(self, package, progress_cb, progress_start,
                              progress_total):
        '''Uninstall the given package.

        As this is called in the backend, this must happen noninteractively.
        For progress reporting, progress_cb(current, total) is called
        regularly. Passes progress_start for current and/or progress_total
        for total if time cannot be determined.

        If this succeeds, subsequent package_installed(package) calls must
        return False.

        Any removal failure should be raised as a SystemError.
        '''
        pkcon = subprocess.Popen(['pkcon', 'remove', '--plain', '-y', package],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        re_progress = re.compile('Percentage:\t(\d+)')

        err = line = ''
        fail = False
        while pkcon.poll() == None or line != '':
            line = pkcon.stdout.readline()
            if fail:
                err += line
            elif progress_cb and 'Percentage' in line:
                m = re_progress.search(line)
                if m:
                    progress_cb(progress_start + int(m.group(1)), progress_total)
                else:
                    progress_cb(progress_start, progress_total)
            elif 'WARNING' in line:
                fail = True
            elif 'transaction-error' in line or 'failed:' in line:
                err += line

        err += pkcon.stderr.read()
        pkcon.wait()
        if self.package_installed(package):
            raise SystemError('package %s failed to remove: %s' % (package, err))

    def has_repositories(self):
        '''Check if package repositories are available.

        This might not be the case after a fresh installation, when package
        indexes haven't been downloaded yet.
        '''
        pkcon = subprocess.Popen(['pkcon', 'get-details', 'bash'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = pkcon.communicate()[0]
        # PK can't detect package sizes without repositories
        m = re.search("^\s*size:\s*0 bytes$", out, re.M)
        return m == None

    def update_repository_indexes(self, progress_cb):
        '''Download package repository indexes.

        Return True on success, False otherwise.

        As this is called in the backend, this must happen noninteractively.
        For progress reporting, progress_cb(current, total) is called
        regularly. Passes '-1' for current and/or total if time cannot be
        determined.
        '''
        pkcon = subprocess.Popen(['pkcon', 'refresh'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        while pkcon.poll() == None:
            time.sleep(0.3)
            if progress_cb:
                progress_cb(-1, -1)
        pkcon.wait()
        return self.has_repositories()

    def packaging_system(self):
        '''Return packaging system.

        Currently defined values: apt, yum
        '''
        if os.path.exists('/etc/apt/sources.list') or os.path.exists(
            '/etc/apt/sources.list.d'):
            return 'apt'
        elif os.path.exists('/etc/yum.conf'):
            return 'yum'

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

        raise NotImplementedError('subclasses need to implement this')

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

        f = None
        try:
            f = open(self.module_blacklist_file, 'w')
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            for module in sorted(self._module_blacklist):
                print >> f, 'blacklist', module
        except IOError as e:
            logging.error('Failed to write to module blacklist: ' + str(e))
        finally:
            if f:
                f.close()

    def _get_os_version(self):
        '''Initialize self.os_vendor and self.os_version.
        '''
        re_distinfo = re.compile('(\w+) release ([\d.]+) \((\w+)\)')
        release_file = open('/etc/system-release')
        dinfo_line = release_file.readline()
        distinfo = re_distinfo.search(dinfo_line)
        if distinfo:
            self.os_vendor = distinfo.group(1)
            self.os_version = distinfo.group(2)
        else:
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
