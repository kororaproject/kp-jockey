# (c) 2009, 2011 Canonical Ltd.
# Author: Martin Owens <doctormo@ubuntu.com>
# License: GPL v2 or later
# Adopted for Fedora: Hedayat Vatankhah <hedayat.fwd@gmail.com>

from jockey.oslib import OSLib
from jockey.handlers import Handler, KernelModuleHandler

# dummy stub for xgettext
def _(x): return x

class NvidiaDriver(KernelModuleHandler):
    '''Handler for the NVidia graphic cards
    Just to provide a better name and description! 
    '''
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'nvidia',
            name=_('NVIDIA accelerated graphics driver'),
            description=_('3D-accelerated proprietary graphics driver for '
                'NVIDIA cards.'),
            rationale=_('This driver is required to fully utilise '
                'the 3D potential of NVIDIA based graphics cards.\n\n'
                'If the default open source Nouveau driver is not be able '
		'to power some 3D games, you can try this driver instead.'))
        self._recommended = None

    def id(self):
        '''Return an unique identifier of the handler.'''
        if self.package:
            return 'kmod:' + self.module + ':' + self.package
        return 'kmod:' + self.module

    def recommended(self):
        if self._recommended == None:
            self._recommended = self.package == "kmod-nvidia" or \
                self.package == "kmod-nvidia-PAE" or \
                self.package == "akmod-nvidia"
        return self._recommended

    def disable(self):
        '''Prevent the OS from using it even if the hardware is available.
        '''
        OSLib.inst.queue_packages_for_removal( { 'nvidia-xconfig',
            'nvidia-settings' } )
        KernelModuleHandler.disable(self)
        return False
