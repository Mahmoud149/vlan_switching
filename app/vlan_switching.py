# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
An OpenFlow 1.0 L2 learning switch implementationself.
"""

import logging
import struct

from ryu.base import app_manager
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet

# Added imports
from ryu.ofproto.ether import ETH_TYPE_8021Q



class SimpleSwitch(app_manager.RyuApp):
    # OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]
    # Change to OpenFlow 1.3
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch, self).__init__(*args, **kwargs)
        # mac_to_port = dict of VLAN : (port,dpid)
        self.mac_to_port = {}
        ################ ADDED CODES #################
        # add a VLAN map table, dict(vlanid:[port,dpid])
        self.vlan_map = {}
        # Hard-coded this 
        # {vlan: [(port,dpid)],....}
        self.vlan_map = {'10':[(2,2),(3,2),(2,3),(3,3)],
                         '20':[(4,2),(5,2),(4,3),(5,3)]}
        # Create a list of all edge ports
        self.edgeList = list()
                
        # Populate the edgeList 
        for x in self.vlan_map:
            for y in self.vlan_map[x]:
        	    if y[0] not in self.edgeList:
        		    self.edgeList.append(y[0])

    def getVLAN(self,port,dpid):
        for vlan,list in self.vlan_map.items():
            if (port,dpid) in list:
                return vlan
        return 1
        
    def getPORTS(self,vlanID,dpid):
        portList = list()
        for x in self.vlan_map[str(vlanID)]:
        	if x[1] == dpid:
        		portList.append(x[0])
        return portList

    def addVLAN(self,vlanID,port,dpid):
        if vlanID not in self.mac_to_port:
            self.mac_to_port[str(vlanID)] = [(port,dpid)]
        else:
            self.mac_to_port[str(vlanID)].append((port,dpid))

    def delVLAN(self,vlanID):
        self.mac_to_port.pop(str(vlanID))

#    def getPorts(self,vlan,dpid):
    	# Get all the ports that belong to the VLAN in the switch
#        pass
        ##############################################

    def add_flow(self, vlan,datapath, in_port, dst, ActNow, actions):
        ofproto = datapath.ofproto

        match = datapath.ofproto_parser.OFPMatch(
            in_port=in_port, dl_dst=haddr_to_bin(dst))

        inst=[parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,ActNow),
             parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,actions)]

        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY, 
            flags=ofproto.OFPFF_SEND_FLOW_REM,instructions=inst)

        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        #self.mac_to_port.setdefault(vlan_id, {})

        #Find VLAN associated with port and dpid
        vlan = str(self.getVLAN(msg.in_port,dpid))
        self.mac_to_port.setdefault(vlan, {})
        self.mac_to_port[vlan].setdefault(dpid, {})
        
        #Include VLAN in print message
        self.logger.info("packet in DPID: %s SRC: %s DST: %s PORT: %s VLAN: %s", dpid, src, dst, msg.in_port, vlan)
        
        # Push or Pop VLAN tag
        self.logger.info("Pushing and Popping VLAN: %s", vlan)
        self.logger.info("Packet from PORT: %s", msg.in_port)

        # If incoming port is the edge port
        if msg.in_port in self.edgeList:
        	# Create a field and specify the vlandID
        	self.logger.info("This is an edge port, push vlanID %s",getVLAN(msg.in_port,dpid))
        	VLAN_TAG_802_1Q = 0x8100
        	field=parser.OFPMatchField.make(ofproto.OXM_OF_VLAN_VID, getVLAN(msg.in_port,dpid))
        	ActNow = [parser.OFPActionPushVlan(VLAN_TAG_802_1Q),parser.OFPActionSetField(field)]
        
        # If incoming port is not the edge port
        else:
        	self.logger.info("Not an edge port, pop vlanID")
        	ActNow =[parser.OFPActionPopVlan()]          


        #if (msg.inport,) in self.mac_to_port[vlan]


        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[vlan][dpid][src] = msg.in_port
        
        if dst in self.mac_to_port[vlan][dpid]:
        	floodOut = False
            out_port = self.mac_to_port[vlan][dpid][dst]
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
        else:
        	#Modify to flood packets only to nodes in the VLAN
            #out_port = ofproto.OFPP_FLOOD

            #create an action list and append to this list all the ports associated with the given VLAN
            floodOut = True
            actions = list()
            for x in self.mac_to_port[vlan]:
                actions.append(datapath.ofproto_parser.OFPActionOutput(x[0]))    

        #actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        # Modify some logics here since will not be using ofproto.OFPP_FLOOD

        if (out_port != ofproto.OFPP_FLOOD) and (!floodOut):
            # Need to modify add_flow to support vlan tag
            self.add_flow(vlan,datapath, msg.in_port, dst, ActNow,actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        

        #Send packet here ...
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions, data=data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no

        ofproto = msg.datapath.ofproto
        if reason == ofproto.OFPPR_ADD:
            self.logger.info("port added %s", port_no)
        elif reason == ofproto.OFPPR_DELETE:
            self.logger.info("port deleted %s", port_no)
        elif reason == ofproto.OFPPR_MODIFY:
            self.logger.info("port modified %s", port_no)
        else:
            self.logger.info("Illeagal port state %s %s", port_no, reason)
