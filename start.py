#!/usr/bin/python
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.node import Controller, RemoteController,UserSwitch,OVSBridge
from mininet.log import setLogLevel
from mininet.link import TCLink,Intf
from mininet.cli import CLI
from mininet.topo import Topo

class CustomTopo(Topo):
    "Simple Data Center Topology"

    "linkopts - (1:core, 2:ToR, 3: access) parameters"
    "fanout - number of child switch per parent switch"
    def __init__(self, linkopts1={}, linkopts2={}, access_fanout=2, host_fanout=2, **opts):
        # Initialize topology and default options
        Topo.__init__(self, **opts)

        # Add your logic here ...
        self.access_fanout = access_fanout
        self.host_fanout = host_fanout

        # Create counters for Agg,Edge,Host
        counterAgg = 0
        counterEdge = 0
        counterHost = 0
	switchcount=2

        # Create Aggregate Switch
        c2 = self.addSwitch('dumb',dpid="0000000001",cls=UserSwitch)
        bridge = self.addSwitch('bridge',dpid="0000000002",cls=OVSBridge)
        # Create Tree of Switches and Hosts
        for i in range(1,access_fanout+1):
        	counterEdge += 1
                switchcount += 1
        	edgeSwitch = self.addSwitch('edge%s'%counterEdge,dpid="00000000000"+`switchcount`,cls=UserSwitch)
        	self.addLink(edgeSwitch,bridge,**linkopts1)
                for j in range(1,host_fanout+1):
                    counterHost += 1
       	            host = self.addHost('h%s'%counterHost)
       	            self.addLink(host,edgeSwitch,**linkopts2)
                    
topos = { 'custom': ( lambda: CustomTopo() ) }

setLogLevel('info')
linkopts1 = {'bw':50}
linkopts2 = {'bw':30}

topo = CustomTopo(linkopts1, linkopts2, access_fanout=2,host_fanout=4)

net = Mininet(topo=topo, link=TCLink,
   controller=lambda name: RemoteController( name, ip='127.0.0.1' ),listenPort=6633)
net.start()
net.pingAll()
CLI(net)

