import os
import sys
import subprocess
import datetime
import traceback
import re
from netd.network_util import NetworkUtil

# This class is responsible for writing 
# based on the settings object passed from sync-settings.py
class DnsMasqManager:
    dnsmasqHostsFilename = "/etc/hosts.dnsmasq"
    dnsmasqConfFilename = "/etc/dnsmasq.conf"
    restartHookFilename = "/etc/untangle-netd/post-network-hook.d/990-restart-dnsmasq"
    dhcpStaticsFilename = "/etc/dnsmasq.d/dhcp-static"

    def write_dnsmasq_hosts( self, settings, prefix, verbosity ):

        filename = prefix + self.dnsmasqHostsFilename
        fileDir = os.path.dirname( filename )
        if not os.path.exists( fileDir ):
            os.makedirs( fileDir )

        file = open( filename, "w+" )
        file.write("## Auto Generated\n");
        file.write("## DO NOT EDIT. Changes will be overwritten.\n");
        file.write("\n\n");

        file.write("# user-defined static entries \n")
        if ( settings.get('dnsSettings') != None and 
             settings.get('dnsSettings').get('staticEntries') != None and 
             settings.get('dnsSettings').get('staticEntries').get('list') != None ):
            for entry in settings.get('dnsSettings').get('staticEntries').get('list'):
                if entry.get('name') != None and entry.get('address') != None:
                    file.write("%s\t%s" % ( entry.get('address'), entry.get('name') ) + "\n" )
            file.write("\n")
                        
        file.write("\n")

        file.flush()
        file.close()

        if verbosity > 0: print "DnsMasqManager: Wrote %s" % filename
        return

    def write_dnsmasq_conf( self, settings, prefix="", verbosity=0 ):
        
        filename = prefix + self.dnsmasqConfFilename
        fileDir = os.path.dirname( filename )
        if not os.path.exists( fileDir ):
            os.makedirs( fileDir )

        file = open( filename, "w+" )
        file.write("## Auto Generated\n");
        file.write("## DO NOT EDIT. Changes will be overwritten.\n");
        file.write("\n\n");
        
        for intf in settings['interfaces']['list']:
            # If its a static WAN then write the uplink DNS values
            if intf.get('configType') == 'ADDRESSED' and intf.get('isWan') == True and intf.get('v4ConfigType') == 'STATIC':
                if intf.get('v4StaticDns1') != None:
                    file.write("# Interface %s DNS 1" % str(intf.get('interfaceId')) + "\n")
                    file.write("server=%s # uplink.%s" % (intf.get('v4StaticDns1'), str(intf.get('interfaceId'))) + "\n")
                    file.write("\n");
                if intf.get('v4StaticDns2') != None:
                    file.write("# Interface %s DNS 2" % str(intf.get('interfaceId')) + "\n")
                    file.write("server=%s # uplink.%s" % (intf.get('v4StaticDns2'), str(intf.get('interfaceId'))) + "\n")
                    file.write("\n");
            # If its a PPPoE WAN then write the uplink DNS values if UserPeerDns is disabled
            if intf.get('configType') == 'ADDRESSED' and intf.get('isWan') == True and intf.get('v4ConfigType') == 'PPPOE' and intf.get('v4PPPoEUsePeerDns') == False:
                if intf.get('v4PPPoEDns1') != None:
                    file.write("# Interface %s DNS 1" % str(intf.get('interfaceId')) + "\n")
                    file.write("server=%s # uplink.%s" % (intf.get('v4PPPoEDns1'), str(intf.get('interfaceId'))) + "\n")
                    file.write("\n");
                if intf.get('v4PPPoEDns2') != None:
                    file.write("# Interface %s DNS 2" % str(intf.get('interfaceId')) + "\n")
                    file.write("server=%s # uplink.%s" % (intf.get('v4PPPoEDns2'), str(intf.get('interfaceId'))) + "\n")
                    file.write("\n");
            # If its a dhcp WAN then write the some comments for clarity
            if intf.get('configType') == 'ADDRESSED' and intf.get('isWan') == True and intf.get('v4ConfigType') == 'AUTO':
                file.write("# Interface %s DNS" % str(intf.get('interfaceId')) + "\n")
                file.write("# stored in /etc/dnsmasq.d/dhcp-upstream-dns-servers" + "\n")
                file.write("\n");
                
                
        # Set globla options
        file.write("# Global DNS options\n")
        file.write("interface=* # specified so local-service option is disabled\n");
        file.write("localise-queries\n");
        file.write("expand-hosts\n");
        # dont read /etc/hosts - this will result in returning 127.0.0.1 for some queries
        file.write("no-hosts\n");
        file.write("addn-hosts=/etc/hosts.dnsmasq\n");
        # use a dedicated file for the interface specific feature where dnsmasq returns the
        # most appropriate IP based on the interface address where the query was received
        file.write("addn-hosts=/etc/hosts.untangle\n");
        file.write("\n");

        # Set global DHCP options
        file.write("# Global DHCP options\n")
        if (settings.get('dhcpAuthoritative') == True): file.write("dhcp-authoritative\n")
        file.write("dhcp-lease-max=5000\n"); # should this be configurable?
        file.write("\n");

        # Enable DHCP on internal NICs (where configured)
        for intf in settings['interfaces']['list']:
            if intf.get('configType') == 'ADDRESSED' and intf.get('isWan') == False:
                if intf.get('dhcpEnabled') == True:
                    leaseTime = 3600
                    if intf.get('dhcpLeaseDuration') != None and intf.get('dhcpLeaseDuration') != "":
                        try:
                            leaseTime = int(intf.get('dhcpLeaseDuration'))
                        except Exception,e:
                            pass
                    
                    # Use symbolicDev so the whole bridge is served if its a bridge
                    file.write("# Interface %s (%s) DHCP" % (str(intf.get('interfaceId')), intf.get('symbolicDev')) + "\n")
                    file.write("dhcp-range=tag:%s,%s,%s,%i" % (intf.get('symbolicDev'), str(intf.get('dhcpRangeStart')), str(intf.get('dhcpRangeEnd')), leaseTime) + "\n")
                    
                    # set gateway option 
                    # If the override value is specified, set it, otherwise use static address (ourselves) as gateway
                    if intf.get('dhcpGatewayOverride') != None and intf.get('dhcpGatewayOverride') != "":
                        file.write("dhcp-option=tag:%s,3,%s # gateway" % (intf.get('symbolicDev'), str(intf.get('dhcpGatewayOverride'))) + "\n")
                    else:
                        file.write("dhcp-option=tag:%s,3,%s # gateway" % (intf.get('symbolicDev'), str(intf.get('v4StaticAddress'))) + "\n")
                        
                    # set netmask option 
                    # If the override value is specified, set it, otherwise use static netmask 
                    if intf.get('dhcpNetmaskOverride') != None and intf.get('dhcpNetmaskOverride') != "":
                        file.write("dhcp-option=tag:%s,1,%s # netmask" % (intf.get('symbolicDev'), str(intf.get('dhcpNetmaskOverride'))) + "\n")
                    else:
                        file.write("dhcp-option=tag:%s,1,%s # netmask" % (intf.get('symbolicDev'), str(intf.get('v4StaticNetmask'))) + "\n")

                    # set dns option 
                    # If the override value is specified, set it, otherwise use static address (ourselves) as DNS 
                    if intf.get('dhcpDnsOverride') != None and intf.get('dhcpDnsOverride') != "":
                        file.write("dhcp-option=tag:%s,6,%s # dns" % (intf.get('symbolicDev'), str(intf.get('dhcpDnsOverride'))) + "\n")
                    else:
                        file.write("dhcp-option=tag:%s,6,%s # dns" % (intf.get('symbolicDev'), str(intf.get('v4StaticAddress'))) + "\n")

                    # write custom DHCP options
                    if intf.get('dhcpOptions') != None and intf.get('dhcpOptions').get('list') != None:
                        for dhcpOption in intf.get('dhcpOptions').get('list'):
                            if dhcpOption.get('enabled') == None or not dhcpOption.get('enabled'):
                                continue
                            file.write("dhcp-option=tag:%s,%s # custom dhcp option" % (intf.get('symbolicDev'), dhcpOption.get('value')) + "\n")

                    file.write("\n");
                            
        # Write domain
        if settings.get('domainName') != None:
            file.write("# domain\n");
            file.write("domain=%s" % ( settings.get('domainName') ) + "\n" )
            file.write("\n");

        # Local DNS servers
        file.write("# Local DNS servers\n")
        if ( settings.get('dnsSettings') != None and 
             settings.get('dnsSettings').get('localServers') != None and 
             settings.get('dnsSettings').get('localServers').get('list') != None ):
            for localServer in settings.get('dnsSettings').get('localServers').get('list'):
                if localServer.get('domain') != None and localServer.get('localServer') != None:
                    file.write("local=/%s/%s" % ( localServer['domain'], localServer['localServer'] ) + "\n" )
            file.write("\n");

        # Write custom advanced options
        if settings.get('dnsmasqOptions') != None:
            file.write("# Custom dnsmasq options\n");
            file.write("%s" % ( settings.get('dnsmasqOptions') ) + "\n" )
            file.write("\n");

        file.write("\n");
        file.flush()
        file.close()

        if verbosity > 0: print "DnsMasqManager: Wrote %s" % filename
        return

    def write_dhcp_statics_file( self, settings, prefix="", verbosity=0 ):

        filename = prefix + self.dhcpStaticsFilename
        fileDir = os.path.dirname( filename )
        if not os.path.exists( fileDir ):
            os.makedirs( fileDir )

        file = open( filename, "w+" )

        # Static DHCP Entries
        file.write("# Static DHCP entries\n")
        if ( settings.get('staticDhcpEntries') != None and 
             settings.get('staticDhcpEntries').get('list') != None ):
            for staticDhcpEntry in settings.get('staticDhcpEntries').get('list'):
                if staticDhcpEntry.get('macAddress') != None and staticDhcpEntry.get('address') != None:
                    file.write("dhcp-host=%s,%s" % ( staticDhcpEntry.get('macAddress'), staticDhcpEntry.get('address') ) + "\n" )
            file.write("\n");

        file.write("\n");
        file.flush()
        file.close()

        if verbosity > 0: print "DnsMasqManager: Wrote %s" % filename
        return

    def write_restart_dnsmasq_hook( self, settings, prefix="", verbosity=0 ):

        filename = prefix + self.restartHookFilename
        fileDir = os.path.dirname( filename )
        if not os.path.exists( fileDir ):
            os.makedirs( fileDir )

        file = open( filename, "w+" )
        file.write("#!/bin/dash");
        file.write("\n\n");

        file.write("## Auto Generated\n");
        file.write("## DO NOT EDIT. Changes will be overwritten.\n");
        file.write("\n");

        file.write(r"""
DNSMASQ_PID="`pidof dnsmasq`"

# Restart dnsmasq if it isnt found
# Or if dnsmasq.conf or hosts.dnsmasq has been written since dnsmasq was started
if [ -z "$DNSMASQ_PID" ] ; then
    /etc/init.d/dnsmasq restart
# use not older than (instead of newer than) because it compares seconds and we want an equal value to still do a restart
elif [ ! /etc/dnsmasq.conf -ot /proc/$DNSMASQ_PID ] ; then
    /etc/init.d/dnsmasq restart
# use not older than (instead of newer than) because it compares seconds and we want an equal value to still do a restart
elif [ ! /etc/hosts.dnsmasq -ot /proc/$DNSMASQ_PID ] ; then
    /etc/init.d/dnsmasq restart
fi
""")

        file.write("\n");
        file.flush()
        file.close()
    
        os.system("chmod a+x %s" % filename)
        if verbosity > 0: print "DnsMasqManager: Wrote %s" % filename
        return

    def sync_settings( self, settings, prefix="", verbosity=0 ):

        if verbosity > 1: print "DnsMasqManager: sync_settings()"
        
        self.write_dnsmasq_hosts( settings, prefix, verbosity )

        self.write_dhcp_statics_file( settings, prefix, verbosity )

        self.write_dnsmasq_conf( settings, prefix, verbosity )

        self.write_restart_dnsmasq_hook( settings, prefix, verbosity )

        return
