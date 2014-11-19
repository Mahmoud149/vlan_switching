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

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet,ethernet
import time

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        DP = ev.msg.datapath
        OF = DP.ofproto
        parser = DP.ofproto_parser
	self.logger.info("Someone is connecting")
        # install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(OF.OFPP_CONTROLLER,
                                          OF.OFPCML_NO_BUFFER)]
        self.add_flow(DP, 0, match, actions)
        #installs meter id=1 to remark flows over 10 Mbps
	self.add_Remark(DP,1,10000)	
        self.add_Table(DP,2)

    def add_flow(self, datapath, priority, match, actions, meter_id=None):
        ofproto = datapath.ofproto

        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                               actions)]
        if meter_id: 
         inst=[parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,actions),
                  parser.OFPInstructionMeter(1),parser.OFPInstructionGotoTable(2)]
        mod = parser.OFPFlowMod(datapath=datapath,priority=priority, match=match,
                                    instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self.add_flow(datapath, 1, match, actions,1)
        data = None

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def add_Table(self,dp, table_id):
        OF=dp.ofproto
        #create table 2 with default forwarding behavior
        parser=dp.ofproto_parser
#	mod = parser.OFPFlowMod(datapath=dp,table_id=table_id,priority=1)
#        dp.send_msg(mod)

        match = parser.OFPMatch(ip_dscp=0,eth_type=0x0800)
        field=parser.OFPMatchField.make(OF.OXM_OF_IP_DSCP, 2)
        ActNow=[parser.OFPActionSetField(field)]
        inst=[parser.OFPInstructionActions(OF.OFPIT_WRITE_ACTIONS,ActNow), parser.OFPInstructionMeter(1)]
        mod = parser.OFPFlowMod(datapath=dp,table_id=table_id,priority=2, match=match,
                                    instructions=inst)
        dp.send_msg(mod)

    def add_Remark(self,dp,vlan,bw):
        OF=dp.ofproto
        parser=dp.ofproto_parser
	burst_size=10000
        band=[]
        band.append( parser.OFPMeterBandDscpRemark( rate=self.get_BW(vlan,bw),
                                              burst_size=burst_size,prec_level=4) )
        meter_mod=parser.OFPMeterMod(datapath=dp,
                                     command=OF.OFPMC_ADD,
                                     flags=OF.OFPMF_KBPS,
                                     meter_id=self.get_Meter_Id(dp,vlan),bands=band)
        dp.send_msg(meter_mod)

    def get_BW(self,vlan,bw):
	return bw

    def get_Meter_Id(self,datapath,vlan):
	return vlan

