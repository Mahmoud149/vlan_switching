mac_to_port = {}
vlan_map = {'10':[(1,1),(3,2),(2,1)],'30':[(3,1),(2,2),(1,2)],'40':[(4,1),(4,40)]}

for vlan in vlan_map:
	mac_to_port[vlan] = vlan_map[vlan]

def getVLAN(port,dpid):
	for vlan in mac_to_port:
		if (port,dpid) in mac_to_port[vlan]:
			return vlan
	return None

def addVLAN(vlanID,port,dpid):
	if vlanID not in mac_to_port:
		mac_to_port[str(vlanID)] = [(port,dpid)]
	else:
		mac_to_port[str(vlanID)].append((port,dpid))

def delVLAN(vlanID):
	mac_to_port.pop(str(vlanID))


if __name__ == "__main__":
	print getVLAN(1,1)
	print getVLAN(3,2)
	print getVLAN(2,1)
	print getVLAN(3,1)
	print getVLAN(2,2)
	print getVLAN(1,2)
	print getVLAN(4,1)
	print getVLAN(4,40)
	addVLAN(11,3,4)
	delVLAN(40)
	print mac_to_port
