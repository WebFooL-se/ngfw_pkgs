import os
import sys
import subprocess
import datetime
import traceback
import time

# This class is responsible for writing /etc/network/interfaces
# based on the settings object passed from sync-settings.py
class WirelessManager:
    hostapdConfFilename = "/etc/hostapd/hostapd.conf"
    hostapdDefaultFilename = "/etc/default/hostapd"
    hostapdRestartFilename = "/etc/untangle-netd/pre-network-hook.d/990-restart-hostapd"
    hostapdRestartCronFilename = "/etc/cron.hourly/hostapd-restart"
    crdaDefaultFilename = "/etc/default/crda"

    def write_hostapd_conf( self, settings, prefix="", verbosity=0 ):

        configFilename = prefix + self.hostapdConfFilename
        defaultFilename = prefix + self.hostapdDefaultFilename
        restartFilename = prefix + self.hostapdRestartFilename
        restartCronFilename = prefix + self.hostapdRestartCronFilename
        crdaFilename = prefix + self.crdaDefaultFilename
        for filename in [ configFilename, defaultFilename, restartFilename, restartCronFilename, crdaFilename ]:
            fileDir = os.path.dirname( filename )
            if not os.path.exists( fileDir ):
                os.makedirs( fileDir )

        configFiles = ""

        if settings == None or settings.get('interfaces') == None and settings.get('interfaces').get('list') == None:
            return

        interfaces = settings.get('interfaces').get('list')

        foundInterface = 0

        for intf in interfaces:
            if intf.get('isWirelessInterface'):
                foundInterface = 1
                filename = configFilename + "-" + intf.get('systemDev')
                self.hostapdConfFile = open( filename, "w+" )

                self.hostapdConfFile.write("## Auto Generated\n")
                self.hostapdConfFile.write("## DO NOT EDIT. Changes will be overwritten.\n")
                self.hostapdConfFile.write("\n\n")        
                self.hostapdConfFile.write("interface=%s\n" % intf.get('systemDev'))
                self.hostapdConfFile.write("ssid=%s\n" % intf.get('wirelessSsid'))
                self.hostapdConfFile.write("country_code=US\n")
                self.hostapdConfFile.write("max_num_sta=255\n")
                self.hostapdConfFile.write("auth_algs=1\n")

                channel = intf.get('wirelessChannel')

                # Channel will be -1 for 2.4 GHz Auto and -2 for 5 GHz Auto
                # hostapd expect the channel to be 0 for auto channel selection
                if channel < 0:
                    channel = 0

                self.hostapdConfFile.write("channel=%u\n" % channel)
                if intf.get('wirelessEncryption') == 'NONE':
                    self.hostapdConfFile.write("wpa=0\n")
                elif intf.get('wirelessEncryption') == 'WPA1':
                    self.hostapdConfFile.write("wpa=1\n")
                    self.hostapdConfFile.write("wpa_passphrase=%s\n" % intf.get('wirelessPassword'))
                    self.hostapdConfFile.write("wpa_key_mgmt=WPA-PSK\n")
                    self.hostapdConfFile.write("wpa_pairwise=TKIP\n")
                    self.hostapdConfFile.write("rsn_pairwise=CCMP\n")
                elif intf.get('wirelessEncryption') == 'WPA12':
                    self.hostapdConfFile.write("wpa=3\n")
                    self.hostapdConfFile.write("wpa_passphrase=%s\n" % intf.get('wirelessPassword'))
                    self.hostapdConfFile.write("wpa_key_mgmt=WPA-PSK\n")
                    self.hostapdConfFile.write("wpa_pairwise=TKIP\n")
                    self.hostapdConfFile.write("rsn_pairwise=CCMP\n")
                elif intf.get('wirelessEncryption') == 'WPA2':
                    self.hostapdConfFile.write("wpa=2\n")
                    self.hostapdConfFile.write("wpa_passphrase=%s\n" % intf.get('wirelessPassword'))
                    self.hostapdConfFile.write("wpa_key_mgmt=WPA-PSK\n")
                    self.hostapdConfFile.write("wpa_pairwise=TKIP\n")
                    self.hostapdConfFile.write("rsn_pairwise=CCMP\n")

                if intf.get('wirelessChannel') > 11 or intf.get('wirelessChannel') == -2:
                    self.hostapdConfFile.write("hw_mode=a\n")
                else:
                    self.hostapdConfFile.write("hw_mode=g\n")
                    
                self.hostapdConfFile.write("ieee80211n=1\n")
                self.hostapdConfFile.write("wmm_enabled=1\n")
                # This configures what HT modes the wifi card support. We are going with the AR9280 to start and it will
                # be the only card supported for now
                self.hostapdConfFile.write("ht_capab=[HT40-][HT40+][SHORT-GI-40][TX-STBC][RX-STBC1][DSSS_CCK-40]\n")

                self.hostapdConfFile.flush()
                self.hostapdConfFile.close()

                print "WirelessManager: Wrote " + filename

                configFiles += filename + " "

        configFiles = configFiles[:-1]

        # FIXME need to get regulatory domain from the UI
        self.crdaDefaultFile = open( crdaFilename, "w+" )
        self.crdaDefaultFile.write("## Auto Generated\n");
        self.crdaDefaultFile.write("## DO NOT EDIT. Changes will be overwritten.\n")
        self.crdaDefaultFile.write("REGDOMAIN=US\n")
        self.crdaDefaultFile.flush()
        self.crdaDefaultFile.close()

        print "WirelessManager: Wrote " + crdaFilename

        self.hostapdDefaultFile = open( defaultFilename, "w+" )
        self.hostapdDefaultFile.write("## Auto Generated\n");
        self.hostapdDefaultFile.write("## DO NOT EDIT. Changes will be overwritten.\n")
        self.hostapdDefaultFile.write('DAEMON_CONF="' + configFiles + '"' + "\n")
        self.hostapdDefaultFile.flush()
        self.hostapdDefaultFile.close()

        print "WirelessManager: Wrote " + defaultFilename

        if foundInterface == 1:            
            # Write out the hostapd restart script

            self.hostapdRestartFile = open( restartFilename, "w+" )

            self.hostapdRestartFile.write("#!/bin/dash")
            self.hostapdRestartFile.write("\n\n")
            self.hostapdRestartFile.write("## Auto Generated\n");
            self.hostapdRestartFile.write("## DO NOT EDIT. Changes will be overwritten.\n")
            self.hostapdRestartFile.write("\n")

            self.hostapdRestartFile.write("/etc/init.d/hostapd restart\n")

            self.hostapdRestartFile.flush()
            self.hostapdRestartFile.close()

            os.system("chmod a+x %s" % restartFilename)

            print "WirelessManager: Wrote " + restartFilename
        else:
            # Write out the hostapd stop script

            self.hostapdRestartFile = open( restartFilename, "w+" )

            self.hostapdRestartFile.write("#!/bin/dash")
            self.hostapdRestartFile.write("\n\n")
            self.hostapdRestartFile.write("## Auto Generated\n");
            self.hostapdRestartFile.write("## DO NOT EDIT. Changes will be overwritten.\n")
            self.hostapdRestartFile.write("\n")

            self.hostapdRestartFile.write("/etc/init.d/hostapd stop\n")

            self.hostapdRestartFile.flush()
            self.hostapdRestartFile.close()

            os.system("chmod a+x %s" % restartFilename)

            print "WirelessManager: Wrote " + restartFilename

        if foundInterface == 1:            
            # Write out the hostapd restart script cron job
            # This is an horrible hack to solve stability issues discovered in wireless drivers
            # The only way to revive the wireless card is to restart hostapd
            # as such, we just do it every 24 hours

            self.hostapdRestartCronFile = open( restartCronFilename, "w+" )

            self.hostapdRestartCronFile.write("#!/bin/dash")
            self.hostapdRestartCronFile.write("\n\n")
            self.hostapdRestartCronFile.write("## Auto Generated\n");
            self.hostapdRestartCronFile.write("## DO NOT EDIT. Changes will be overwritten.\n")
            self.hostapdRestartCronFile.write("\n")

            self.hostapdRestartCronFile.write("/etc/init.d/hostapd restart >/dev/null 2>&1\n")

            self.hostapdRestartCronFile.flush()
            self.hostapdRestartCronFile.close()

            os.system("chmod a+x %s" % restartCronFilename)

            print "WirelessManager: Wrote " + restartCronFilename
        else:
            # Write out the hostapd stop script

            self.hostapdRestartCronFile = open( restartCronFilename, "w+" )

            self.hostapdRestartCronFile.write("#!/bin/dash")
            self.hostapdRestartCronFile.write("\n\n")
            self.hostapdRestartCronFile.write("## Auto Generated\n");
            self.hostapdRestartCronFile.write("## DO NOT EDIT. Changes will be overwritten.\n")
            self.hostapdRestartCronFile.write("\n")

            self.hostapdRestartCronFile.flush()
            self.hostapdRestartCronFile.close()

            os.system("chmod a+x %s" % restartCronFilename)

            print "WirelessManager: Wrote " + restartCronFilename

        return

    def sync_settings( self, settings, prefix="", verbosity=0 ):
        if verbosity > 1: print "WirelessManager: sync_settings()"
        
        self.write_hostapd_conf( settings, prefix, verbosity )

