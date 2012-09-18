Jockey driver manager
=====================

Jockey provides the infrastructure and the user interface for finding
and installing third-party drivers which are applicable to the
computer. This includes drivers which are added or updated after the
release of a distribution, or drivers which cannot be included into
the distribution for various reasons (CD space limitation, licensing
problems, etc.). 

A common use case is providing a friendly and semiautomatic way to
install drivers for new hardware which the current distribution
release does not support yet, or install Nvidia and ATI fglrx X.org
drivers.

Jockey was designed to be distribution agnostic and fulfill the need
of different distributions, driver vendors, and system integrators. It
is designed and developed within the LinuxFoundation driver backports
workgroup [1].

Operation
---------

At startup, the Jockey backend probes the system for available
hardware. This can happen in various ways, currently implemented is
scanning /sys for modaliases. In the future it is planned to add more
methods, such as querying cups for detected printers which do not have
a driver.  Detection methods will be added as needed by component
vendors and distributions. The set of available hardware is
represented as "HardwareID" objects (which can represent anything that
uniquely identifies a piece of hardware, such as a vendor/product ID,
a modalias, or a printer identification string).

For each hardware ID, a set of driver databases (instances of
DriverDB) are queried for available drivers. At the moment, the only
existing implementation is LocalKernelModulesDriverDB, which uses the
standard Linux kernel modules.alias maps to map modaliases to
kernel modules. In the near future we plan to add another
implementation which queries an online driver database as well.
The DriverDBs transform the set of HardwareIDs to a set of DriverIDs.

A DriverID represents all necessary metadata about a driver, such as:

 * driver class (kernel module, printer driver, package, X.org
   graphics driver, firmware, etc.)
 * handler class name (see below)
 * location of the driver (repository, package name, possibly sha1 and
   other checksums, signatures)
 * driver specific parameters (arbitrary type/value pairs which the
   handler understands)

All drivers handled by Jockey need to be encapsulated by a subclass of
"Handler". A handler instance provides a hook for arbitrary code which
needs to run in order to fully install a driver. Jockey already
provides handler implementations for common cases such as kernel
modules, kernel module firmware, X.org driver, groups of drivers, etc.
The vast majority of drivers will use parameterized instances of these
default handlers, but drivers which need some more sophisticated
local configuration can ship their own handler subclass and add the
necessary code.

Auto-install mode
-----------------

For integration into installers or for OEMs, handlers can be marked for
automatic installation. When calling Jockey with --auto-install, these marked
handlers will be automatically installed if they are applicable to the system.
The --list option will show which drivers are configured for this.

This can happen by setting a handler's "self._auto_install = True" attribute in
the code, but the preferred way is to create a flag file
/usr/share/jockey/handlers/autoinstall.d/<id>, where <id> is the driver ID
shown by --list (for example, "xorg:fglrx" or "kmod:wl").

Structure
---------

The bulk of Jockey's work (hardware detection, driver database
queries, package installation, etc.) is done by an UI independent
backend which provides its functionality over the system D-BUS. Access
is controlled by PolicyKit privileges (see
backend/com.ubuntu.devicedriver.policy.in for details); by default,
all users can do local device driver status queries, all local users
can trigger a remote driver database query, and actually
installing/removing drivers is restricted to system administrators.

The different user interfaces (GTK, and KDE, and both provide a CLI as
well) run with normal user privileges and just provide a human
friendly and internationalized presentation/UI of the backend
services. They do not contain any driver logic.

Adapting Jockey to a Linux distribution
---------------------------------------

Jockey is carefully written to not be specific to any Linux
distribution. All OS/distro specific operations are encapsulated in
the "OSLib" class, which needs to be subclassed and implemented by the
Linux distributions. Most methods already have a reasonable default
implementation upstream, but some are just inherently distro specific
(search for "NotImplementedError" to find those).

This minimizes the porting efforts of distributors while retaining the
possibility to make adjustments in one central place.

The abstract OSLib class is thoroughly documented, and there already
exists a branch for Ubuntu[3], and the test suite has a dummy
implementation (see tests/sandbox.py). These should suffice to
implement Jockey for other distributions as well.

Dependencies
------------

Jockey needs a working Python installation, and the following Python
modules:

 - dbus-python for providing the D-BUS service for enquiring
   and requesting drivers. Latest release is available at
   http://dbus.freedesktop.org/releases/dbus-python/ . dbus-python
   itself depends on pygobject, which can be downloaded from
   http://ftp.gnome.org/pub/GNOME/sources/pygobject/ .

 - pyxdg: http://freedesktop.org/wiki/Software/pyxdg

 - X-Kit for X.org driver handler for parsing and changing xorg.conf.
   Releases available at https://launchpad.net/xorgparser/+download , or check
   out latest trunk with "bzr get lp:xorgparser".
   
 - DistUtilsExtra for running setup.py (which will care about
   building, merging, and installing gettext .po files, installing
   icons, etc.): Latest tarball can be downloaded from
   https://launchpad.net/python-distutils-extra/+download .
   Note that this is not necessary for running Jockey from the source
   tree.

 - pycurl for fetching and verifying GPG fingerprints from vendor https sites.
   Latest releases can be downloaded from http://pycurl.sourceforge.net .

 - polkit-1. The latest release is available at
   http://hal.freedesktop.org/releases/

 - If you want to run the frontend as normal user, you also need a
   PolicyKit authentication agent for your desktop environment. You need
   PolicyKit-GNOME (available at the same URL) for GNOME, a KDE frontend is
   available at ftp://ftp.kde.org/pub/kde/stable/apps/KDE4.x/admin/

   Alternatively, you can change the .desktop files to run them as root (e. g.
   add "X-KDE-SubstituteUID=true" to the KDE one).

 - If you want to use the default upstream implementation of the
   package handling methods in OSLib, you need PackageKit (tested with
   >= 0.2.2). The latest release is available at
   http://www.packagekit.org/releases/
   If your distribution does not work with PackageKit, you need to
   provide your own implementation in OSLib.

For the GTK frontend, you need the GIR typelibs for GLib, GdkPixbuf, Gtk, and
Notify, and optionally AppIndicator.

For the KDE frontend, you need

 - PyQt4: http://www.riverbankcomputing.co.uk/pyqt/index.php

 - PyKDE4 from the kdebindings KDE component

Trying it
---------

As written above, Jockey provides mostly infrastructure. Without an
implementation for a particular distribution and without actual
drivers it is fairly useless. However, you can get a first impression
by installing the upstream version.

 1. Run "./setup.py build" (as normal user) for running the i18n magic
    and to build the PolicyKit .policy file.

 2. Running the backend on the system D-BUS requires at least the
    D-BUS .conf and Policykit .policy files to be installed, so the
    easiest way is to install the package:

    # ./setup.py install --record jockey.files

    (as root).

Then you can run either "jockey-gtk" or "jockey-kde" to spawn the GUI.
See --help for information how to run it in particular modes, or how
to use it in command line mode.
 
This will bring up the UI and list all standard kernel modules which
are tied to hardware. (Note that you will *not* see all this stuff in
a proper distribution implementation, of course.) Disabling and
enabling kernel modules will work, it cause them to get
(un)blacklisted. Make sure to not render your system unbootable that
way :-) .

Normal the backend is started automatically via D-BUS activation.
For debugging you can also start it on a shell with debugging enabled:

  # /usr/share/jockey/jockey-backend --debug

for some insight of how Jockey detects hardware and which
kernel modules are responsible for driving it.

If you want to uninstall again, use the --record file created with
install:

  # xargs rm < jockey.files
  # xargs rmdir -p < jockey.files

Testing drivers without hardware
--------------------------------

If you do not actually have hardware which needs third-party drivers, you can
create a "match-all" fake modalias file for all the drivers you want to test.
Have a look at examples/fake.modaliases how this looks like.

Just copy that to /usr/share/jockey/modaliases/fake and restart jockey.

D-BUS interface
---------------

Jockey provides two different D-DBUS interfaces. One is on the system
bus and provides access to the Jockey backend, which needs root
privileges. This is used by the various Jockey frontends (GTK, KDE,
command line), but can of course be used independently by other
applications. Please see jockey/backend.py, all functions marked with
"@dbus.service.method", for a detailled interface documentation.

The single most interesting request that other applications have is "I
have this device, and need a driver". This requires a graphical user
interface for allowing the user to confirm installation, and present
progress dialogs, etc. Thus Jockey offers a D-BUS interface on the
session as well, which provides this feature in a convenient way:

  bus: com.ubuntu.DeviceDriver
  object path: /GUI
  interface: com.ubuntu.DeviceDriver
  method: search_driver(hardware_id)

This method takes a single string, a "Hardware ID" (see above).

Example:

   dbus-send --print-reply --dest=com.ubuntu.DeviceDriver /GUI \
      com.ubuntu.DeviceDriver.search_driver \
      string:"printer_deviceid:MFG:Hewlett-Packard;MDL:HP DesignJet 3500CP"
  
This will search local and remote driver databases (such as
openprinting.org) for a matching driver, and if it finds one which is
not installed yet, present the details of that driver, ask for
confirmation, and install it.

This returns a pair (success, files); where 'success' is True if a
driver was found, acknowledged by the user, and installed, otherwise
False; "files" is the list of files shipped by the newly installed
packages (useful for e. g. printer drivers to get a list of PPDs to
check).

Test suite
----------

Every new feature and bug fix should first get a test case, to
maintain nearly 100% code coverage. tests/sandbox.py provides fake
implemetations of OSLib, a fake /sys tree, modinfo, etc., so that the
entire hardware detection and handler system can be automatically
tested independent of the actual hardware Jockey runs on, as well as
being independent of a concrete OSLib implementation.

To run it, simply do

 tests/run 

The graphical UIs have separate test scripts, since they might not
work in all cases (like running them automatically during package
build):

  tests/run-gtk
  tests/run-qt

A commit to trunk must only be done if all test suites succeed.

Please note that the tests do not depend on the system D-BUS or
installation of any files. They will spawn their own local test
backend on the session D-BUS.

Development
-----------

Development of trunk and the Ubuntu implementation happens on the
"jockey" Launchpad project: 

  https://launchpad.net/jockey
  
This is the place to report bugs, do translations, hosting your own
branches (if you wish to do so), and download upstream releases.

References
----------

[1] http://www.linux-foundation.org/en/Driver_Backport
[2] https://code.launchpad.net/~jockey-hackers/jockey/trunk
[3] https://code.launchpad.net/~ubuntu-core-dev/jockey/ubuntu

Martin Pitt <martin.pitt@ubuntu.com>
