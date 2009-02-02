Ext.ns('Ung');
Ext.ns('Ung.Alpaca');
Ext.ns('Ung.Alpaca.Pages');
Ext.ns('Ung.Alpaca.Pages.Network');

if ( Ung.Alpaca.Glue.hasPageRenderer( "network", "index" )) {
    Ung.Alpaca.Util.stopLoading();
}

Ung.Alpaca.Pages.Network.Index = Ext.extend( Ung.Alpaca.PagePanel, {
    initComponent : function()
    {
        var items = [{
            xtype : "label",
            cls: 'page-header-text',
            html : this._( "Network" )
        },{
            xtype : 'button',
            text : this._( "Refresh Interfaces" ),
            handler : Ung.Alpaca.Util.refreshInterfaces,
            cls: 'float-button-1',            
            scope : Ung.Alpaca.Util
        },{
            xtype : 'button',
            text : this._( "External Aliases" ),
            cls: 'float-button-2',
            handler : this.externalAliases.createDelegate( this )
        },{
            html:'<br/>'
        }]

        for ( var c = 0 ; c < this.settings.config_list.length ; c++ ) {
            var config = this.settings.config_list[c];
            var interfaceConfig = config["interface"];
            items.push({
                xtype : "label",
                cls : 'label-section-heading-2',
                html : String.format( this._( "{0} Interface" ), interfaceConfig["name"] )
            });

            if ( interfaceConfig["wan"] ) {
                items.push( this.buildWanPanel( c ));
            } else {
                items.push( this.buildStandardPanel( c ));
            }
        }

        Ext.apply( this, {
            defaults : {
                xtype : "fieldset"
            },
            items : items
        });

        this.confirmMessage = this._( "These settings are critical to proper network operation and you should be sure these are the settings you want. Your Untangle Client may be logged out." );
        
        Ung.Alpaca.Pages.Network.Index.superclass.initComponent.apply( this, arguments );
    },

    saveMethod : "/network/set_settings",
    
    buildWanPanel : function( i )
    {
        var staticPanel = {
            cls:'left-indent-3',                                                    
            items : [{
                defaults : {
                    xtype : 'textfield',
                    itemCls:'label-width-1'
                        
                },
                items : [{
                    fieldLabel : this._( "Address" ),
                    name : this.generateName( "config_list", i, "static.ip" ),
                    vtype : "ipAddress",
                },{
                    xtype : "combo",
                    fieldLabel : this._( "Netmask" ),
                    name : this.generateName( "config_list", i, "static.netmask" ),
                    store : Ung.Alpaca.Util.cidrData,
                    listWidth : 140,
                    width : 40,
                    triggerAction : "all",
                    mode : "local",
                    editable : false                                        
                },{
                    fieldLabel : this._( "Default Gateway" ),
                    name : this.generateName( "config_list", i, "static.default_gateway" ),
                    allowBlank : false,
                    vtype : "ipAddress"
                },{
                    fieldLabel : this._( "Primary DNS Server" ),
                    name : this.generateName( "config_list", i, "static.dns_1" ),
                    allowBlank : false,
                    vtype : "ipAddress"
                },{
                    fieldLabel : this._( "Secondary DNS Server" ),
                    name : this.generateName( "config_list", i, "static.dns_2" ),
                    allowBlank : true
                }]
            }]
        };

        var dynamicPanel = {
            cls:'left-indent-3',                                    
            items : [{
                defaults : {
                    xtype : 'textfield',
                    readOnly : true
                },
                items : [{
                    xtype : 'button',
                    text : this._( "Renew Lease" ),
                    handler : this.onRenewLease,
                    scope : this
                },{
                    fieldLabel : this._( "Address" ),
                    name : "dhcp_status.ip"
                },{
                    fieldLabel : this._( "Netmask" ),
                    name : "dhcp_status.netmask"
                },{
                    fieldLabel : this._( "Default Gateway" ),
                    name : "dhcp_status.default_gateway"
                },{
                    fieldLabel : this._( "Primary DNS Server" ),
                    name : "dhcp_status.dns_1"
                },{
                    fieldLabel : this._( "Secondary DNS Server" ),
                    name :  "dhcp_status.dns_2"
                }]
            }]
        };

        var pppoePanel = {
            cls:'left-indent-3',                                    
            items : [{
                defaults : {
                    xtype : 'textfield'
                },
                items : [{
                    xtype : 'button',
                    text : this._( "Renew Lease" ),
                    handler : this.onRenewLease,
                    scope : this
                },{
                    fieldLabel : this._( "Username" ),
                    name : this.generateName( "config_list", i, "pppoe.username" )
                },{
                    fieldLabel : this._( "Password" ),
                    name : this.generateName( "config_list", i, "pppoe.password" )
                },{
                    xtype : "checkbox",
                    fieldLabel : this._( "User peer DNS" ),
                    name : this.generateName( "config_list", i, "pppoe.use_peer_dns" )
                },{
                    fieldLabel : this._( "Primary DNS Server" ),
                    name : this.generateName( "config_list", i, "pppoe.dns_1" ),
                    vtype : "ipAddress",
                    allowBlank : true
                },{
                    fieldLabel : this._( "Secondary DNS Server" ),
                    name : this.generateName( "config_list", i, "pppoe.dns_2" ),
                    vtype : "ipAddress",
                    allowBlank : true
                }]
            }]
        };

        var configTypes = [ "static", "dynamic", "pppoe" ];
        var configType = this.settings.config_list[i]["interface"]["config_type"];

        var switchBlade = new Ext.Panel({
            layout : "card",
            activeItem : this.getActiveItem( configType, configTypes ),
            border : false,
            defaults : {
                border : false,
                layout : 'form',
                xtype : 'panel',
                defaults : {
                    autoHeight : true,
                    xtype : 'fieldset'
                }
            },
            items : [ staticPanel, dynamicPanel, pppoePanel ]
        });

        var panel = new Ext.FormPanel({
            border : false,
            items : [{
                xtype : "fieldset",
                autoHeight : true,
                items : [{
                    xtype : "combo",
                    name : this.generateName( "config_list", i, "interface.config_type" ),
                    fieldLabel : this._( "Config Type" ),
                    store : configTypes,
                    switchBlade : switchBlade,
                    triggerAction : "all",
                    mode : "local",
                    editable : false,
                    listeners : {
                        "select" : {
                            fn : this.onSelectConfigType,
                            scope : this
                        }
                    }
                }],
            }, switchBlade ]
        });

        return panel;
    },

    buildStandardPanel : function( i )
    {
        var staticPanel = {
            items : [{
                defaults : {
                    xtype : 'textfield'
                },
                items : [{
                    fieldLabel : this._( "Address" ),
                    name : this.generateName( "config_list", i, "static.ip" ),
                    vtype : "ipAddress",
                    allowBlank : false
                },{
                    xtype : "combo",
                    fieldLabel : this._( "Netmask" ),
                    name : this.generateName( "config_list", i, "static.netmask" ),
                    store : Ung.Alpaca.Util.cidrData,
                    listWidth : 140,
                    width : 40,
                    triggerAction : "all",
                    mode : "local",
                    editable : false
                }]
            }]
        };

        var bridgePanel = {
            cls:'left-indent-3',                                    
            items : [{
                items : [{
                    fieldLabel : this._( "Bridge To" ),
                    xtype : "combo",
                    mode : "local",
                    triggerAction : "all",
                    editable : false,
                    listWidth : 160,
                    name : this.generateName( "config_list", i, "bridge" ),
                    store :  this.settings.config_list[i]["bridgeable_interfaces_v2"]
                }]
            }]
        };

        var configTypes = [ "static", "bridge" ];
        var configType = this.settings.config_list[i]["interface"]["config_type"];

        var switchBlade = new Ext.Panel({
            layout : "card",
            activeItem : this.getActiveItem( configType, configTypes ),
            border : false,
            defaults : {
                border : false,
                layout : 'form',
                xtype : 'panel',
                defaults : {
                    autoHeight : true,
                    xtype : 'fieldset'
                }
            },
            items : [ staticPanel, bridgePanel ]
        });

        var panel = new Ext.FormPanel({
            border : false,
            items : [{
                xtype : "fieldset",
                autoHeight : true,
                items : [{
                    xtype : "combo",
                    name : this.generateName( "config_list", i, "interface.config_type" ),
                    fieldLabel : this._( "Config Type" ),
                    store : configTypes,
                    switchBlade : switchBlade,
                    triggerAction : "all",
                    editable : false,
                    listeners : {
                        "select" : {
                            fn : this.onSelectConfigType,
                            scope : this
                        }
                    }
                }],
            }, switchBlade ]
        });

        return panel;
    },

    externalAliases : function()
    {
        application.switchToQueryPath( "/alpaca/network/aliases" );
    },

    generateName : function( prefix, i, suffix )
    {
        return prefix + "." + i + "." + suffix;
    },

    onSelectConfigType : function( combo, record, index )
    {
        combo.switchBlade.layout.setActiveItem( index );
    },

    getActiveItem : function( value, valueArray )
    {
        for ( var c = 0 ; c < valueArray.length ; c++ ) {
            if ( value == valueArray[c] ) return c;
        }

        return 0;
    },

    onRenewLease : function()
    {
        /* Refresh just saves settings, doesn't warn the user though, because that looks bad */
        this.confirmMessage = null;
        
        /* Update all of the save messages so it looks normal. */
        this.saveConfig = {
            waitTitle : this._( "Please Wait" ),
            waitMessage : this._( "Renewing Lease" ),
            successTitle : this._( "Lease Updated" ),
            successMessage : this._( "Attempt to update lease has been completed." ),
            errorTitle : this._( "Internal Error" ),
            errorMessage : this._( "Unable to renew lease" )

        };
        application.onSave();
    }
});

Ung.Alpaca.Pages.Network.Index.settingsMethod = "/network/get_settings";
Ung.Alpaca.Glue.registerPageRenderer( "network", "index", Ung.Alpaca.Pages.Network.Index );

