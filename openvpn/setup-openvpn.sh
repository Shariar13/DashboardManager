#!/bin/bash
OVPN_DATA="ovpn-data"
docker volume create --name $OVPN_DATA
docker run -v $OVPN_DATA:/etc/openvpn --rm kylemanna/openvpn ovpn_genconfig -u udp://$(curl -s ifconfig.me):1194
docker run -v $OVPN_DATA:/etc/openvpn --rm kylemanna/openvpn ovpn_initpki nopass
echo "OpenVPN server initialized!"
