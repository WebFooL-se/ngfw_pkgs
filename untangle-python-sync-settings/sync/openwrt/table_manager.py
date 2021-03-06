"""table manager manages nftable tables"""
# pylint: disable=unused-argument
# pylint: disable=bare-except
import os
import stat
from sync import registrar
from sync import nftables_util

class TableManager:
    """ReportsManager manages the all the firewall tables"""
    filename_prefix = "/etc/config/nftables-rules.d/2"

    def initialize(self):
        """initialize this module"""
        registrar.register_file(self.filename_prefix + ".*", "restart-nftables-rules", self)

    def sanitize_settings(self, settings):
        """sanitizes settings"""
        pass

    def validate_settings(self, settings):
        """validates settings"""
        pass

    def create_settings(self, settings, prefix, delete_list, filename):
        """creates settings"""
        print("%s: Initializing settings" % self.__class__.__name__)

        tables = {}
        tables['filter'] = default_filter_rules_table()
        tables['port-forward'] = default_port_forward_table()
        tables['vote'] = default_vote_table()
        tables['nat'] = default_nat_rules_table()
        tables['access'] = default_access_rules_table()
        tables['web-filter'] = default_web_filter_table()
        tables['captive-portal'] = default_captive_portal_table()
        tables['shaping'] = default_shaping_rules_table()

        settings['firewall'] = {}
        settings['firewall']['tables'] = tables

    def write_files(self, settings, prefix, delete_list):
        """writes the rule files"""
        if settings.get('firewall') is None or settings.get('firewall').get('tables') is None:
            return

        i = 0
        for _, table in sorted(settings.get('firewall').get('tables').items()):
            if table.get('name') is None:
                raise Exception('Invalid table: Missing name')
            if table.get('family') is None:
                raise Exception('Invalid table %s: Missing family' % table.get('name'))
            if table.get('chains') is None:
                raise Exception('Invalid table %s: Missing chains' % table.get('name'))

            filename_noprefix = self.filename_prefix + ("%02d-%s" % (i, table.get('name')))
            filename = prefix + filename_noprefix
            try:
                delete_list.remove(filename_noprefix)
            except:
                pass
            write_file(filename, table, prefix)
            i = i+1

    def sync_settings(self, settings, prefix, delete_list):
        """syncs settings"""

        # Add all /etc/config/nftables-rules.d/2.* files to the delete_list
        # Remove all the files that we write later
        # This ensures that all the existing /etc/config/nftables-rules.d/2* that we don't
        # write get removed
        for (dirpath, _, filenames) in os.walk("/etc/config/nftables-rules.d/"):
            for filename in filenames:
                if filename.startswith("2"):
                    full_name = dirpath + filename
                    delete_list.append(full_name)
        # Write all the /etc/config/nftables-rules.d/2.* files
        self.write_files(settings, prefix, delete_list)

registrar.register_manager(TableManager())

def write_file(filename, table_settings, prefix):
    """write_file writes the specified file"""
    file_dir = os.path.dirname(filename)
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)

    file = open(filename, "w+")
    file.write("#!/bin/sh")
    file.write("\n\n")

    file.write("## Auto Generated\n")
    file.write("## DO NOT EDIT. Changes will be overwritten.\n")
    file.write("\n\n")

    file.write(nftables_util.table_all_cmds(table_settings) + "\n")

    file.write("\n")
    file.flush()
    file.close()

    os.chmod(filename, os.stat(filename).st_mode | stat.S_IEXEC)
    print("TableManager: Wrote %s" % filename)
    return


def default_filter_rules_table():
    """default filter rules table"""
    return {
        "name": "filter",
        "family": "inet",
        "chains": [{
            "name": "filter-rules",
            "description": "The base filter-rules chain",
            "base": True,
            "type": "filter",
            "hook": "forward",
            "priority": 0,
            "rules": [{
                "enabled": True,
                "description": "Call new session filter rules",
                "ruleId": 1,
                "conditions": [],
                "action": {
                    "type": "JUMP",
                    "chain": "filter-rules-new"
                }
            }, {
                "enabled": True,
                "description": "Call early-session session filter rules",
                "ruleId": 2,
                "conditions": [],
                "action": {
                    "type": "JUMP",
                    "chain": "filter-rules-early"
                }
            }, {
                "enabled": True,
                "description": "Call deep-session (all packets) session filter rules",
                "ruleId": 3,
                "conditions": [],
                "action": {
                    "type": "JUMP",
                    "chain": "filter-rules-all"
                }
            }]
        }, {
            "name": "filter-rules-new",
            "description": "The chain to process the first packet of each session (new sessions)",
            "default": True,
            "rules": [{
                "ruleId": 1,
                "description": "Example: A rule of blocking TCP sessions to 1.2.3.4 port 1234",
                "enabled": False,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "SERVER_ADDRESS",
                    "op": "==",
                    "value": "1.2.3.4"
                }, {
                    "type": "SERVER_PORT",
                    "op": "==",
                    "value": "1234"
                }],
                "action": {
                    "type": "REJECT"
                }
            }, {
                "ruleId": 2,
                "description": "Example: A rule of blocking TCP port 21 (FTP) from 192.168.1.100",
                "enabled": False,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "CLIENT_ADDRESS",
                    "op": "==",
                    "value": "192.168.1.100"
                }, {
                    "type": "SERVER_PORT",
                    "op": "==",
                    "value": "21"
                }],
                "action": {
                    "type": "REJECT"
                }
            }]
        }, {
            "name": "filter-rules-early",
            "description": "The chain to process the first few packets of each session (early in session)",
            "rules": []
        }, {
            "name": "filter-rules-all",
            "description": "The chain to process the all packets",
            "rules": []
        }]
    }


def default_port_forward_table():
    """default port forward table"""
    return {
        "name": "port-forward",
        "family": "ip,ip6",
        "chains": [{
            "name": "port-forward-rules",
            "description": "The base port-forwards chain",
            "base": True,
            "type": "nat",
            "hook": "prerouting",
            "priority": 100,
            "default": True,
            "rules": [{
                "enabled": False,
                "description": "Example: Forward 1.2.3.4 to 1.2.3.5",
                "ruleId": 1,
                "conditions": [{
                    "type": "DESTINATION_ADDRESS",
                    "op": "==",
                    "value": "1.2.3.4"
                }],
                "action": {
                    "type": "DNAT",
                    "dnat_address": "1.2.3.5"
                }
            }]
        }]
    }


def default_vote_table():
    """default vote table"""
    return {
        "name": "vote",
        "family": "ip,ip6,inet",
        "chains": [{
            "name": "prerouting-route-vote-rules",
            "description": "The prerouting route vote rules",
            "base": True,
            "type": "filter",
            "hook": "prerouting",
            "priority": -130,
            "rules": [{
                "enabled": True,
                "description": "Call route-vote-rules",
                "ruleId": 1,
                "conditions": [],
                "action": {
                    "type": "JUMP",
                    "chain": "route-vote-rules"
                }
            }],
        }, {
            "name": "output-route-vote-rules",
            "description": "The prerouting route vote rules",
            "base": True,
            "type": "route",
            "hook": "output",
            "priority": -140,
            "rules": [{
                "enabled": True,
                "description": "Call route-vote-rules",
                "ruleId": 2,
                "conditions": [],
                "action": {
                    "type": "JUMP",
                    "chain": "route-vote-rules"
                }
            }],
        }, {
            "name": "route-vote-rules",
            "description": "The main route vote rules chain",
            "default": True,
            "rules": []
        }]
    }


def default_nat_rules_table():
    """default nat rules table"""
    return {
        "name": "nat",
        "family": "ip,ip6",
        "chains": [{
            "name": "nat-rules",
            "description": "The nat-rules chain",
            "base": True,
            "type": "nat",
            "hook": "postrouting",
            "priority": 95,
            "rules": [{
                "enabled": True,
                "description": "Example: NAT TCP port 25 to 1.2.3.4",
                "ruleId": 1,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "SERVER_PORT",
                    "op": "==",
                    "value": "1234"
                }],
                "action": {
                    "type": "SNAT",
                    "snat_address": "1.2.3.4"
                }
            }, {
                "enabled": True,
                "description": "Example: NAT client 192.168.1.100 to 1.2.3.4",
                "ruleId": 2,
                "conditions": [{
                    "type": "SOURCE_ADDRESS",
                    "op": "==",
                    "value": "192.168.1.100"
                }],
                "action": {
                    "type": "SNAT",
                    "snat_address": "1.2.3.4"
                }
            }, {
                "enabled": True,
                "description": "Example: NAT client 192.168.1.200 to Auto",
                "ruleId": 3,
                "conditions": [{
                    "type": "SOURCE_ADDRESS",
                    "op": "==",
                    "value": "192.168.1.200"
                }],
                "action": {
                    "type": "MASQUERADE"
                }
            }],
        }]
    }


def default_access_rules_table():
    """default access rules table"""
    return {
        "name": "access",
        "family": "inet",
        "chains": [{
            "name": "access-rules",
            "description": "The base access-rules chain",
            "base": True,
            "type": "filter",
            "hook": "input",
            "priority": 0,
            "rules": [{
                "enabled": True,
                "description": "Accept established",
                "ruleId": 1,
                "conditions": [{
                    "type": "CT_STATE",
                    "op": "==",
                    "value": "established"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept related",
                "ruleId": 2,
                "conditions": [{
                    "type": "CT_STATE",
                    "op": "==",
                    "value": "related"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Drop invalid",
                "ruleId": 3,
                "conditions": [{
                    "type": "CT_STATE",
                    "op": "==",
                    "value": "invalid"
                }],
                "action": {
                    "type": "DROP"
                }
            }, {
                "enabled": True,
                "description": "Accept loopback",
                "ruleId": 4,
                "conditions": [{
                    "type": "SOURCE_INTERFACE_NAME",
                    "op": "==",
                    "value": "lo"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept HTTP on LANs (TCP/80)",
                "ruleId": 5,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "80"
                }, {
                    "type": "SOURCE_INTERFACE_ZONE",
                    "op": "==",
                    "value": "lan"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept HTTP on WANs (TCP/80)",
                "ruleId": 6,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "80"
                }, {
                    "type": "SOURCE_INTERFACE_ZONE",
                    "op": "==",
                    "value": "wan"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept SSH on LANs (TCP/22)",
                "ruleId": 7,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "22"
                }, {
                    "type": "SOURCE_INTERFACE_ZONE",
                    "op": "==",
                    "value": "lan"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept SSH on WANs (TCP/22)",
                "ruleId": 8,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "22"
                }, {
                    "type": "SOURCE_INTERFACE_ZONE",
                    "op": "==",
                    "value": "wan"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept DNS on LANs (TCP/53)",
                "ruleId": 9,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "53"
                }, {
                    "type": "SOURCE_INTERFACE_ZONE",
                    "op": "==",
                    "value": "lan"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept DNS on LANs (UDP/53)",
                "ruleId": 10,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "17"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "53"
                }, {
                    "type": "SOURCE_INTERFACE_ZONE",
                    "op": "==",
                    "value": "lan"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept ICMP",
                "ruleId": 11,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "1"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept ICMPv6",
                "ruleId": 12,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "58"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept DHCP on LANs (UDP/67)",
                "ruleId": 13,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "17"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "67"
                }, {
                    "type": "SOURCE_INTERFACE_ZONE",
                    "op": "==",
                    "value": "lan"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept DHCPv6 on LANs (UDP/547)",
                "ruleId": 14,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "17"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "547"
                }, {
                    "type": "SOURCE_INTERFACE_ZONE",
                    "op": "==",
                    "value": "lan"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Accept DHCPv6 Replies (UDP/546)",
                "ruleId": 15,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "17"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "546"
                }],
                "action": {
                    "type": "ACCEPT"
                }
            }, {
                "enabled": True,
                "description": "Drop All",
                "ruleId": 16,
                "conditions": [],
                "action": {
                    "type": "DROP"
                }
            }]
        }]
    }


def default_web_filter_table():
    """default web filter table"""
    return {
        "name": "web-filter",
        "family": "ip,ip6",
        "chains": [{
            "name": "web-filter-rules",
            "description": "The base web-filter-rules chain",
            "base": True,
            "type": "nat",
            "hook": "prerouting",
            "priority": -105,
            "rules": []
        }]
    }


def default_captive_portal_table():
    """default captive portal table"""
    return {
        "name": "captive-portal",
        "family": "ip,ip6",
        "chains": [{
            "name": "captive-portal-rules",
            "description": "The base captive-portal-rules chain",
            "base": True,
            "type": "nat",
            "hook": "prerouting",
            "priority": -110,
            "rules": []
        }]
    }


def default_shaping_rules_table():
    """default shaping rules table"""
    return {
        "name": "shaping",
        "family": "inet",
        "chains": [{
            "name": "shaping-rules",
            "description": "The base shaping-rules chain",
            "base": True,
            "type": "filter",
            "hook": "postrouting",
            "priority": 5,
            "rules": [{
                "enabled": True,
                "description": "Call prioritization-rules",
                "ruleId": 1,
                "conditions": [],
                "action": {
                    "type": "JUMP",
                    "chain": "prioritization-rules"
                }
            }, {
                "enabled": True,
                "description": "Call limiting-rules",
                "ruleId": 2,
                "conditions": [],
                "action": {
                    "type": "JUMP",
                    "chain": "limiting-rules"
                }
            }],
        }, {
            "name": "prioritization-rules",
            "description": "The main prioritization rules chain",
            "default": True,
            "rules": [{
                "enabled": False,
                "description": "VoIP (SIP) Traffic",
                "ruleId": 1,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "{5060,5061}"
                }],
                "action": {
                    "type": "SET_PRIORITY",
                    "priority": 1
                }
            }, {
                "enabled": False,
                "description": "VoIP (IAX) Traffic",
                "ruleId": 2,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "4569"
                }],
                "action": {
                    "type": "SET_PRIORITY",
                    "priority": 1
                }
            }, {
                "enabled": True,
                "description": "Ping Priority",
                "ruleId": 3,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "icmp"
                }],
                "action": {
                    "type": "SET_PRIORITY",
                    "priority": 1
                }
            }, {
                "enabled": True,
                "description": "DNS Priority",
                "ruleId": 4,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "udp"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "53"
                }],
                "action": {
                    "type": "SET_PRIORITY",
                    "priority": 1
                }
            }, {
                "enabled": True,
                "description": "SSH Priority",
                "ruleId": 5,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "22"
                }],
                "action": {
                    "type": "SET_PRIORITY",
                    "priority": 2
                }
            }, {
                "enabled": True,
                "description": "Openvpn Priority",
                "ruleId": 6,
                "conditions": [{
                    "type": "IP_PROTOCOL",
                    "op": "==",
                    "value": "6"
                }, {
                    "type": "DESTINATION_PORT",
                    "op": "==",
                    "value": "1194"
                }],
                "action": {
                    "type": "SET_PRIORITY",
                    "priority": 3
                }
            }]
        }, {
            "name": "limiting-rules",
            "description": "The main limiting rules chain",
            "default": True,
            "rules": []
        }]
    }
