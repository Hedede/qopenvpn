#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import sys, os, subprocess, socket
from PyQt4 import QtCore, QtGui

import stun
from ui_qopenvpnsettings import Ui_QOpenVPNSettings
from ui_qopenvpnlogviewer import Ui_QOpenVPNLogViewer


class QOpenVPNSettings(QtGui.QDialog, Ui_QOpenVPNSettings):
    def __init__(self, parent=None):
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)

        settings = QtCore.QSettings()
        self.vpnNameEdit.setText(settings.value("vpn_name").toString())
        self.sudoCommandEdit.setText(settings.value("sudo_command").toString() or "kdesu")
        if settings.value("use_sudo").toBool():
            self.sudoCheckBox.setChecked(True)
        if settings.value("show_warning").toBool():
            self.warningCheckBox.setChecked(True)

    def accept(self):
        settings = QtCore.QSettings()
        settings.setValue("vpn_name", QtCore.QVariant(self.vpnNameEdit.text()))
        settings.setValue("sudo_command", QtCore.QVariant(self.sudoCommandEdit.text()))
        settings.setValue("use_sudo", QtCore.QVariant(self.sudoCheckBox.isChecked()))
        settings.setValue("show_warning", QtCore.QVariant(self.warningCheckBox.isChecked()))
        QtGui.QDialog.accept(self)


class QOpenVPNLogViewer(QtGui.QDialog, Ui_QOpenVPNLogViewer):
    def __init__(self, parent=None):
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)
        self.refreshButton.clicked.connect(self.refresh)
        self.refresh()

    def journalctl(self, disable_sudo=False):
        """Run journalctl command and get OpenVPN logs"""
        settings = QtCore.QSettings()
        cmdline = []
        if not disable_sudo and settings.value("use_sudo").toBool():
            cmdline.append(str(settings.value("sudo_command").toString()) or "sudo")
        cmdline.extend(["journalctl", "-b", "-u", "openvpn@%s" % str(settings.value("vpn_name").toString())])
        try:
            output = subprocess.check_output(cmdline)
        except subprocess.CalledProcessError as e:
            output = e.output
        return output

    def getip(self):
        """Get external IP address and hostname"""
        try:
            stunclient = stun.StunClient()
            ip, port = stunclient.get_ip()
        except:
            ip = ""

        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except:
            hostname = ""

        return (ip, hostname)

    def refresh(self):
        """Refresh logs"""
        self.logViewerEdit.setPlainText(self.journalctl(disable_sudo=True).decode("utf-8"))
        QtCore.QTimer.singleShot(0, self.refresh_timeout)

    def refresh_timeout(self):
        """Move scrollbar to bottom and refresh IP address
        (must be called by single shot timer or else scrollbar sometimes doesn't move)"""
        self.logViewerEdit.verticalScrollBar().setValue(self.logViewerEdit.verticalScrollBar().maximum())

        ip = self.getip()
        self.ipAddressEdit.setText("%s (%s)" % (ip[0], ip[1]) if ip[1] else ip[0])


class QOpenVPNWidget(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.vpn_enabled = False

        self.create_actions()
        self.create_menu()
        self.create_icon()
        self.update_status()

        # Update status every 10 seconds
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(10000)

    def create_actions(self):
        """Create actions and connect relevant signals"""
        self.startAction = QtGui.QAction(self.tr("&Start"), self)
        self.startAction.triggered.connect(self.vpn_start)
        self.stopAction = QtGui.QAction(self.tr("S&top"), self)
        self.stopAction.triggered.connect(self.vpn_stop)
        self.settingsAction = QtGui.QAction(self.tr("S&ettings ..."), self)
        self.settingsAction.triggered.connect(self.settings)
        self.logsAction = QtGui.QAction(self.tr("Show &logs ..."), self)
        self.logsAction.triggered.connect(self.logs)
        self.quitAction = QtGui.QAction(self.tr("&Quit"), self)
        self.quitAction.triggered.connect(self.quit)

    def create_menu(self):
        """Create menu and add items to it"""
        self.trayIconMenu = QtGui.QMenu(self)
        self.trayIconMenu.addAction(self.startAction)
        self.trayIconMenu.addAction(self.stopAction)
        self.trayIconMenu.addSeparator()
        self.trayIconMenu.addAction(self.settingsAction)
        self.trayIconMenu.addAction(self.logsAction)
        self.trayIconMenu.addSeparator()
        self.trayIconMenu.addAction(self.quitAction)

    def create_icon(self):
        """Create system tray icon"""
        self.trayIcon = QtGui.QSystemTrayIcon(self)
        self.iconActive = QtGui.QIcon("%s/openvpn.svg" % os.path.dirname(os.path.abspath(__file__)))
        self.iconDisabled = QtGui.QIcon("%s/openvpn_disabled.svg" % os.path.dirname(os.path.abspath(__file__)))
        self.trayIcon.activated.connect(self.icon_activated)
        self.trayIcon.setContextMenu(self.trayIconMenu)
        self.trayIcon.setIcon(self.iconDisabled)
        self.trayIcon.setToolTip("QOpenVPN")
        self.trayIcon.show()

    def update_status(self, disable_warning=False):
        """Update GUI according to OpenVPN status"""
        settings = QtCore.QSettings()
        vpn_status = self.vpn_status()
        if vpn_status:
            self.trayIcon.setIcon(self.iconActive)
            self.startAction.setEnabled(False)
            self.stopAction.setEnabled(True)
            self.vpn_enabled = True
        else:
            self.trayIcon.setIcon(self.iconDisabled)
            self.startAction.setEnabled(True)
            self.stopAction.setEnabled(False)

            if not disable_warning and settings.value("show_warning").toBool() and self.vpn_enabled:
                QtGui.QMessageBox.warning(self, self.tr(u"QOpenVPN - Warning"),
                                          self.tr(u"You have been disconnected from VPN!"))
            self.vpn_enabled = False

    def systemctl(self, command, disable_sudo=False):
        """Run systemctl command"""
        settings = QtCore.QSettings()
        cmdline = []
        if not disable_sudo and settings.value("use_sudo").toBool():
            cmdline.append(str(settings.value("sudo_command").toString()) or "sudo")
        cmdline.extend(["systemctl", command, "openvpn@%s" % str(settings.value("vpn_name").toString())])
        return subprocess.call(cmdline)

    def vpn_start(self):
        """Start OpenVPN service"""
        retcode = self.systemctl("start")
        if retcode == 0:
            self.update_status()

    def vpn_stop(self):
        """Stop OpenVPN service"""
        retcode = self.systemctl("stop")
        if retcode == 0:
            self.update_status(disable_warning=True)

    def vpn_status(self):
        """Check if OpenVPN service is running"""
        retcode = self.systemctl("is-active", disable_sudo=True)
        return True if retcode == 0 else False

    def settings(self):
        """Show settings dialog"""
        dialog = QOpenVPNSettings(self)
        if dialog.exec_() and self.vpn_enabled:
            self.vpn_stop()
            self.vpn_start()

    def logs(self):
        """Show log viewer dialog"""
        dialog = QOpenVPNLogViewer(self)
        dialog.exec_()

    def icon_activated(self, reason):
        """Start or stop OpenVPN by double-click on tray icon"""
        if reason == QtGui.QSystemTrayIcon.DoubleClick:
            if self.vpn_enabled:
                self.vpn_stop()
            else:
                self.vpn_start()

    def quit(self):
        """Quit QOpenVPN GUI (and ask before quitting if OpenVPN is still running)"""
        if self.vpn_enabled:
            reply = QtGui.QMessageBox.question(
                self, self.tr(u"QOpenVPN - Quit"),
                self.tr(u"You are still connected to VPN! Do you really want to quit "
                        u"QOpenVPN GUI (OpenVPN service will keep running in background)?"),
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No
            )
            if reply == QtGui.QMessageBox.Yes:
                QtGui.qApp.quit()
        else:
            QtGui.qApp.quit()


def main():
    app = QtGui.QApplication(sys.argv)
    app.setOrganizationName("QOpenVPN")
    app.setOrganizationDomain("qopenvpn.eutopia.cz")
    app.setApplicationName("QOpenVPN")
    app.setQuitOnLastWindowClosed(False)
    window = QOpenVPNWidget()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
