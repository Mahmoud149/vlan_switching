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
from ryu.lib.packet import packet,vlan
from ryu.lib.packet import ethernet
VLAN_TAG_802_1Q = 0x8100
VLAN = vlan.vlan.__name__
ETHERNET = ethernet.ethernet.__name__
class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        # add a VLAN map table 
        # format: {'vlanID':[(port1,dpid1),(port2,dpid2),...]}
        self.vlan_map = {10:[(2,1),(1,1),
                           (2,3),(3,3),(4,3),
			               (5,4)],
                         20:[(2,4),(3,4),(4,4),
                           (5,3)]}
        self.trunk_map = {10:[(1,3),(1,4),(1,1),(2,1),(1,2),(2,2)],
                          20:[(1,3),(1,4)]}
        # populate edges containing edge ports
        self.edges=self.getEdges()

    def getEdges(self):
        edges = [(pt,id) for vlan in self.vlan_map.values() for (pt,id) in vlan]
        return list(set(edges))
        
    def getVlan(self,port,dpid):
        for vlan,list in self.vlan_map.items():
            if (port,dpid) in list:  return vlan
        return 1

#<<<<<<< HEAD
    def getPorts(self,map,vlanID,dpid):
        ports=[port if id==dpid else 0 for (port,id) in map[vlanID]]
        '''=======
        def getPORTS(self,vlanID,dpid):
        self.logger.info("getPORTS called vlanID = %s dpid = %s",vlanID,dpid)
        access=[x[0] if x[1]==dpid else 0 for x in self.vlan_map[vlanID]]
        trunk=[x[0] if x[1]==dpid else 0 for x in self.trunk_map[vlanID]]
        ports=access+trunk
        >>>>>> parent of 51315fa... Not working yet. Gotta fix flooding on vlan trunk'''
        while 0 in ports: ports.remove(0)
        return ports

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        OF = datapath.ofproto
        parser = datapath.ofproto_parser
        # install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(OF.OFPP_CONTROLLER,OF.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, write=None,buffer_id=None):
        OF = datapath.ofproto
        parser = datapath.ofproto_parser
        inst=[]
        if len(actions)>0: inst.append(parser.OFPInstructionActions(OF.OFPIT_APPLY_ACTIONS,actions))
        if write is not None:inst.append(parser.OFPInstructionActions(OF.OFPIT_WRITE_ACTIONS,write))
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                        priority=priority, match=match,instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        print inst
        #self.logger.info("flow_mod match: %s action: %s", str(match),str(inst))
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        pkt = packet.Packet(msg.data)
        header = dict((p.protocol_name, p) for p in pkt.protocols if type(p) != str)
        
        datapath = msg.datapath
        OF,parser = datapath.ofproto,datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id
        vlan = self.getVlan(in_port,dpid)
        actions=[]
        Wactions=[]
        match = parser.OFPMatch()
        eth = header[ETHERNET]
        dst,src = eth.dst,eth.src
        #Pop Vlan Tag if necessary        
        if VLAN in header: 
            vlan=header[VLAN].vid
            vlan=vlan-vlan%2#get even vlans
            print ("Vlan in the HEADER %s src: %s dst: %s P: %s V: %s", dpid, src, dst,in_port, vlan)           
        #self.logger.info("packet in %s src: %s dst: %s P: %s V: %s", dpid, src, dst,in_port, vlan)
        self.mac_to_port.setdefault(dpid, {})
        if vlan is not 1:
            access_ports=self.getPorts(self.vlan_map,vlan,dpid)
            trunk_ports=self.getPorts(self.trunk_map,vlan,dpid)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port
        self.logger.info("packet in %s src: %s dst: %s P: %s V: %s", dpid, src, dst,in_port, vlan)
        if dst in self.mac_to_port[dpid]:
            #self.logger.info("found %s in mac_to_port[%s][%s]",dst,vlan,dpid)
            floodOut = False
            out_port = self.mac_to_port[dpid][dst]           
            self.logger.info("packet known %s P: %s V: %s", dpid, out_port, vlan)
            if vlan is 1:
                Wactions.append(parser.OFPActionOutput(out_port))
            elif out_port in trunk_ports:
                Wactions.append(parser.OFPActionOutput(out_port))
                self.logger.info("Pushing Vlan Tag %s, dpid:%s,src:%s,dst:%s", vlan, dpid,src, dst)
                field=parser.OFPMatchField.make(OF.OXM_OF_VLAN_VID,vlan)
                actions.append(parser.OFPActionPushVlan(VLAN_TAG_802_1Q))
                actions.append(parser.OFPActionSetField(field))
            elif out_port in access_ports:
                Wactions.append(parser.OFPActionOutput(out_port))
            
        else:
            floodOut = True
            actions = []
            out_port = []
            if vlan is 1:
                out_port = OF.OFPP_FLOOD
                Wactions.append(parser.OFPActionOutput(out_port))
            else:
                out_port=list(set(access_ports+trunk_ports)-set([in_port]))
                #self.logger.warning(str(self.getPorts(self.vlan,dpid)))
                for x in out_port:
                    Wactions.append(datapath.ofproto_parser.OFPActionOutput(x))

        #actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if not floodOut:
            if VLAN in header:
                print ("About to POP VLAN in %s src: %s dst: %s P: %s V: %s", dpid, src, dst,in_port, vlan)
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst,vlan_vid=vlan)
                actions.append(parser.OFPActionPopVlan())
                #match.set_vlan_vid_masked(vlan,((1 << 16) - 2))
            else:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            #actions.append(parser.OFPActionPopVlan())
            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
            if msg.buffer_id != OF.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, write=Wactions,buffer_id=msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions,write=Wactions)
        #self.logger.info("packet out %s P: %s V: %s", dpid, out_port, vlan)
        data = None
        if msg.buffer_id == OF.OFP_NO_BUFFER:
            data = msg.data
        actions=actions+Wactions
        out = parser.OFPPacketOut(datapath=datapath,in_port=in_port, buffer_id=msg.buffer_id, actions=actions, data=data)
        datapath.send_msg(out)






