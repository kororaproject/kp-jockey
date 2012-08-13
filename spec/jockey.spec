%global selinux_variants targeted mls
%global selinux_policyver %(%{__sed} -e 's,.*selinux-policy-\\([^/]*\\)/.*,\\1,' /usr/share/selinux/devel/policyhelp || echo 0.0.0)

Name:           jockey
Version:        0.9.7
Release:        3%{?dist}
Summary:        Jockey driver manager

License:        GPLv2+
URL:            https://launchpad.net/jockey
Source0:        %{name}-%{version}.tar.gz
Patch0:         jockey-0.9.3-gtkwidthfix.patch

BuildArch:      noarch
BuildRequires:  python2-devel python-distutils-extra gettext intltool sed
Requires:       dbus-python polkit PackageKit python-xkit jockey-modaliases

%description
Jockey provides an user interface and desktop integration for installation 
and upgrade of third-party drivers. It is written in a distribution agnostic 
way, and to be easily portable to different front-ends (GNOME, KDE, 
command line).

%package gtk
Summary:        GTK front-end for Jockey driver manager
Requires:       %{name} = %{version}-%{release}
Requires:       dbus-python polkit-gnome gdk-pixbuf2 gtk3 
Requires:       gobject-introspection libnotify pygobject3

%description gtk
This package provides a GTK interface for Jockey.

Jockey provides an user interface and desktop integration for installation 
and upgrade of third-party drivers. It is written in a distribution agnostic 
way, and to be easily portable to different front-ends (GNOME, KDE, 
command line).

%package kde
Summary:        KDE front-end for Jockey driver manager
Requires:       %{name} = %{version}-%{release}
Requires:       dbus-python polkit-kde PyQt4 PyKDE4
Requires:       pygobject3

%description kde
This package provides a KDE interface for Jockey.

Jockey provides an user interface and desktop integration for installation 
and upgrade of third-party drivers. It is written in a distribution agnostic 
way, and to be easily portable to different front-ends (GNOME, KDE, 
command line).

%package selinux
Summary:        SELinux module for Jockey driver manager
Epoch:          1
BuildRequires:  checkpolicy selinux-policy selinux-policy-devel hardlink
BuildRequires:  /usr/share/selinux/devel/policyhelp
Requires:       %{name}
Requires:       selinux-policy >= %{selinux_policyver} selinux-policy-targeted
Requires(post):   /usr/sbin/semodule
Requires(postun): /usr/sbin/semodule

%description selinux
This package provides an SELinux module for Jockey driver manager.
You should install this package if you are using SELinux, so that Jockey
can be run in enforcing mode.

%prep
%setup -q
%patch0 -p1 -b .gtkwidthfix
sed -i.nocert "s|'repository' not in|'repository' in|" jockey/ui.py
sed -i.noblacklist "s|do_blacklist=True|do_blacklist=False|" jockey/handlers.py

%build
%{__python} setup.py build

# building SELinux module
cd selinux
for selinuxvariant in %{selinux_variants}
do
  make NAME=${selinuxvariant} -f /usr/share/selinux/devel/Makefile
  mv %{name}_custom.pp %{name}_custom.pp.${selinuxvariant}
  make NAME=${selinuxvariant} -f /usr/share/selinux/devel/Makefile clean
done
cd -

%install
%{__python} setup.py install -O1 --root %{buildroot}
rm -r %{buildroot}%{_datadir}/doc
mkdir -p %{buildroot}%{_var}/cache/%{name}

# Install config file
mkdir -p %{buildroot}%{_sysconfdir}
install -p -m 644 config/%{name}.conf \
      %{buildroot}%{_sysconfdir}/

# Move autostart files to the new place
mkdir -p %{buildroot}%{_sysconfdir}/xdg/autostart/
mv %{buildroot}%{_datadir}/autostart/* %{buildroot}%{_sysconfdir}/xdg/autostart/
rmdir %{buildroot}%{_datadir}/autostart/

# install the selinux module
for selinuxvariant in %{selinux_variants}
do
  install -d %{buildroot}%{_datadir}/selinux/${selinuxvariant}
  install -p -m 644 \
    selinux/%{name}_custom.pp.${selinuxvariant} \
    %{buildroot}%{_datadir}/selinux/${selinuxvariant}/%{name}_custom.pp
done
/usr/sbin/hardlink -cv %{buildroot}%{_datadir}/selinux

sed -i s/X-GNOME-Settings-Panel\;//g %{buildroot}%{_datadir}/applications/jockey-gtk.desktop

# validate desktop files
desktop-file-validate %{buildroot}%{_datadir}/applications/jockey-gtk.desktop
desktop-file-validate %{buildroot}%{_datadir}/applications/jockey-kde.desktop

desktop-file-validate  \
      %{buildroot}%{_sysconfdir}/xdg/autostart/jockey-gtk.desktop
desktop-file-validate  \
      %{buildroot}%{_sysconfdir}/xdg/autostart/jockey-kde.desktop

%find_lang %{name}

%post
/bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :

%post selinux
for selinuxvariant in %{selinux_variants}
do
  /usr/sbin/semodule -s ${selinuxvariant} -i \
    %{_datadir}/selinux/${selinuxvariant}/%{name}_custom.pp &> /dev/null || :
done

%postun
if [ $1 -eq 0 ] ; then
    /bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null
    /usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
fi

%postun selinux
if [ $1 -eq 0 ] ; then
  for selinuxvariant in %{selinux_variants}
  do
    /usr/sbin/semodule -s ${selinuxvariant} -r %{name} &> /dev/null || :
  done
fi

%posttrans
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%files -f %{name}.lang
%doc AUTHORS COPYING README.txt
%config %{_sysconfdir}/%{name}.conf
%{_bindir}/jockey-text
%{python_sitelib}/*
%{_datadir}/%{name}/%{name}-backend
%{_datadir}/%{name}/handlers
%{_datadir}/icons/hicolor/*/*/*
%{_datadir}/dbus-1/system-services/*
%{_datadir}/polkit-1/actions/*
%{_sysconfdir}/dbus-1/system.d/*
%{_var}/cache/%{name}

%files gtk
%{_bindir}/jockey-gtk
%{_datadir}/%{name}/%{name}-gtk.ui
%{_datadir}/applications/jockey-gtk.desktop
%{_sysconfdir}/xdg/autostart/jockey-gtk.desktop
%{_datadir}/dbus-1/services/*

%files kde
%{_bindir}/jockey-kde
%{_datadir}/%{name}/LicenseDialog.ui
%{_datadir}/%{name}/ManagerWindowKDE4.ui
%{_datadir}/%{name}/ProgressDialog.ui

%{_datadir}/applications/jockey-kde.desktop
%{_sysconfdir}/xdg/autostart/jockey-kde.desktop
%{_datadir}/kde4/apps/jockey/jockey.notifyrc

%files selinux
%doc selinux/*te
%{_datadir}/selinux/*/%{name}_custom.pp

%changelog
* Mon Aug 13 2012 Chris Smart <chris@kororaa.org> - 0.9.7-3
- Package provides user feedback when building akmods and initramfs. Also removes shortcut from GNOME's control center as package cannot be run from there.

* Wed Jun 27 2012 Chris Smart <chris@kororaa.org> - 0.9.7-2
- Updated SELinux policy to be compatible with selinux-policy 3.10.0-132 which includes Jockey module.
- Improved akmod support, which is now the default.

* Wed May 30 2012 Hedayat Vatankhah <hedayat.fwd+rpmchlog@gmail.com> - 0.9.7-1
- Updated to jockey 0.9.7

* Fri Dec 09 2011 Chris Smart <chris@kororaa.org> - 0.9.6-2
- Added pygobject3 to list of runtime dependencies, fixes breakage on KDE

* Thu Dec 08 2011 Hedayat Vatankhah <hedayat.fwd+rpmchlog@gmail.com> - 0.9.6-1
- Updated to latest upstream version 0.9.6

* Wed Dec 07 2011 Hedayat Vatankhah <hedayat.fwd+rpmchlog@gmail.com> - 0.9.5-2
- Add an Epoch for jockey-selinux to resolve versioning inconsistency

* Tue Dec 06 2011 Hedayat Vatankhah <hedayat.fwd+rpmchlog@gmail.com> - 0.9.5-1
- Remove separate versioning for -selinux subpackage

* Mon Dec 05 2011 Chris Smart <chris@kororaa.org> - 0.9.5-1
- Update to upstream version 0.9.5
- Added support for akmods (where available), if enabled in Jockey config file.

* Sun Oct 16 2011 Hedayat Vatankhah <hedayat.fwd+rpmchlog@gmail.com> - 0.9.3-3
- Add initial PAE kernel module installation support

* Thu Aug 18 2011 Hedayat Vatankhah <hedayat.fwd+rpmchlog@gmail.com> - 0.9.3-2
- jockey should depend on xkit, not jockey-gtk

* Thu Jul 28 2011 Hedayat Vatankhah <hedayat.fwd+rpmchlog@gmail.com> - 0.9.3-1
- Initial version

