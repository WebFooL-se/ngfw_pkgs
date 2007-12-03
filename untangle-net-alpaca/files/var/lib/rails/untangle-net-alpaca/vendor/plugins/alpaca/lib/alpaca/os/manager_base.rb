class Alpaca::OS::ManagerBase
  include Alpaca::OS::Logging
    
  ## Override at your own risk
  def initialize
    ## Hash of all of the hooks.
    ## @@hooks[method_name] => a sorted array of the MethodHandles to invoke
    ## Methods at 0 are invoke right before the hook, methods at 1 are 
    ## invoked right after the hook
    @hooks = {}

    ## REVIEW: Since this is a singleton, this can lock the system
    ## If one of the managers registers a hook with itself.
    register_hooks
  end

  MethodPrefixRegex = /^hook_/

  class MethodHandler
    def initialize( index, manager, method_id )
      @index = index
      @manager = manager
      @method_id = method_id
    end
    
    def <=>( other )
      @index <=> other.index
    end

    attr_reader :index, :manager, :method_id
  end

  ## Override this method in order to register hooks.
  def register_hooks
  end

  ## Register a hook with this manager
  def register_hook( index, manager, hook_name, method_id )    
    ## Initialize the method array if necessary
    @hooks[hook_name] = [] if @hooks[hook_name].nil?

    hooks = @hooks[hook_name]

    ## Delete any duplicate entries
    hooks.delete_if { |handle| (( handle.manager == manager ) && ( handle.index == index )) }

    logger.debug( "Registering the hook: #{index}, #{manager}, '#{hook_name}' #{self.class.name}" )
    
    ## Append the method handle
    hooks << MethodHandler.new( index, manager, method_id )

    ## Sort so they are invoked in order (yes this is terribly inefficient)
    hooks.sort! { |x,y| x <=> y }
  end

  ## Remove all calls into a particular manager, useful for unregistering
  ## a currently installed manager.
  def self.remove_hook( manager )
    @hooks.each do |k,v|
      v.delete_if  { |handle| handle.manager == manager }
    end
  end

  ## This is the method that gets defined automatically
  def self.hook_method_lamba( hook_method_name, hook_method_id )
    lambda do |*args| 
      hooks = @hooks[hook_method_name]
      hooks = [] if hooks.nil?
      ## (invoke method)
      im = true
      response = nil
      hooks.each do |handler|
        ## run the method the first time index is greater than zero.
        response, im = send( hook_method_id, *args ), false if ( im && ( handler.index > 0 ))

        os[handler.manager].send( handler.method_id, *args )
      end

      ## Run the method if it hasn't been called before.
      response = send( hook_method_id, *args ), false if im
      
      ## Return the response from the hook
      response
    end
  end

  ## Define this last so that it doesn't hit the methods defined above
  def self.method_added( method_id )
    method_name = method_id.id2name
    return if MethodPrefixRegex.match( method_name ).nil?
    
    ## Strip the prefix
    method_name = method_name.sub( MethodPrefixRegex, "" )

    define_method( method_name, hook_method_lamba( method_name, method_id ))
  end

  private_class_method :hook_method_lamba, :method_added
end
