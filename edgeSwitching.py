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
        self.vlan_map = {10:[(2,1),(1,1),
                           (2,3),(3,3),(4,3),(5,4)],
                         20:[(2,4),(3,4),(4,4),(5,3)]}
        self.trunk_map = {10:[(1,3),(1,4),(1,1),(2,1),(1,2),(2,2)],
                          20:[(1,3),(1,4)]}
        # format: {dpid:{vlanID:meterID}}
        self.meter_map = {1: {10:1,20:2},
                          3: {10:1,20:2},
                          4: {10:1,20:2}}
        # bandwidth allocation based on each vlan                 
        self.bw = {10:1000,20:2000}

    # Handy function that lists all attributes in the given object    
    def ls(self,obj):
        print("\n".join([x for x in dir(obj) if x[0] != "_"]))

    def getEdges(self):
        edges = [(pt,id) for vlan in self.vlan_map.values() for (pt,id) in vlan]
        return list(set(edges))
    #FIXME 3 lines to get a vlan id?    
    def getVlan(self,port,dpid):
        for vlan,list in self.vlan_map.items():
            if (port,dpid) in list:  return vlan
        return 1
    def getMeterID(self,vlanID,dpid):
        if dpid not in self.meter_map: return 0
        if vlanID not in self.meter_map[dpid]: return 0
        return self.meter_map[dpid][vlanID]

    def add_DscpRemark(self,dp,vlan):
        OF,parser=dp.ofproto,dp.ofproto_parser
        self.logger.info("Installing meter %s on %s, rate is  %s", 
                                      self.getMeterID(vlan,dp.id), dp.id,self.bw[vlan] )
        band=[( parser.OFPMeterBandDscpRemark( rate=self.bw[vlan],burst_size=10,prec_level=4 ) )]
        meter_mod=parser.OFPMeterMod(datapath=dp,command=OF.OFPMC_ADD,flags=OF.OFPMF_KBPS,
                                     meter_id=self.getMeterID(vlan,dp.id),bands=band)
        dp.send_msg(meter_mod)    

    def getPorts(self,map,vlanID,dpid):
        #conditions for vlan=1
        ports=[port if id==dpid else 0 for (port,id) in map[vlanID]]
        while 0 in ports: ports.remove(0)
        return ports

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        #self.ls(ev.msg)
        datapath = ev.msg.datapath
        msg = ev.msg
        dpid = datapath.id
        OF,parser=datapath.ofproto,datapath.ofproto_parser
        # install table-miss flow entry
        #FIXME figureout what difference does a buffer make on the data structure
        actions = [parser.OFPActionOutput(OF.OFPP_CONTROLLER,OF.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, parser.OFPMatch(), actions)
        # Create DSCP Remark for each VLAN in the map
        for vlan in self.vlan_map:
            self.add_DscpRemark(datapath,vlan)

    def add_flow(self, datapath, priority, match, actions, write=None,buffer_id=None,meter_id=None):
        OF,parser=datapath.ofproto,datapath.ofproto_parser
        inst=[]
        if len(actions)>0: inst.append(parser.OFPInstructionActions(OF.OFPIT_APPLY_ACTIONS,actions))
        if write is not None:inst.append(parser.OFPInstructionActions(OF.OFPIT_WRITE_ACTIONS,write))
        if (meter_id is not None) and (meter_id != 0) : inst.append(parser.OFPInstructionMeter(meter_id))
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                        priority=priority, match=match,instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        #self.logger.info("flow_mod match: %s action: %s", str(match),str(inst))
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        if ev.msg.msg_len < ev.msg.total_len:self.logger.debug("packet truncated: only %s of %s bytes",ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        pkt = packet.Packet(msg.data)
        header = dict((p.protocol_name, p) for p in pkt.protocols if type(p) != str)
        datapath = msg.datapath
        OF,parser = datapath.ofproto,datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id
        vlan = self.getVlan(in_port,dpid)
        meterID =self.getMeterID(vlan,dpid)
        actions,Wactions=[],[]
        match = parser.OFPMatch()
        dst,src = header[ETHERNET].dst,header[ETHERNET].src      
        if VLAN in header: 
            vlan=header[VLAN].vid
            vlan=vlan-vlan%2#get even vlans
            #print ("Vlan in the HEADER %s src: %s dst: %s P: %s V: %s", dpid, src, dst,in_port, vlan)           
        #FIXME find a better way to debug the code
        #self.logger.info("packet in %s src: %s dst: %s P: %s V: %s", dpid, src, dst,in_port, vlan)
        self.mac_to_port.setdefault(dpid, {})
        if vlan is not 1:
            access_ports=self.getPorts(self.vlan_map,vlan,dpid)
            trunk_ports=self.getPorts(self.trunk_map,vlan,dpid)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port
        #self.logger.info("packet in %s src: %s dst: %s P: %s V: %s", dpid, src, dst,in_port, vlan)
        if dst in self.mac_to_port[dpid]:
            #self.logger.info("found %s in mac_to_port[%s][%s]",dst,vlan,dpid)
            floodOut = False
            out_port = self.mac_to_port[dpid][dst]           
            #self.logger.info("packet known %s P: %s V: %s", dpid, out_port, vlan)
            if vlan is 1:
                Wactions.append(parser.OFPActionOutput(out_port))
            elif out_port in trunk_ports:
                Wactions.append(parser.OFPActionOutput(out_port))
                if VLAN not in header:#Don't overlap vlan tags
                    self.logger.info("Pushing Vlan Tag %s, dpid:%s,src:%s,dst:%s", vlan, dpid,src, dst)
                    field=parser.OFPMatchField.make(OF.OXM_OF_VLAN_VID,vlan)
                    actions.append(parser.OFPActionPushVlan(VLAN_TAG_802_1Q))
                    actions.append(parser.OFPActionSetField(field))
            elif out_port in access_ports:
                Wactions.append(parser.OFPActionOutput(out_port))
        else:
            #improve this condition
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
        # install a flow to avoid packet_in next time
        #improve this condition
        if not floodOut:
            if VLAN in header:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst,vlan_vid=vlan)
                if out_port in trunk_ports:#reassign vlan based on dscp flag
                else:actions.append(parser.OFPActionPopVlan())
                meterID=0
                #match.set_vlan_vid_masked(vlan,((1 << 16) - 2))
            else:
                meterID=self.getMeterID(vlan,dpid)#meter if meter_id
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            # verify if we have a valid buffer_id, if yes avoid to send both
            if msg.buffer_id != OF.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, write=Wactions,buffer_id=msg.buffer_id,meter_id=meterID)
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






