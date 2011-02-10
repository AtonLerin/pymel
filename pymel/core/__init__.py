"The primary module for maya commands and node classes"

import sys
import pymel as _pymel
_pymel.core = sys.modules[__name__]
import pymel.versions as _versions
import pymel.internal.startup as _startup
import pymel.internal as _internal

# will check for the presence of an initilized Maya / launch it
_startup.mayaInit()

import pymel.internal.factories as _factories
import pymel.internal.pmcmds as _pmcmds
_pmcmds.addAllWrappedCmds()

import pymel.api as _api
import pymel.api.plugins as _plugins
from general import *
from context import *
from system import *
from windows import *
from animation import *
from effects import *
from modeling import *
from rendering import *
from language import *
from other import *

# to allow lazy loading, we avoid import *
import nodetypes
import nodetypes as nt
import datatypes
import datatypes as dt
import uitypes
import uitypes as ui

import runtime

import maya.cmds as cmds

# these modules are imported anyway so they should not be a performance hit
import pymel.util as util
import pymel.api as api

_logger = _internal.getLogger(__name__)

#: dictionary of plugins and the nodes and commands they register
_pluginData = {}

_module = sys.modules[__name__]

def _addPluginCommand(pluginName, funcName):
    global _pluginData
    
    if funcName not in _pluginData[pluginName].setdefault('commands', []):
        _pluginData[pluginName]['commands'].append(funcName)
    #_logger.debug("adding new command:", funcName)
    _factories.cmdlist[funcName] = _factories.cmdcache.getCmdInfoBasic( funcName )
    _pmcmds.addWrappedCmd(funcName)
    func = _factories.functionFactory( funcName )
    try:
        if func:
            setattr( _module, funcName, func )
            if 'pymel.all' in sys.modules:
                setattr( sys.modules['pymel.all'], funcName, func )
        else:
            _logger.warning( "failed to create function" )
    except Exception, msg:
        _logger.warning("exception: %s" % str(msg) )
        
def _addPluginNode(pluginName, mayaType):
    global _pluginData
    
    if mayaType not in _pluginData[pluginName].setdefault('dependNodes', []):
        _pluginData[pluginName]['dependNodes'].append(mayaType)    
    _logger.debug("Adding node: %s" % mayaType)
    extraAttrs = _plugins.pyNodeMethods.get(pluginName, {}).get(mayaType, {})
    _factories.addCustomPyNode(nodetypes, mayaType, extraAttrs=extraAttrs)
    

def _removePluginCommand(pluginName, command):
    global _pluginData

    commands = _pluginData.get(pluginName, {}).get('commands', [])
    if command in commands:
        commands.remove(command)
    try:
        _pmcmds.removeWrappedCmd(command)
        _module.__dict__.pop(command, None)
    except KeyError:
        _logger.warn( "Failed to remove %s from module %s" % (command, _module.__name__) )

def _removePluginNode(pluginName, node):
    global _pluginData

    nodes = _pluginData.get(pluginName, {}).get('dependNodes', [])
    if node in nodes:
        nodes.remove(node)
    _factories.removePyNode( nodetypes, node )
    

def _pluginLoaded( *args ):
    global _pluginData
    
    if len(args) > 1:
        # 2009 API callback, the args are ( [ pathToPlugin, pluginName ], clientData )
        pluginName = args[0][1]
    else:
        pluginName = args[0]

    if not pluginName:
        return

    _logger.debug("Plugin loaded: %s", pluginName)
    _pluginData[pluginName] = {}

    try:
        commands = _pmcmds.pluginInfo(pluginName, query=1, command=1)
    except:
        _logger.error("Failed to get command list from %s", pluginName)
        commands = None

    # Commands
    if commands:
        # clear out the command list first
        _pluginData[pluginName]['commands'] = []
        for funcName in commands:
            _addPluginCommand(pluginName, funcName) 

    # Nodes
    try:
        mayaTypes = cmds.pluginInfo(pluginName, query=1, dependNode=1)
    except:
        _logger.error("Failed to get depend nodes list from %s", pluginName)
        mayaTypes = None
    #apiEnums = cmds.pluginInfo(pluginName, query=1, dependNodeId=1)
    if mayaTypes :
        def addPluginPyNodes(*args):
            try:
                id = _pluginData[pluginName]['callbackId']
                if id is not None:
                    _api.MEventMessage.removeCallback( id )
                    if hasattr(id, 'disown'):
                        id.disown()
            except KeyError:
                _logger.warning("could not find callback id!")

            _pluginData[pluginName]['dependNodes'] = []
            allTypes = set(cmds.ls(nodeTypes=1))
            for mayaType in mayaTypes:
                # make sure it's a 'valid' type - some plugins list node types
                # that don't show up in ls(nodeTypes=1), and aren't creatable
                # ...perhaps they're abstract types?
                # Unfortunately, can't check this, as only plugin I know of
                # that has such a node - mayalive, mlConstraint - is only
                # available up to 2009, which has a bug with allNodeTypes...
                # Oddly enough, mlConstraint WILL show up in allTypes here,
                # but not after the plugin is loaded / callback finishes...?
                if mayaType not in allTypes:
                    continue
                _addPluginNode(pluginName, mayaType)
                _logger.debug("Adding node: %s" % mayaType)

        # evidently isOpeningFile is not avaiable in maya 8.5 sp1.  this could definitely cause problems
        if _api.MFileIO.isReadingFile() or ( _versions.current() >= _versions.v2008 and _api.MFileIO.isOpeningFile() ):
            _logger.debug("Installing temporary plugin-loaded callback")
            id = _api.MEventMessage.addEventCallback( 'SceneOpened', addPluginPyNodes )
            _pluginData[pluginName]['callbackId'] = id
            # scriptJob not respected in batch mode, had to use _api
            #cmds.scriptJob( event=('SceneOpened',doSomethingElse), runOnce=1 )
        else:
            # add the callback id as None so that if we fail to get an id in addPluginPyNodes we know something is wrong
            _pluginData[pluginName]['callbackId'] = None
            addPluginPyNodes()



def _pluginUnloaded(*args):
    global _pluginData

    if len(args) > 1:
        # 2009 API callback, the args are
        # ( [ pluginName, pathToPlugin ], clientData )  OR
        # ( [ pathToPlugin ], clientData )
        pluginName = args[0][0]
    else:
        pluginName = args[0]

    _logger.debug("Plugin unloaded: %s" % pluginName)
    
    try:
        data = _pluginData.pop(pluginName)
    except KeyError:
        pass
    else:
        # Commands
        commands = data.pop('commands', [])
        if commands:
            _logger.debug("Removing commands: %s", ', '.join( commands ))
            for command in commands:
                _removePluginCommand(pluginName, command)

        # Nodes
        nodes = data.pop('dependNodes', [])
        if nodes:
            _logger.debug("Removing nodes: %s" % ', '.join( nodes ))
            for node in nodes:
                _removePluginNode(pluginName, node)


global _pluginLoadedCB
global _pluginUnloadedCB
_pluginLoadedCB = None
_pluginUnloadedCB = None

def _installCallbacks():
    """install the callbacks that trigger new nodes and commands to be added to pymel when a
    plugin loads.  This is called from pymel.__init__
    """

    global _pluginLoadedCB
    if _pluginLoadedCB is None:
        _pluginLoadedCB = True
        _logger.debug("Adding pluginLoaded callback")
        #_pluginLoadedCB = pluginLoadedCallback(module)


        if _versions.current() >= _versions.v2009:
            id = _api.MSceneMessage.addStringArrayCallback( _api.MSceneMessage.kAfterPluginLoad, _pluginLoaded  )
            if hasattr(id, 'disown'):
                id.disown()
        else:
            # BUG: this line has to be a string, because using a function causes a 'pure virtual' error every time maya shuts down
            cmds.loadPlugin( addCallback='import pymel.core; pymel.core._pluginLoaded("%s")' )
    else:
        _logger.debug("PluginLoaded callback already exists")

    global _pluginUnloadedCB
    if _pluginUnloadedCB is None:
        _pluginUnloadedCB = True

        # BUG: autodesk still has not add python callback support, and calling this as MEL is not getting the plugin name passed to it
        #mel.unloadPlugin( addCallback='''python("import pymel; pymel._pluginUnloaded('#1')")''' )

        if _versions.current() >= _versions.v2009:
            _logger.debug("Adding pluginUnloaded callback")
            id = _api.MSceneMessage.addStringArrayCallback( _api.MSceneMessage.kAfterPluginUnload, _pluginUnloaded )
            if hasattr(id, 'disown'):
                id.disown()


    else:
        _logger.debug("PluginUnloaded callback already exists")

    # add commands and nodes for plugins loaded prior to importing pymel
    preLoadedPlugins = cmds.pluginInfo( q=1, listPlugins=1 )
    if preLoadedPlugins:
        _logger.info("Updating pymel with pre-loaded plugins: %s" % ', '.join( preLoadedPlugins ))
        for plugin in preLoadedPlugins:
            _pluginLoaded( plugin )

_installCallbacks()

# run userSetup.py / initialize MEL...
# ...userStartup.py / .mel may try to add plugins and then use their commands /
# nodes with pymel... so do the plugin stuff first
_startup.finalize()




