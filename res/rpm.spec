Name:       boasafra
Version:    1.4.9
Release:    0
Summary:    RPM package
License:    GPL-3.0
URL:        https://github.com/RafaelPiassi/rustdesk
Vendor:     Boa Safra
Requires:   gtk3 libxcb libXfixes alsa-lib libva2 gstreamer1-plugins-base
Recommends: libayatana-appindicator-gtk3 libxdo

# https://docs.fedoraproject.org/en-US/packaging-guidelines/Scriptlets/

%description
The best open-source remote desktop client software, written in Rust.

%prep
# we have no source, so nothing here

%build
# we have no source, so nothing here

%global __python %{__python3}

%install
mkdir -p %{buildroot}/usr/bin/
mkdir -p %{buildroot}/usr/share/boasafra/
mkdir -p %{buildroot}/usr/share/boasafra/files/
mkdir -p %{buildroot}/usr/share/icons/hicolor/256x256/apps/
mkdir -p %{buildroot}/usr/share/icons/hicolor/scalable/apps/
install -m 755 $HBB/target/release/boasafra %{buildroot}/usr/bin/boasafra
install $HBB/libsciter-gtk.so %{buildroot}/usr/share/boasafra/libsciter-gtk.so
install $HBB/res/boasafra.service %{buildroot}/usr/share/boasafra/files/
install $HBB/res/128x128@2x.png %{buildroot}/usr/share/icons/hicolor/256x256/apps/boasafra.png
install $HBB/res/scalable.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/boasafra.svg
install $HBB/res/boasafra.desktop %{buildroot}/usr/share/boasafra/files/
install $HBB/res/boasafra-link.desktop %{buildroot}/usr/share/boasafra/files/

%files
/usr/bin/boasafra
/usr/share/boasafra/libsciter-gtk.so
/usr/share/boasafra/files/boasafra.service
/usr/share/icons/hicolor/256x256/apps/boasafra.png
/usr/share/icons/hicolor/scalable/apps/boasafra.svg
/usr/share/boasafra/files/boasafra.desktop
/usr/share/boasafra/files/boasafra-link.desktop
/usr/share/boasafra/files/__pycache__/*

%changelog
# let's skip this for now

%pre
# can do something for centos7
case "$1" in
  1)
    # for install
  ;;
  2)
    # for upgrade
    systemctl stop boasafra || true
  ;;
esac

%post
cp /usr/share/boasafra/files/boasafra.service /etc/systemd/system/boasafra.service
cp /usr/share/boasafra/files/boasafra.desktop /usr/share/applications/
cp /usr/share/boasafra/files/boasafra-link.desktop /usr/share/applications/
systemctl daemon-reload
systemctl enable boasafra
systemctl start boasafra
update-desktop-database

%preun
case "$1" in
  0)
    # for uninstall
    systemctl stop boasafra || true
    systemctl disable boasafra || true
    rm /etc/systemd/system/boasafra.service || true
  ;;
  1)
    # for upgrade
  ;;
esac

%postun
case "$1" in
  0)
    # for uninstall
    rm /usr/share/applications/boasafra.desktop || true
    rm /usr/share/applications/boasafra-link.desktop || true
    update-desktop-database
  ;;
  1)
    # for upgrade
  ;;
esac
