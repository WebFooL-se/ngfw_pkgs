"""This class is responsible for managing the reports settings"""
# pylint: disable=unused-argument
from sync import registrar

class ReportsManager:
    """ReportsManager manages the system settings"""
    def initialize(self):
        """initialize this module"""
        pass

    def sanitize_settings(self, settings):
        """sanitizes settings"""
        pass

    def validate_settings(self, settings):
        """validates settings"""
        pass

    def create_settings(self, settings, prefix, delete_list, filename):
        """creates settings"""
        print("%s: Initializing settings" % self.__class__.__name__)
        settings['reports'] = default_reports_settings()
        settings['dashboard'] = default_dashboard_settings()

    def sync_settings(self, settings, prefix, delete_list):
        """syncs settings"""
        pass


registrar.register_manager(ReportsManager())


def default_reports_settings():
    """default reports settings"""
    return {
        "entries": []
    }

def default_dashboard_settings():
    """default dashboard settings"""
    return {
        "widgets": [{
            "name": "Top Server Ports by Session Count",
            "interval": 10
        }, {
            "name": "Top Clients Sessions by Time",
            "interval": 10
        }, {
            "name": "Top Client Addresses by Session Count",
            "interval": 5
        }, {
            "name": "Top Server Port Sessions by Time",
            "interval": 30
        }, {
            "name": "Sessions",
            "interval": 10
        }, {
            "name": "Session Count Summary",
            "interval": 30
        }]
    }
