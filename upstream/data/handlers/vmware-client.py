# (c) 2009, 2011 Canonical Ltd.
# Author: Martin Owens <doctormo@ubuntu.com>
# License: GPL v2 or later
# Adopted for Fedora: Hedayat Vatankhah <hedayat.fwd@gmail.com>

from jockey.handlers import Handler, KernelModuleHandler
from jockey.oslib import OSLib

# dummy stub for xgettext
def _(x): return x

class VmwareClientHandler(KernelModuleHandler):
    '''Handler for the VMWARE client tools.
    '''
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'vmxnet',
                name=_('VMWare Client Tools'),
                description=_('Install VMWare client drivers and tools'),
                rationale=_('Install the VMWare client drivers'
                    'for your VMWare based {0} installation.\n\n'
                    'This should help you use {0} in your VM.').format(OSLib.inst.os_vendor))

    def id(self):
        '''Return an unique identifier of the handler.'''
        return 'vm:' + self.module

