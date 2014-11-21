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
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet


class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

        # add a VLAN map table 
        # format: {'vlanID':[(port1,dpid1),(port2,dpid2),...]}
        self.vlan_map = {'10':[(2,1),(1,1),
                           (2,3),(3,3),(4,3),
			   (5,4)],
                         '20':[(2,4),(3,4),(4,4),
                           (5,3)]}
        self.trunk_map = {'10':[(1,3),(1,4)],
                          '20':[(1,3),(1,4)]}

        # populate edgeList containing edge ports
        self.edgeList = list()
        for x in self.vlan_map:
            for y in self.vlan_map[x]:
                if y[0] not in self.edgeList:
                    self.edgeList.append(y[0])

    def getVLAN(self,port,dpid):
        self.logger.info("getVLAN called port = %s dpid = %s",port,dpid)

        for vlan,list in self.vlan_map.items():
            if (port,dpid) in list:
                return vlan
        return 1

    def getPORTS(self,vlanID,dpid):
        self.logger.info("getPORTS called vlanID = %s dpid = %s",vlanID,dpid)
        access=[x[0] if x[1]==dpid else 0 for x in self.vlan_map[vlanID]]
        trunk=[x[0] if x[1]==dpid else 0 for x in self.trunk_map[vlanID]]
        ports=access+trunk
        while 0 in ports: ports.remove(0)
        return ports

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        # install table-miss flow entry
        #
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
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

        #obtain vlan from vlan_map
        vlan = str(self.getVLAN(in_port,dpid))
        self.mac_to_port.setdefault(vlan, {})
        self.mac_to_port[vlan].setdefault(dpid, {})
        
        self.logger.info("packet in %s src:%s dst:%s p:%s vlan:%s", dpid, src, dst, in_port,vlan)
        #self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # learn a mac address to avoid FLOOD next time.
        #self.logger.info("add in_port: %s in mac_to_port[%s][%s][%s]", in_port,vlan,dpid,src)
        self.mac_to_port[vlan][dpid][src] = in_port

        if dst in self.mac_to_port[vlan][dpid]:
            self.logger.info("found %s in mac_to_port[%s][%s]",dst,vlan,dpid)
            floodOut = False
            out_port = self.mac_to_port[vlan][dpid][dst]
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
        else:
            floodOut = True
            actions = []
            out_port = []
            if vlan is '1':
                out_port = ofproto.OFPP_FLOOD
                actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
            #out_port = ofproto.OFPP_FLOOD
            else:
                self.logger.warning(str(self.getPORTS(vlan,dpid)))
                for x in self.getPORTS(vlan,dpid):
                    actions.append(datapath.ofproto_parser.OFPActionOutput(x))

        #actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
