#!/usr/bin/env python3

"""Usage:
   sudo python3 FatTreeRAN.py [--plot] Optional: use plotGraph function to visualize the RAN segment (APs and stations) in a 2D space.
                              [--arp] Optional: pre-computes ARP tables statically in all stations and hosts
                              [--isolation] Optional: prevent communication between stations associated to the same AP without an
                                                      explicit OpenFlow rule
                              [--test_net/--test_sw/--test_ap/--test_h/--test_sta/--test_as] Optional: run network deployment tests"""
import multiprocessing

#################################################################################################################Imports
####Network Emulation
from mn_wifi.net import Mininet_wifi
from mininet.log import setLogLevel, info
from mn_wifi.cli import CLI

from mininet.node import RemoteController #controller device
from mininet.node import OVSKernelSwitch #OVS forwarding device (switch)
from mn_wifi.node import OVSKernelAP #OVS forwarding device (AP)

from mininet.link import TCLink #Ethernet links emulation
from mn_wifi.link import wmediumd #WiFi connections emulation
from mn_wifi.wmediumdConnector import interference #WiFi connections emulation

####ONOS REST API interaction
import json
import requests

####Utility
import sys
import math
import time
import threading

########################################################################################################Global Variables
###Network Parameters
k=4 #number of herds of Fat-Tree topology
eth_bw=1000 #bandwidth of Ethernet links [Mbps]
max_queue=1000 #number of packets that can be queued on an L2 interface (both Ethernet and WiFi)

channels=[36, 40, 44, 48] #available radio channels

tx_power=14 #antenna's transmission power [dBm]
staG=5 #gain of station's antenna [dBi]
apG=10 #gain of AP's antenna [dBi]
prop_coef=2.5 #propagation model's exponential coefficient

z_ap=20.0 #fixed z coordinate for APs [m]
y_sta=[5.0, 0.0] #fixed y coordinates for two rows of stations [m]
z_sta=0.0 #fixed z coordinate for stations [m]
x1=10.0 #x coordinate for first AP and first pair of stations [m]

PR_REF=-20.0 #mimimum rx power received from nearest AP [dBm]
PR_NEI=-40.0 #mimimum rx power received from neighbor AP [dBm]

###Data Structures
coreSw={} #<switch_name, OVSKernelSwitch> for every core level OVS switch
aggSw={} #<switch_name, OVSKernelSwitch> for every aggregation level OVS switch
edgeAP={} #<AP_name, OVSKernelAP> for every edge level OVS AP
hosts={} #<host_name, Host> for every host device
stations={} #<station_name, Station> for every station device

mininet_lock=threading.Lock() #lock to avoid race condition when issuing cmd within threads

###Exposed ONOS REST-API endpoints
onos_network_conf_url="http://localhost:8181/onos/v1/network/configuration"

###ONOS REST-API metadata
onos_auth=("onos", "rocks") #user credentials
post_headers={"Content-Type": "application/json"} #HTTP POST request headers

#############################################################################################Network Emulation Functions
'''Creates a Mininet_wifi object.
   We emulate a RAN (Radio Access Network) of a 5G mobile network.
   A Fat-Tree topology of OVS switches (programmable forwarding devices) emulates a core segment.
   Links in the core segment are of Type Ethernet. TC utility emulates Ethernet features on switches' L2 ports.
   Each OVS switch is connected to a Host device (emulating a remote traffic source), and to a remote controller
   instance (ONOS).
   Edges of the Fat-Tree are OVS AP (programmable forwarding devices with wlan ports), emulating RAN connection points.
   Radio connections are of type IEEE802.11a. Wmediumd utility emulates radio connectivity features.
   Each OVS AP is connected to the same remote controller instance (ONOS).
   Station devices are connected to OVS AP via WiFi channels, emulating mobile stations.
   Fat-Tree topology provides redundant least-cost paths between each pair of communicating host/station. 
   @param str[] args
   @return Mininet_wifi net'''
def topology(args):
    global k, eth_bw, max_queue, prop_coef
    global coreSw, aggSw, edgeAP, hosts, stations
    global channels, z_ap, y_ap, z_sta, y_sta, z_sta, x1, dx

    ###Indexes (each node in the topology is univocally identified by a 3-tuple of indexes)
    herds=range(0, k) #herds are indexed 0 to k-1
    core_sws=range(1, (k//2)+1) #subset of core switches connected to a unique group of aggregation switches (indexed 1 to k/2)
    agg_sws=range((k//2), k) #aggregation switches in a herd are indexed k/2 to k-1
    edge_aps=range(0, (k//2)) #edge APs in a herd are indexed 0 to (k/2)-1
    stas=range(2, (k//2)+2) #stations connected to a given edge AP are indexed 2 to (k/2)+1

    num_aps=(k**2)//2 #number of access points

    net=Mininet_wifi(topo=None, build=False,
                     controller=RemoteController,
                     link=wmediumd,
                     wmediumd_mode=interference,
                     ac_method='ssf', #station<->AP association control: strongest signal first
                     autoAssociation=True, allAutoAssociation=True, #Mininet-WiFi automatically handles station<->AP association
                     mode="a", freq=5,
                     ipBase="192.168.1.0/24")

    if '--isolation' in args:
        net.client_isolation=True #stations cannot communicate without an explicit OF rule, even if associated to the same AP

    info("************Creating Network Nodes**********\n")

    ###Add core switches to the topology (for each core switch, we add a host directly connected to it)
    for a in agg_sws: #for all aggregation switches in a herd
        c_index=a-(k//2)+1 #each agg switch in the herd connects to a distinct group of core switches

        for c in core_sws: #for all core switches serving the current aggregation switch
            core_name=get_name(k, c_index, c) #core switch name "sw[k][c_index][c]"
            core_dpid=get_dpid(k, c_index, c) #get DPID of current core switch from the same 3-tuple
            coreSw[core_name]=net.addSwitch(name=core_name, cls=OVSKernelSwitch,
                                            dpid=core_dpid, protocols='OpenFlow13') #adds OVS switch

            host_name=get_name(k+1, c_index, c) #name of host directly connected to the core switch
            host_mac=get_MAC(k+1, c_index, c) #get host's MAC from the same 3-tuple
            host_ipv4=get_IPv4(k+1, c_index, c) #get host's IPv4 from the same 3-tuple
            hosts[host_name]=net.addHost(name=host_name, mac=host_mac, ip=host_ipv4) #adds host

            net.addLink(node1=coreSw[core_name], node2=hosts[host_name], port1=k+1, port2=1,
                        cls=TCLink, bw=eth_bw, max_queue_size=max_queue) #adds core switch-host connection

    count_aps=0 #counter of all OVS APs in the network

    ###Create herds
    for p in herds: #for every herd

        ###Add aggregation switches to the current herd (for each agg switch, we add a host directly connected to it)
        for a in agg_sws: #for all aggregation switches in the current herd
            agg_name=get_name(p, a, 1) #aggregation switch's name "sw[p][a][1]"
            agg_dpid=get_dpid(p, a, 1) #get switch's DPID with the same 3-tuple
            aggSw[agg_name]=net.addSwitch(name=agg_name, cls=OVSKernelSwitch,
                                          dpid=agg_dpid, protocols='OpenFlow13') #add OVS switch

            host_name=get_name(p, a, 2) #name of host directly connected to the agg switch
            host_mac=get_MAC(p, a, 2) #get host's MAC from the same 3-tuple
            host_ipv4=get_IPv4(p, a, 2) #get host's IPv4 from the same 3-tuple
            hosts[host_name]=net.addHost(name=host_name, mac=host_mac, ip=host_ipv4) #adds host

            net.addLink(node1=aggSw[agg_name], node2=hosts[host_name], port1=k+1, port2=1,
                        cls=TCLink, bw=eth_bw, max_queue_size=max_queue) #adds agg switch-host connection

            for c in core_sws: #connect current agg switch to a group of core level OVS switches
                core_name=get_name(k, a-(k//2)+1, c) #target core switch
                net.addLink(node1=aggSw[agg_name], node2=coreSw[core_name], port1=(k//2)+c, port2=p+1,
                            cls=TCLink, bw=eth_bw, max_queue_size=max_queue) #adds core switch-agg switch connection

        ###Add edge APs to the current herd
        for ap in edge_aps: #for every edge AP in the current herd
            ap_name=get_name(p, ap, 1) #edge AP's name "ap[p][ap][1]"
            ap_dpid=get_dpid(p, ap, 1) #get AP's DPID with the same 3-tuple
            ap_pos=f'{x1+(dx*count_aps)},{y_ap},{z_ap}' #spatial coordinates of current AP
            ap_channel=f'{channels[count_aps%4]}' #frequency channel selected for current AP
            edgeAP[ap_name]=net.addAccessPoint(name=ap_name, cls=OVSKernelAP, dpid=ap_dpid, protocols='OpenFlow13',
                                               ssid=f"ssid-{ap_name}", channel=ap_channel,
                                               position=ap_pos) #adds OVS AP

            ###Each AP is directly connected to a Host device via Ethernet
            host_name=get_name(p, ap, stas[-1]+1) #name of host directly connected to the OVS AP
            host_mac=get_MAC(p, ap, stas[-1]+1) #get host's MAC from the same 3-tuple
            host_ipv4=get_IPv4(p, ap, stas[-1]+1) #get host's IPv4 from the same 3-tuple
            hosts[host_name]=net.addHost(name=host_name, mac=host_mac, ip=host_ipv4) #adds host

            count_stas=0 #counter of stations connected to current AP

            ###Adds stations connected to the current OVS AP
            for sta in stas: #for every station connected to the current OVS AP
                station_name=get_name(p, ap, sta) #station's name "sta[p][ap][sta]"
                station_mac=get_MAC(p, ap, sta) #get station MAC address using the same 3-tuple
                station_ip=get_IPv4(p, ap, sta) #get station IPv4 address using the same 3-tuple
                sta_pos=f'{x1+(dx*count_aps)},{y_sta[count_stas]},{z_sta}' #spatial coordinates of current station
                stations[station_name]=net.addStation(name=station_name, mac=station_mac, ip=station_ip,
                                                      position=sta_pos) #adds station
                count_stas+=1 #update station counter

            count_aps+=1 #update AP counter

    info(f"\n")
    info(f"\n**********Wifi Configuration**********\n")
    net.setPropagationModel(model="logDistance", exp=prop_coef)
    net.configureWifiNodes() #configure and connect L2 wireless interfaces on stations and APs
    info(f"\n")

    ###Establishing Ethernet connections between OVS APs and OVS agg switches
    for p in herds: #for every herd
        for ap in edge_aps: #for every edge AP in the current herd
            ap_name=get_name(p, ap, 1) #edge AP's name "ap[p][ap][1]"

            for a in agg_sws: #for all aggregation switches in the current herd
                agg_name=get_name(p, a, 1) #aggregation switch's name "sw[p][a][1]"
                net.addLink(node1=edgeAP[ap_name], node2=aggSw[agg_name], port1=a, port2=ap+1,
                            cls=TCLink, bw=eth_bw, max_queue_size=max_queue) #adds edge AP-agg switch connection

            ###Establish Ethernet connection between current OVS AP and target host device
            host_name=get_name(p, ap, stas[-1]+1) #name of host directly connected to the OVS AP
            net.addLink(node1=edgeAP[ap_name], node2=hosts[host_name], port1=k, port2=1,
                        cls=TCLink, bw=eth_bw, max_queue_size=max_queue) #adds edge AP-host connection

    if '--plot' in args:
        net.plotGraph(min_x=-(x1+dx*(num_aps+1))*0.5, min_y=0,
                      max_x=(x1+dx*(num_aps+1))*1.5, max_y=y_ap*3) #visual representation of RAN segment in a 2D space

    return net

'''Starting network emulation'''
def net_start():
    global net

    info(f"\n")
    info(f"\n**********Network Emulation is Starting**********\n")

    controller=net.addController('controller', controller=RemoteController, ip='127.0.0.1', port=6653) #adds remote controller
    net.build()
    controller.start()
    info(f"\n")

    for sw in net.switches:
        net.get(sw.name).start([controller]) #starts switches and force connection to remote controller listening on localhost:6653

    for ap in net.aps:
        net.get(ap.name).start([controller]) #starts APs and force connection to remote controller listening on localhost:6653

'''Manually setting radio parameters in APs and stations (tx rate and antenna gain)'''
def set_params():
    global staG, apG
    global net

    for sta in net.stations:
        intf_name=sta.wintfs[0]

        sta.setAntennaGain(staG, intf=intf_name)
        sta.params['txrate']='54Mbps'

    for ap in net.aps:
        intf_name=ap.wintfs[0]

        ap.setAntennaGain(apG, intf=intf_name)
        ap.params['txrate']='54Mbps'

'''Trigger's ONOS host discovery by instructing station/host devices to inject traffic into the network'''
def trigger_hosts():
    global net

    print(f'\n')
    info("************Triggering ONOS host discovery**********\n")

    target1='sta002' #host/station device to be pinged
    target2='h511' #host/station device to be pinged

    ###Inject traffic (ping messages) from network's hosts/stations
    for host in net.hosts:
        net.ping([host, net.getNodeByName(target1)])
    for sta in net.stations:
        if sta.name==target1:
            net.ping([sta, net.getNodeByName(target2)])
        else:
            net.ping([sta, net.getNodeByName(target1)])

###################################################################################################Positioning Functions
'''Compute y coordinate for APs
   @return float y_ap'''
def get_y_ap():
    global PR_REF, z_ap, z_sta, y_sta

    d=d_from_RX(PR_REF) #minimum AP-station distance to receive at least -30 [dBm] power

    #d^2=(Xap - Xsta)^2 + (Yap-Ysta)^2 + (Zap-Zsta)^2
    #Xap==Xsta   ->   d^2=(Yap-Ysta)^2 + (Zap-Zsta)^2   ->   (Yap-Ysta)^2=d^2 - (Zap-Zsta)^2
    dy=d**2 - (z_ap - z_sta)**2 #(Yap-Ysta)^2
    if dy<0:
        raise ValueError("Invalid Parameters: solution cannot be computed")

    #since dy>0 and y_ap-y_sta1>0  ->  y_ap =  dy^1/2 + y_sta1
    y_ap=math.sqrt(dy)+y_sta[0] #Y coordinate of APs
    return y_ap

'''Compute horizontal spacing between APs/stations
   @return float dx'''
def get_spacing():
    global PR_NEI, z_ap, z_sta, y_ap, y_sta

    d=d_from_RX(PR_NEI) #minimum AP-station distance to receive at least -50 [dBm] power

    #d^2=(Xap - Xsta)^2 + (Yap-Ysta)^2 + (Zap-Zsta)^2   ->   (Xap-Xsta)^2=d^2 - (Yap-Ysta)^2 - (Zap-Zsta)^2
    dx2=d**2 - (y_ap-y_sta[0])**2 - (z_ap - z_sta)**2 #(Xap-Xsta)^2
    if dx2<0:
        raise ValueError("Invalid Parameters: solution cannot be computed")
    dx=math.sqrt(dx2) #horizontal spacing
    return dx

'''Compute antenna's range from sensed received power
   RX [dBm] = TX [dBm] + GT [dBi] + GR [dBi] - 10*n*log10(d)
   d [m] = 10^((TX [dBm] +  GT [dBi] + GR [dBi] - RX [dBm) / (10*n))
   @param float rx [dBm]'''
def d_from_RX(rx):
    global tx_power, apG, staG, prop_coef

    return 10.0**((tx_power+apG+staG-rx)/(10.0*prop_coef))

###############################################################################################ONOS Annotation Functions
'''Acquire additional info about OVS access points and annotate them on ONOS:
   -> Position
   @param Bool flag (True if the function is called as thread target)'''
def annotate_aps(flag=False):
    global net, onos_network_conf_url, onos_auth, post_headers

    aps_cfg={} #new AP data

    for ap in net.aps:
        annotations={ #additional data for APs
            "entries": {
                "position": ap.position
            }
        }

        aps_cfg[f"of:{ap.dpid}"]={ "annotations": annotations }

    payload={"devices": aps_cfg}
    #print(f"{payload}\n")

    ###POST request on ONOS Rest API to annotate additional info
    response=requests.post(onos_network_conf_url, auth=onos_auth, headers=post_headers, data=json.dumps(payload))

    if response.status_code in [200, 201]:
        if not flag:
            print("\nAPs data correctly noted on ONOS")
    else:
        print(f"\nAnnotation Error: {response.status_code}, {response.text}")

'''Acquire additional info about L2 Ethernet ports and annotate them on ONOS
   -> maxQueueLength
   -> backlogPackets
   -> backlogBytes
   -> maxThroughput
   @param Bool flag (True if the function is called as thread target)'''
def annotate_eth_ports(flag=False):
    global net, onos_network_conf_url, onos_auth, post_headers, mininet_lock

    ports_cfg={}

    for sw in net.switches:
        for port in sw.ports:
            if port.name=='lo':
                continue #skip loopback interface

            max_throughput=port.params['bw']
            max_queue=port.params['max_queue_size']

            with mininet_lock:
                out_p=sw.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\S+\\s+\\K\\d+(?=p)' | head -n1")
                out_b=sw.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\K\\d+(?=b)' | head -n1")

            annotations={ #additional data for Ethernet Ports
                "entries": {
                    "maxThroughput": max_throughput,
                    "maxQueueLength": max_queue,
                    "backlogPackets": out_p.strip(),
                    "backlogBytes": out_b.strip()
                }
            }

            ports_cfg[f"of:{sw.dpid}/{port.name[-1]}"]={ "annotations": annotations }

    for ap in net.aps:
        for port in ap.ports:
            if port.name=='lo' or "wlan" in port.name:
                continue #skip loopback interface and wireless ports

            max_throughput=port.params['bw']
            max_queue=port.params['max_queue_size']

            with mininet_lock:
                out_p=ap.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\S+\\s+\\K\\d+(?=p)' | head -n1")
                out_b=ap.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\K\\d+(?=b)' | head -n1")

            annotations={ #additional data for Ethernet Ports
                "entries": {
                    "maxThroughput": max_throughput,
                    "maxQueueLength": max_queue,
                    "backlogPackets": out_p.strip(),
                    "backlogBytes": out_b.strip()
                }
            }

            ports_cfg[f"of:{ap.dpid}/{port.name[-1]}"]={ "annotations": annotations }

    payload={"ports": ports_cfg}
    #print(f"{payload}\n")

    ###POST request on ONOS Rest API to annotate additional info
    response=requests.post(onos_network_conf_url, auth=onos_auth, headers=post_headers, data=json.dumps(payload))

    if response.status_code in [200, 201]:
        if not flag:
            print("\nEthernet ports data correctly noted on ONOS")
    else:
        print(f"\nAnnotation Error: {response.status_code}, {response.text}")

'''Acquire additional info about L2 WiFi ports on OVS switches and annotate them on ONOS
   -> maxQueueLength
   -> backlogPackets
   -> backlogBytes
   -> maxThroughput
   -> WiFi Mode
   -> WiFi Frequency
   -> WiFi Channel
   -> Bandwidth
   -> Tx Power
   -> Gain
   -> SSID
   -> Range
   -> Collisions
   @param Bool flag (True if the function is called as thread target)'''
def annotate_wlan_ports(flag=False):
    global net, onos_network_conf_url, onos_auth, post_headers, mininet_lock

    wports_cfg={}

    for ap in net.aps:
        for wport in ap.wports:
            max_throughput=wport.node.params['txrate']

            with mininet_lock:
                max_queue=ap.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'limit\\s+\\K\\d+(?=p)' | head -n1")

                out_p=ap.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'backlog\\s+\\S+\\s+\\K\\d+(?=p)' | head -n1")
                out_b=ap.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'backlog\\s+\\K\\d+(?=b)' | head -n1")

                out_col=ap.cmd(f"cat /sys/class/net/{wport.name}/statistics/collisions")

            tx_power=wport.node.get_txpower(wport)
            gain=wport.node.wintfs[0].antennaGain
            range=wport.node.wintfs[0].range
            mode=wport.node.wintfs[0].mode
            ssid=wport.node.params['ssid']
            freq=wport.node.wintfs[0].freq
            channel=wport.node.params['channel']
            bw=wport.node.params['band']

            annotations={ #additional data for Ethernet Ports
                "entries": {
                    "maxThroughput": max_throughput.replace("Mbps", ""),
                    "maxQueueLength": max_queue.strip(),
                    "backlogPackets": out_p.strip(),
                    "backlogBytes": out_b.strip(),
                    "wifiMode": mode,
                    "wifiFrequency": freq,
                    "wifiChannel": channel,
                    "Bandwidth": bw,
                    "txPower": tx_power,
                    "gain": gain,
                    "ssid": ssid,
                    "range": range,
                    "collisions": out_col.strip()
                }
            }

            wports_cfg[f"of:{ap.dpid}/{wport.name[-1]}"]={ "annotations": annotations }

    payload={"ports": wports_cfg}
    #print(f"{payload}\n")

    ###POST request on ONOS Rest API to annotate additional info
    response=requests.post(onos_network_conf_url, auth=onos_auth, headers=post_headers, data=json.dumps(payload))

    if response.status_code in [200, 201]:
        if not flag:
            print("\nWiFi ports data correctly noted on ONOS")
    else:
        print(f"\nAnnotation Error: {response.status_code}, {response.text}")

'''Acquire additional info about host devices and annotates them on ONOS:
   -> Name
   -> Type (Host)
   -> Ethernet ports
   @param Bool flag (True if the function is called as thread target)'''
def annotate_hosts(flag=False):
    global net, onos_network_conf_url, onos_auth, post_headers

    hosts_cfg={} #new host data

    for host in net.hosts:
        name=host.name
        type="Host"
        interfaces=[f"{port.name[-1]}:{port.name}" for port in host.ports]

        annotations={ #additional data for hosts
            "entries": {
                "name": name,
                "type": type,
                "interfaces": interfaces
                }
            }

        hosts_cfg[f"{host.MAC()}/None"]={ "annotations": annotations }

    payload={"hosts": hosts_cfg}
    #print(f"{payload}\n")

    ###POST request on ONOS Rest API to annotate additional info
    response=requests.post(onos_network_conf_url, auth=onos_auth, headers=post_headers, data=json.dumps(payload))

    if response.status_code in [200, 201]:
        if not flag:
            print("\nHosts data correctly noted on ONOS")
    else:
        print(f"\nAnnotation Error: {response.status_code}, {response.text}")

'''Acquire additional info about station devices and annotates them on ONOS
   -> Name
   -> Type (Station)
   -> WiFi ports
   -> Position
   -> WiFi Mode
   -> WiFi Frequency
   -> RSSI
   -> Connected SSID
   -> Distance from AP
   -> Tx Packets
   -> Rx Packets
   -> Tx Bytes
   -> Rx Bytes
   -> Tx Errors
   -> Rx Errors
   -> Tx Drops
   -> Rx Drops
   -> Collisions
   @param Bool flag (True if the function is called as thread target)'''
def annotate_stations(flag=False):
    global net, onos_network_conf_url, onos_auth, post_headers, mininet_lock

    stas_cfg={} #new host data

    for sta in net.stations:
        name=sta.name
        type="Station"
        interfaces=[f"{wport.name[-1]}:{wport.name}" for wport in sta.wports]

        with mininet_lock:
            out_txb=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/tx_bytes")
            out_rxb=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/rx_bytes")
            out_txp=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/tx_packets")
            out_rxp=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/rx_packets")
            out_txe=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/tx_errors")
            out_rxe=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/rx_errors")
            out_txd=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/tx_dropped")
            out_rxd=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/rx_dropped")
            out_col=sta.cmd(f"cat /sys/class/net/{sta.wintfs[0].name}/statistics/collisions")

            out_ap=sta.cmd(f"iw dev {sta.wintfs[0].name} link | grep -oP '(?<=SSID:\\\\s).*'")

        if out_ap.strip():
            ssid_name=out_ap.strip()
            distance=net.get_distance(sta, net.getNodeByName(out_ap.strip().split("ssid-")[-1]))
        else:
            ssid_name="NaN"
            distance="NaN"

        annotations={ #additional data for hosts stations
            "entries": {
                "name": name,
                "type": type,
                "interfaces": interfaces,
                "position": sta.position,
                "wifiMode": sta.wintfs[0].mode,
                "wifiFrequency": sta.wintfs[0].freq,
                "RSSI": sta.wintfs[0].rssi,
                "apSSID": ssid_name,
                "distanceFromAp": distance,
                "txBytes": out_txb.strip(),
                "rxBytes": out_rxb.strip(),
                "txPackets": out_txp.strip(),
                "rxPackets": out_rxp.strip(),
                "txErrors": out_txe.strip(),
                "rxErrors": out_rxe.strip(),
                "txDropped": out_txd.strip(),
                "rxDropped": out_rxd.strip(),
                "collisions": out_col.strip()
            }
        }

        stas_cfg[f"{sta.MAC()}/None"]={ "annotations": annotations }

    payload={"hosts": stas_cfg}
    #print(f"{payload}\n")

    ###POST request on ONOS Rest API to annotate additional info
    response=requests.post(onos_network_conf_url, auth=onos_auth, headers=post_headers, data=json.dumps(payload))

    if response.status_code in [200, 201]:
        if not flag:
            print("\nHosts/stations data correctly noted on ONOS")
    else:
        print(f"\nAnnotation Error: {response.status_code}, {response.text}")

#################################################################################################Thread Target Functions
'''Periodically update annotations on OVS APs'''
def update_aps():
    global stop_event

    while not stop_event.is_set():
        time.sleep(15) #waiting interval of 15 s in between updates
        annotate_aps(flag=True)

'''Periodically update annotations on Ethernet Ports'''
def update_eth_ports():
    global stop_event

    while not stop_event.is_set():
        time.sleep(15) #waiting interval of 15 s in between updates
        annotate_eth_ports(flag=True)

'''Periodically update annotations on WiFi Ports'''
def update_wlan_ports():
    global stop_event

    while not stop_event.is_set():
        time.sleep(15) #waiting interval of 15 s in between updates
        annotate_wlan_ports(flag=True)

'''Periodically update annotations on host devices'''
def update_hosts():
    global stop_event

    while not stop_event.is_set():
        time.sleep(15) #waiting interval of 15 s in between updates
        annotate_hosts(flag=True)

'''Periodically update annotations on station devices'''
def update_stations():
    global stop_event

    while not stop_event.is_set():
        time.sleep(15) #waiting interval of 15 s in between updates
        annotate_stations(flag=True)

#######################################################################################################Testing Functions
'''Expose basic network info (num devices, links, num links, distances)'''
def test_network():
    global net

    print(f'\n')
    info("************Testing Network Deployment**********\n")
    num_sw=len(net.switches)
    num_ap=len(net.aps)
    num_host=len(net.hosts)
    num_sta=len(net.stations)
    print(f'Num OVS Switches: {num_sw}')
    print(f'Num OVS APs: {num_ap}')
    print(f'Num Hosts: {num_host}')
    print(f'Num Stations: {num_sta}')
    print(f'Num Nodes: {num_sw+num_ap+num_host+num_sta}\n')

    print(f'Network Links (Ethernet + WiFi):')
    for link in net.links:
        print(f'{link} - Type: {type(link)}')
    print(f'Num Links: {len(net.links)}\n')

    ap1=net.getNodeByName('ap001')
    ap2=net.getNodeByName('ap311')
    sta=net.getNodeByName('sta313')
    print(f'Max AP <-> AP distance: {ap1.get_distance_to(ap2)} [m]')
    print(f'Max AP <-> Station distance: {ap1.get_distance_to(sta)} [m]\n')

'''Expose info about OVS switches (params, Ethernet ports, ports statistics)'''
def test_switches():
    global net

    print(f'\n')
    info("************OVS Switches Info**********\n")
    for sw in net.switches:
        print(f'Switch: {sw.name}')
        print(f"Type: {type(sw)}. Datapath: {sw.datapath}")
        print(f"DPID: {sw.dpid}. Length: {len(sw.dpid)}")
        print(f'L2 Ethernet Interfaces: {sw.intfs}\n')

        for port in sw.ports:
            if port.name=='lo':
                continue #skip loopback interface
            print(f'L2 Ethernet Port: {port.name} - Type: {type(port)}')
            print(f'Params: {port.params}')

            ###Port Stats
            out_txb=sw.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_bytes")
            out_rxb=sw.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_bytes")
            out_txp=sw.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_packets")
            out_rxp=sw.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_packets")
            out_txe=sw.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_errors")
            out_rxe=sw.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_errors")

            print("Transmitted bytes count:", out_txb.strip())
            print("Received bytes count:", out_rxb.strip())
            print("Transmitted packets count:", out_txp.strip())
            print("Received packets count:", out_rxp.strip())
            print("Transmission errors count:", out_txe.strip())
            print("Reception errors count:", out_rxe.strip())

            out_p=sw.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\S+\\s+\\K\\d+(?=p)' | head -n1")
            out_b=sw.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\K\\d+(?=b)' | head -n1")
            print("Backlog Packets:", out_p.strip()) #packets currently queued
            print("Backlog Bytes:", out_b.strip()) #bytes currently queued
            print(f"\n")

'''Expose info about OVS APs (params, Ethernet ports, WiFi ports, ports statistics, radio features)'''
def test_aps():
    global net

    print(f'\n')
    info("************OVS APs Info**********\n")
    for ap in net.aps:
        print(f"AP: {ap.name}")
        print(f"Type: {type(ap)}. Datapath: {ap.datapath}")
        print(f"DPID: {ap.dpid}. Length: {len(ap.dpid)}")
        print(f"Position: {ap.position}")
        print(f"AP Parameters: {ap.params}\n")

        print(f"L2 interfaces: {ap.intfs}")
        print(f"L2 WiFi interfaces: {ap.wintfs}\n")

        for port in ap.ports:
            if port.name=='lo' or "wlan" in port.name:
                continue #skip loopback interface and wireless ports
            print(f'L2 Ethernet Port: {port.name} - Type: {type(port)}')
            print(f'Params: {port.params}')

            ###Port Stats
            out_txb=ap.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_bytes")
            out_rxb=ap.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_bytes")
            out_txp=ap.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_packets")
            out_rxp=ap.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_packets")
            out_txe=ap.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_errors")
            out_rxe=ap.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_errors")

            print("Transmitted bytes count:", out_txb.strip())
            print("Received bytes count:", out_rxb.strip())
            print("Transmitted packets count:", out_txp.strip())
            print("Received packets count:", out_rxp.strip())
            print("Transmission errors count:", out_txe.strip())
            print("Reception errors count:", out_rxe.strip())

            out_p=ap.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\S+\\s+\\K\\d+(?=p)' | head -n1")
            out_b=ap.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\K\\d+(?=b)' | head -n1")
            print("Backlog Packets:", out_p.strip()) #currently queued packets
            print("Backlog Bytes:", out_b.strip()) #currently queued
            print(f"\n")

        for wport in ap.wports:
            print(f'L2 WiFi Port: {wport.name} - Type: {type(wport)}')

            print(f'Transmission Power [dBm]: {wport.node.get_txpower(wport)} - {wport.node.wintfs[0].txpower}')
            print(f"Antenna Gain [dBi]: {wport.node.wintfs[0].antennaGain}")
            print(f"Antenna Height [m]: {wport.node.getAntennaHeight(wport)} "
                  f"(relative to AP's height {wport.node.getxyz()[2]} [m])")
            print(f"Transmission Range [m]: {wport.node.wintfs[0].range}")

            print(f'WiFi Mode: 802.11{wport.node.wintfs[0].mode}')
            print(f"SSID: {wport.node.params['ssid']}")
            print(f'Frequency [GHz]: {wport.node.wintfs[0].freq}')
            print(f"Channel: {wport.node.params['channel']} - Bandwidth [MHz]: {wport.node.params['band']}")
            print(f"Transmission Rate: {wport.node.params['txrate']}")
            out_size=ap.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'limit\\s+\\K\\d+(?=p)' | head -n1")
            print("Max packets in queue:", out_size.strip())

            #Port Stats
            out_txb=ap.cmd(f"cat /sys/class/net/{wport.name}/statistics/tx_bytes")
            out_rxb=ap.cmd(f"cat /sys/class/net/{wport.name}/statistics/rx_bytes")
            out_txp=ap.cmd(f"cat /sys/class/net/{wport.name}/statistics/tx_packets")
            out_rxp=ap.cmd(f"cat /sys/class/net/{wport.name}/statistics/rx_packets")
            out_txe=ap.cmd(f"cat /sys/class/net/{wport.name}/statistics/tx_errors")
            out_rxe=ap.cmd(f"cat /sys/class/net/{wport.name}/statistics/rx_errors")

            print("Transmitted bytes count:", out_txb.strip())
            print("Received bytes count:", out_rxb.strip())
            print("Transmitted packets count:", out_txp.strip())
            print("Received packets count:", out_rxp.strip())
            print("Transmission errors count:", out_txe.strip())
            print("Reception errors count:", out_rxe.strip())

            out_p=ap.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'backlog\\s+\\S+\\s+\\K\\d+(?=p)' | head -n1")
            out_b=ap.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'backlog\\s+\\K\\d+(?=b)' | head -n1")
            print("Backlog Packets:", out_p.strip()) #packets currently queued
            print("Backlog Bytes:", out_b.strip()) #packets currently queued
            print(f"\n")

'''Expose info about Host devices (params, Ethernet ports, ports statistics)'''
def test_hosts():
    global net

    print(f'\n')
    info("************Hosts Info**********\n")
    for h in net.hosts:
        print(f"Host: {h.name}")
        print(f"MAC: {h.MAC()}")
        print(f"IPv4: {h.IP()}")
        print(f"Parameters: {h.params}\n")

        print(f"L2 Ethernet interfaces: {h.intfs}\n")

        for port in h.ports:
            if port.name=='lo':
                continue #skip loopback interface
            print(f'L2 Ethernet Port: {port.name} - Type: {type(port)}')
            print(f'Params: {port.params}')

            ###Port Stats
            out_txb=h.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_bytes")
            out_rxb=h.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_bytes")
            out_txp=h.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_packets")
            out_rxp=h.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_packets")
            out_txe=h.cmd(f"cat /sys/class/net/{port.name}/statistics/tx_errors")
            out_rxe=h.cmd(f"cat /sys/class/net/{port.name}/statistics/rx_errors")

            print("Transmitted bytes count:", out_txb.strip())
            print("Received bytes count:", out_rxb.strip())
            print("Transmitted packets count:", out_txp.strip())
            print("Received packets count:", out_rxp.strip())
            print("Transmission errors count:", out_txe.strip())
            print("Reception errors count:", out_rxe.strip())

            out_p=h.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\S+\\s+\\K\\d+(?=p)' | head -n1")
            out_b=h.cmd(f"tc -s qdisc show dev {port.name} | grep -oP 'backlog\\s+\\K\\d+(?=b)' | head -n1")
            print("Backlog Packets:", out_p.strip()) #packets currently queued
            print("Backlog Bytes:", out_b.strip()) #bytes currently queued
            print(f"\n")

'''Expose info about Station devices (params, WiFi ports, ports statistics, radio features)'''
def test_stations():
    global net

    print(f'\n')
    info("************Stations Info**********\n")
    for sta in net.stations:
        print(f"Station: {sta.name}")
        print(f"MAC: {sta.MAC()}")
        print(f"IPv4: {sta.IP()}")

        print(f"Position: {sta.position}")
        print(f"Parameters: {sta.params}\n")

        print(f"L2 WiFi interfaces: {sta.wintfs}")

        for wport in sta.wports:
            print(f'L2 WiFi Port: {wport.name} - Type: {type(wport)}')

            print(f'RSSI (Received Signal Strength Indicator) [dBm]: {wport.node.wintfs[0].rssi}')
            print(f"Antenna Gain [dBi]: {wport.node.wintfs[0].antennaGain}")
            print(f"Antenna Height [m]: {wport.node.getAntennaHeight(wport)} "
                  f"(relative to stations's height {wport.node.getxyz()[2]} [m])")

            print(f'WiFi Mode: 802.11{wport.node.wintfs[0].mode}')
            print(f'Frequency [GHz]: {wport.node.wintfs[0].freq}')
            print(f"Channel: {wport.node.params['channel']} - Bandwidth [MHz]: {wport.node.params['band']}")
            print(f"Transmission Rate: {wport.node.params['txrate']}")
            out_size=sta.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'limit\\s+\\K\\d+(?=p)' | head -n1")
            print("Max packets in queue:", out_size.strip())

            out_txb=sta.cmd(f"cat /sys/class/net/{wport.name}/statistics/tx_bytes")
            out_rxb=sta.cmd(f"cat /sys/class/net/{wport.name}/statistics/rx_bytes")
            out_txp=sta.cmd(f"cat /sys/class/net/{wport.name}/statistics/tx_packets")
            out_rxp=sta.cmd(f"cat /sys/class/net/{wport.name}/statistics/rx_packets")
            out_txe=sta.cmd(f"cat /sys/class/net/{wport.name}/statistics/tx_errors")
            out_rxe=sta.cmd(f"cat /sys/class/net/{wport.name}/statistics/rx_errors")

            print("Transmitted bytes count:", out_txb.strip())
            print("Received bytes count:", out_rxb.strip())
            print("Transmitted packets count:", out_txp.strip())
            print("Received packets count:", out_rxp.strip())
            print("Transmission errors count:", out_txe.strip())
            print("Reception errors count:", out_rxe.strip())

            out_p=sta.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'backlog\\s+\\S+\\s+\\K\\d+(?=p)' | head -n1")
            out_b=sta.cmd(f"tc -s qdisc show dev {wport.name} | grep -oP 'backlog\\s+\\K\\d+(?=b)' | head -n1")
            print("Backlog Packets:", out_p.strip())
            print("Backlog Bytes:", out_b.strip())
            print(f"\n")

'''Expose info about WiFi associations in the network'''
def test_associations():
    global net

    print(f'\n')
    info("************Station <-> AP Association Info**********\n")
    for sta in net.stations:
        print(f"Station: {sta.name}")

        for wport in sta.wports:
            print(f'L2 WiFi Port: {wport.name} - Type: {type(wport)}')

            out_ap=sta.cmd(f"iw dev {wport.name} link | grep -oP '(?<=SSID:\\\\s).*'")
            print("Connection Point:", out_ap.strip())

            if out_ap.strip():
                ap_name=out_ap.strip().split("ssid-")[-1]
                print(f"Connection AP: {net.getNodeByName(ap_name)} - {type(net.getNodeByName(ap_name))}\n")
            else:
                print(f'\n')

#######################################################################################################Utility Functions
'''Return the name of a Node object by specifying the node's 3-tuple of indexes
   @param int f (first index)
   @param int s (second index)
   @param int t (third index)
   @return str name'''
def get_name(f=0, s=0, t=0):
    global k

    if f==k+1: #node is a host connected to core switch via Ethernet
        return f"h{f}{s}{t}"
    elif f==k: #node is an OVS switch at core level
        return f"sw{f}{s}{t}"
    elif 0<=f<k:
        if t==1: #node is an OVS device (switch or AP)
            if 0<=s<(k//2): #node is an AP
                return f"ap{f}{s}{t}"
            elif (k//2)<=s<k: #node is an OVS switch at aggregation level
                return f"sw{f}{s}{t}"
            else:
                raise ValueError(f"Invalid Second Index {s}")
        elif 1<t<k: #node is a host or a station
            if 0<=s<(k//2): #node is a station connected to an edge OVS AP via WiFi
                return f"sta{f}{s}{t}"
            elif (k//2)<=s<k: #node is a host connected to an aggregation level OVS switch via Ethernet
                return f"h{f}{s}{t}"
            else:
                raise ValueError(f"Invalid Second Index {s}")
        elif t==k: #node is a host connected to an edge OVS AP via Ethernet
            return f"h{f}{s}{t}"
        else:
            raise ValueError(f"Invalid Third Index {t}")
    else:
        raise ValueError(f"Invalid First Index {f}")

'''Return the DPID of a OVS switch/AP object by specifying the node's 3-tuple of indexes
   @param int f (first index)
   @param int s (second index)
   @param int t (third index)
   @return str dpid (hexadecimal)'''
def get_dpid(f=0, s=0, t=0):
    return f'0000000000000{f:x}{s:x}{t:x}'

'''Return the MAC of a Host/Station object by specifying the node's 3-tuple of indexes
   @param int f (first index)
   @param int s (second index)
   @param int t (third index)
   @return str dpid (hexadecimal)'''
def get_MAC(f=0, s=0, t=0):
    return f'00:00:00:0{f}:0{s}:0{t}'

'''Return the IPv4 address of a Host/Station object by specifying the node's 3-tuple of indexes
   @param int f (first index)
   @param int s (second index)
   @param int t (third index)
   @return str dpid (hexadecimal)'''
def get_IPv4(f=0, s=0, t=0):
    last_octet=(36*f)+(6*s)+t
    return f'192.168.1.{last_octet}/24'

####################################################################################################################Main
if __name__ == '__main__':
    setLogLevel('info')
    print(f'Running Configurations: {sys.argv}\n')

    try:
        y_ap=get_y_ap() #get Y coordinate of OVS APs according to RX power requirements
    except ValueError as e:
        y_ap=40.0 #default value

    try:
        dx=get_spacing() #get horizontal spacing between OVS APs and between stations according to RX power requirements
    except ValueError as e:
        dx=50.0 #default value

    net=topology(sys.argv) #function creating the network

    net_start() #function kick-starting network emulation

    set_params() #setting antenna gain and transmission rate for APs and stations

    ###Testing network deployment and network devices' features
    if '--test_net' in sys.argv:
        test_network()
    if '--test_sw' in sys.argv:
        test_switches()
    if '--test_ap' in sys.argv:
        test_aps()
    if '--test_h' in sys.argv:
        test_hosts()
    if '--test_sta' in sys.argv:
        test_stations()
    if '--test_as' in sys.argv:
        time.sleep(120)
        test_associations()

    time.sleep(10)
    annotate_aps() #upload additional AP info on ONOS
    annotate_eth_ports() #upload additional Ethernet ports info on ONOS
    annotate_wlan_ports() #upload additional WiFi ports info on ONOS
    time.sleep(10)

    trigger_hosts() #allows ONOS to discover host devices
    if '--arp' in sys.argv:
        net.staticArp() #pre-computes ARP tables statically

    time.sleep(10)
    annotate_hosts() #upload additional host info on ONOS
    annotate_stations() #upload additional station info on ONOS
    time.sleep(10)

    ###Starting threads to periodically refresh annotations on network elements
    threads=[] #array of all threads started during simulation
    stop_event=threading.Event() #this event will be used to signal the threads to stop

    threads.append(threading.Thread(target=update_aps, daemon=True))
    threads.append(threading.Thread(target=update_eth_ports, daemon=True))
    threads.append(threading.Thread(target=update_wlan_ports, daemon=True))
    threads.append(threading.Thread(target=update_hosts, daemon=True))
    threads.append(threading.Thread(target=update_stations, daemon=True))

    for t in threads:
        t.start()

    CLI(net) #opens Mininet CLI

    stop_event.set() #signal the threads to stop
    print(f'Stopping threads: {stop_event}\n')
    for t in threads:
        t.join() #wait for all threads to finish

    net.stop()

    print(f"\n**********Simulation has Ended**********\n")