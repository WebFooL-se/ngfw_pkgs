class OSLibrary::Debian::DnsServerManager < OSLibrary::DnsServerManager
  include Singleton

  ResolvConfFile = "/etc/resolv.conf"

  def register_hooks
    os["network_manager"].register_hook( -200, "dns_server_manager", "write_files", :hook_commit )
  end

  def hook_commit
    resolv_conf
  end

  private

  def resolv_conf
    name_servers = []
    Interface.find_all( :wan => true, :config_type => InterfaceHelper::ConfigType::STATIC ).each do |i|
      config = i.current_config

      next if config.nil?
      name_servers << config.dns_1
      name_servers << config.dns_2
    end

    ## Delete all of the empty name servers, and fix the lines.
    name_servers = name_servers.delete_if { |ns| ns.nil? || ns.empty? }.map { |ns| "nameserver #{ns}" }

    ## REVIEW: Need to get the search domain.

    ## REVIEW: This is a possible hook where something else would introduce or replace name servers.
    
    header = <<EOF
## #{Time.new}
## Auto Generated by the Untangle Net Alpaca
## If you modify this file manually, your changes
## may be overriden
EOF

    os["override_manager"].write_file( ResolvConfFile, header, name_servers.join( "\n" ), "\n" )
  end
end

