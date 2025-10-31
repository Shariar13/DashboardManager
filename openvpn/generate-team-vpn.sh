#!/bin/bash
TEAM_ID=$1
docker exec openvpn-server easyrsa build-client-full team$TEAM_ID nopass
docker exec openvpn-server ovpn_getclient team$TEAM_ID > ../vpn-configs/team$TEAM_ID.ovpn
echo "route 10.100.$TEAM_ID.0 255.255.255.0" >> ../vpn-configs/team$TEAM_ID.ovpn
echo "VPN config created: vpn-configs/team$TEAM_ID.ovpn"
