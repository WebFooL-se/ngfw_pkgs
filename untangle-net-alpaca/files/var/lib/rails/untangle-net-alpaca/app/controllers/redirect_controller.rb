#
# $HeadURL$
# Copyright (c) 2007-2008 Untangle, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License, version 2,
# as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# AS-IS and WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE, TITLE, or
# NONINFRINGEMENT.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
class RedirectController < ApplicationController  
  def get_settings
    settings = {}
    settings["user_redirects"] = Redirect.find( :all, :conditions => [ "system_id IS NULL" ] )

    ## We do not use system redirects.
    settings["system_redirects"] = Redirect.find( :all, :conditions => [ "system_id IS NOT NULL" ] )

    json_result( settings )
  end

  def set_settings
    s = json_params

    ## Destroy all of the user rules
    Redirect.destroy_all( "system_id IS NULL" )
    position = 0
    s["user_redirects"].each do |entry|
      rule = Redirect.new( entry )
      rule.position = position
      rule.save
      position += position
    end
    
    s["system_redirects"].each do |entry|
      rule = Redirect.find( :first, :conditions => [ "system_id = ?", entry["system_id"]] )
      next if rule.nil?
      rule.enabled = entry["enabled"]
      rule.save
    end

    ## Commit all of the packet filter rules.
    os["packet_filter_manager"].commit
    
    json_result    
  end

  alias_method :index, :extjs

  def manage
    @redirects = Redirect.find( :all, :conditions => [ "system_id IS NULL" ] )
    @system_redirect_list = Redirect.find( :all, :conditions => [ "system_id IS NOT NULL" ] )

    render :action => 'manage'
  end

  def create_redirect
    ## Reasonable defaults
    @redirect = Redirect.new( :enabled => true, :position => -1, :description => "", :filter => "d-port::&&d-local::true&&protocol::tcp" )
  end

  def edit
    @row_id = params[:row_id]
    raise "unspecified row id" if @row_id.nil?
    
    @redirect = Redirect.new
    @redirect.description = params[:description]
    @redirect.new_ip = params[:new_ip]
    @redirect.new_enc_id = params[:new_enc_id]
    @redirect.enabled = params[:enabled]

    ## Create a copy of the filter types, and remove the source port
    @interfaces, @parameter_list = RuleHelper::get_edit_fields( params )
    
    @filter_types = RedirectHelper::filter_types
  end

  def save
    ## Review : Internationalization
    if ( params[:commit] != "Save".t )
      redirect_to( :action => "manage" ) 
      return false
    end

    save_user_rules

    save_system_rules

    ## Commit all of the packet filter rules.
    os["packet_filter_manager"].commit

    ## Review : should have some indication that is saved.
    redirect_to( :action => "manage" )
  end

  def scripts
    RuleHelper::Scripts
  end

  private
  
  def save_user_rules
    redirect_list = []
    redirects = params[:redirects]
    enabled = params[:enabled]
    filters = params[:filters]
    description = params[:description]
    new_ip = params[:new_ip]
    new_enc_id = params[:new_enc_id]

    position = 0
    unless redirects.nil?
      redirects.each do |key|
        redirect = Redirect.new
        redirect.enabled, redirect.filter, redirect.system_id = enabled[key], filters[key], nil
        redirect.new_ip, redirect.new_enc_id = new_ip[key], new_enc_id[key]
        redirect.description, redirect.position, position = description[key], position, position + 1
        redirect_list << redirect
      end
    end

    ## Delete all of the non-system rules
    Redirect.destroy_all( "system_id IS NULL" )
    redirect_list.each { |redirect| redirect.save }
  end

  def save_system_rules
    rules = params[:system_redirects]
    system_ids = params[:system_system_id]
    enabled = params[:system_enabled]
    
    unless rules.nil?
      rules.each do |key|
        ## Skip anything with an empty or null key.
        next if ApplicationHelper.null?( key )

        redirect = Redirect.find( :first, :conditions => [ "system_id = ?", key ] )
        next if redirect.nil?
        redirect.enabled = enabled[key]
        redirect.save
      end
    end

  end
end
