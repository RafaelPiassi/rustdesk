Name:       boasafra
Version:    1.4.9
Release:    0
Summary:    RPM package
License:    GPL-3.0
URL:        https://github.com/RafaelPiassi/rustdesk
Vendor:     Boa Safra
Requires:   gtk3 libxcb libXfixes alsa-lib libva gstreamer1-plugins-base
Recommends: libayatana-appindicator-gtk3 libxdo
Provides:   libdesktop_drop_plugin.so()(64bit), libdesktop_multi_window_plugin.so()(64bit), libfile_selector_linux_plugin.so()(64bit), libflutter_custom_cursor_plugin.so()(64bit), libflutter_linux_gtk.so()(64bit), libscreen_retriever_plugin.so()(64bit), libtray_manager_plugin.so()(64bit), liburl_launcher_linux_plugin.so()(64bit), libwindow_manager_plugin.so()(64bit), libwindow_size_plugin.so()(64bit), libtexture_rgba_renderer_plugin.so()(64bit)

# https://docs.fedoraproject.org/en-US/packaging-guidelines/Scriptlets/

%description
The best open-source remote desktop client software, written in Rust.

%prep
# we have no source, so nothing here

%build
# we have no source, so nothing here

# %global __python %{__python3}

%install

mkdir -p "%{buildroot}/usr/share/boasafra" && cp -r ${HBB}/flutter/build/linux/x64/release/bundle/* -t "%{buildroot}/usr/share/boasafra"
mkdir -p "%{buildroot}/usr/bin"
install -Dm 644 $HBB/res/boasafra.service -t "%{buildroot}/usr/share/boasafra/files"
install -Dm 644 $HBB/res/boasafra.desktop -t "%{buildroot}/usr/share/boasafra/files"
install -Dm 644 $HBB/res/boasafra-link.desktop -t "%{buildroot}/usr/share/boasafra/files"
install -Dm 644 $HBB/res/128x128@2x.png "%{buildroot}/usr/share/icons/hicolor/256x256/apps/boasafra.png"
install -Dm 644 $HBB/res/scalable.svg "%{buildroot}/usr/share/icons/hicolor/scalable/apps/boasafra.svg"

%files
/usr/share/boasafra/*
/usr/share/boasafra/files/boasafra.service
/usr/share/icons/hicolor/256x256/apps/boasafra.png
/usr/share/icons/hicolor/scalable/apps/boasafra.svg
/usr/share/boasafra/files/boasafra.desktop
/usr/share/boasafra/files/boasafra-link.desktop

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
ln -sf /usr/share/boasafra/boasafra /usr/bin/boasafra
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
    rm /usr/bin/boasafra || true
    rmdir /usr/lib/boasafra || true
    rmdir /usr/local/boasafra || true
    rmdir /usr/share/boasafra || true
    rm /usr/share/applications/boasafra.desktop || true
    rm /usr/share/applications/boasafra-link.desktop || true
    update-desktop-database
  ;;
  1)
    # for upgrade
    rmdir /usr/lib/boasafra || true
    rmdir /usr/local/boasafra || true
  ;;
esac
