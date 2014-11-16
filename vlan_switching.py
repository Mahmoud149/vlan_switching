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


class SimpleSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

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

    def getVLAN(self,port,dpid):
        for vlan,list in self.vlan_map.items():
            if (port,dpid) in list:
                return vlan
        return 1

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

    def add_flow(self, vlan,datapath, in_port, dst, actions):
        ofproto = datapath.ofproto

        match = datapath.ofproto_parser.OFPMatch(
            in_port=in_port, dl_dst=haddr_to_bin(dst))

        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto

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


        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[vlan][dpid][src] = msg.in_port

        if dst in self.mac_to_port[vlan][dpid]:
            out_port = self.mac_to_port[vlan][dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            # Need to modify this code
            self.add_flow(vlan,datapath, msg.in_port, dst, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

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
