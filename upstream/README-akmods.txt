Jockey driver manager akmod support
===================================

To install an outside of the kernel driver we normally install a kmod
package, which delivers the module for a specific kernel. That kmod
package will not work on other versions (including minor ones) of the
kernel.

An alternative to kmods are akmods, which are automatic kernel modules
that the system builds on boot. To use akmods, one must have several
build tools, such as gcc, installed on the machine as well as the
kernel headers to compile against.

By default Jockey uses kmod packages, however it does also support
the use of akmods if configured. The jockey-akmods meta-package will
pull in all the required packages and also sets the jockey.conf file
to use akmods, so a user need only install this package to ensure they
have full support for akmods.

With akmod support, when jockey is run it will install akmod driver
packages (suchas akmod-nvidia) from rpmfusion rather than the regular
kmod. The akmod service will build the package each time the system is
booted if a driver does not exist for the running kernel.

This is preferable on many systems because often Fedora will release a
new kernel, but there is not yet a kmod package for it. In such cases
system updates may fail, and a user may be running a vulnerable kernel
for as long as it takes for an updated kmod package to be created.
