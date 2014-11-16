#!/usr/bin/python
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.node import Controller, RemoteController
from mininet.log import setLogLevel
from mininet.link import TCLink
from CustomTopo import *
from mininet.cli import CLI

setLogLevel('info')
linkopts1 = {'bw':50}
linkopts2 = {'bw':30}

topo = CustomTopo(linkopts1, linkopts2, access_fanout=2,host_fanout=4)

net = Mininet(topo=topo, link=TCLink,
   controller=lambda name: RemoteController( name, ip='127.0.0.1' ),listenPort=6633)
net.start()
CLI(net)
