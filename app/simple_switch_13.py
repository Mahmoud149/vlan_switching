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

import logging
import struct

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.ofp_event import EventOFPSwitchFeatures
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto.ofproto_v1_2 import OFPG_ANY
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.ofproto.ether import ETH_TYPE_8021Q


class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        # add a VLAN map table, dict(vlanid:[port,dpid])
        self.vlan_map = {}
        # Hard coded this
        # {str(vlan):[(port,dpid),...]}
        self.vlan_map = {'10':[(2,1),(1,2),(2,3),(3,3)],
                         '20':[(4,2),(5,2),(4,3),(5,3)]}
        # Populate EdgeList
        self.edgeList = list()
        for x in self.vlan_map:
            for y in self.vlan_map[x]:
                if y[0] not in self.edgeList:
                    self.edgeList.append(y[0])

    ########## Added Functions ##############
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
    #########################################
    
    @set_ev_cls(EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle switch features reply to install table miss flow entries."""
        datapath = ev.msg.datapath
        [self.install_table_miss(datapath, n) for n in [0, 1]]
    
    def install_table_miss(self, datapath, table_id):
        """Create and install table miss flow entries."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        empty_match = parser.OFPMatch()
        output = parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                        ofproto.OFPCML_NO_BUFFER)
        write = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                             [output])
        instructions = [write]
        flow_mod = datapath.ofproto_parser.OFPFlowMod(datapath, 0, 0, table_id,
                                                      ofproto.OFPFC_ADD, 0, 0,
                                                      0,
                                                      ofproto.OFPCML_NO_BUFFER,
                                                      ofproto.OFPP_ANY,
                                                      OFPG_ANY, 0,
                                                      empty_match, instructions)

	#self.create_flow_mod(datapath, 0, table_id,
        #                                empty_match, instructions)
        datapath.send_msg(flow_mod)

    def add_flow(self, datapath, port, dst, ActNow, actions):
        ofproto = datapath.ofproto

        match = datapath.ofproto_parser.OFPMatch(in_port=port,
                                                 eth_dst=dst)
        inst=[parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,ActNow),
              parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,actions)]

        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, cookie=0, cookie_mask=0, table_id=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=0, buffer_id=ofproto.OFP_NO_BUFFER,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            flags=0, match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        in_port = msg.match['in_port']
        parser = datapath.ofproto_parser


        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        ################ ADDED CODES #########################
        vlan = str(self.getVLAN(in_port,dpid))
        self.mac_to_port.setdefault(vlan, {})
        self.mac_to_port[vlan].setdefault(dpid, {})


        self.logger.info("packet in DPID:%s SRC:%s DST:%s PORT:%s VLAN:%s", dpid, src, dst, in_port,vlan)
        
        self.logger.info("VLAN PUSHING and POPPING, VLAN ID:%s",vlan)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[vlan][dpid][src] = in_port

        if dst in self.mac_to_port[vlan][dpid]:
            floodOut = False
            out_port = self.mac_to_port[vlan][dpid][dst]
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

        else:
            floodOut = True
            actions = list()
            out_port = []
            if vlan is '1':
                out_port = ofproto.OFPP_FLOOD
                actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
            else:

                self.logger.warning(str(self.getPORTS(vlan,dpid)))
                #out_port = ofproto.OFPP_FLOOD
                for x in self.getPORTS(vlan,dpid):
                    actions.append(datapath.ofproto_parser.OFPActionOutput(x))
                    #actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

        if out_port in self.edgeList:
            # Create a filed and specify the vlanID
            self.logger.info("This is an edge port, push vlanID %s",self.getVLAN(msg.in_port,dpid))
            VLAN_TAG_802_1Q = 0x8100
            field=parser.OFPMatchField.make(ofproto.OXM_OF_VLAN_VID, self.getVLAN(msg.in_port,dpid))
            ActNow = [parser.OFPActionPushVlan(VLAN_TAG_802_1Q),parser.OFPActionSetField(field)]
        else:
            #outport is not an edge port
            self.logger.info("Not an edge port, pop vlanID")
            ActNow = [parser.OFPActionPopVlan()]

        #actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if (out_port != ofproto.OFPP_FLOOD) and (not floodOut):
            self.add_flow(vlan,datapath, in_port, dst, ActNow,actions)

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port,
            actions=actions)
        datapath.send_msg(out)
