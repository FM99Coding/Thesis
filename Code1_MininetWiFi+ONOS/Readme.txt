Codes using Mininet-WiFi and ONOS REST API:

1. FatTreeRAN.py code emulates a 5G RAN architecture using Mininet-WiFi and annotates topology metrics on ONOS controller using exposed ONOS REST API;
2. TopoDiscovery.py uses ONOS REST-API to retrieve and expose topology info from ONOS Controller;
3. FlowDiscovery.py uses ONOS REST-API to retrieve and expose installed OpenFlow rules from ONOS Controller;
4. ECMPRouting.py applies Equal Cost MultiPath Routing on emulated topology (Djikstra Algorithm for computing paths, hash-based mod-N selection for choosing paths) to compute
   IPv4 routing. Flow rules are installed on emulated OVS switches using ONOS REST API;
