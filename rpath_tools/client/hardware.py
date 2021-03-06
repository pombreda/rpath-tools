#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import socket
from conary.lib import util
from rpath_tools.client import utils
from rpath_tools.client.utils import wbemlib

class WBEMData(object):
    
    cimClasses = []

    def __init__(self, url=None):
        self.url = url or '/tmp/sfcbHttpSocket'
        self.server = wbemlib.WBEMServer(self.url)
        self.data = {}
    
    def populate(self):
        for cimClassDict in self.cimClasses:
            for cimClass, cimProperties in cimClassDict.items():
                self.data[cimClass] = {}
                insts = getattr(self.server, cimClass).EnumerateInstances()
                for inst in insts:
                    instId = inst.properties['instanceID'].value
                    if not instId:
                        instId = inst.properties['Name'].value
                    self.data[cimClass][instId] = {} 
                    for cimProperty in cimProperties:
                        self.data[cimClass][instId][cimProperty] = \
                            inst.properties[cimProperty].value

    def getData(self):
        return self.data


class HardwareData(WBEMData):
    
    cimSystemClasses = {'Linux_OperatingSystem' : ['ElementName',
                            'OSType', 'Version']}
    cimCpuClasses = {'Linux_Processor' : ['ElementName',
                            'NumberOfEnabledCores', 'MaxClockSpeed']}
    cimNetworkClasses = {'Linux_IPProtocolEndpoint' : [
                            'IPv4Address', 'IPv6Address',
                            'SubnetMask', 'ProtocolType', 'SystemName',
                            'Name', 'NameFormat',
                            ]}

    cimClasses = [cimNetworkClasses]

    class IP(object):
        __slots__ = ['ipv4', 'ipv6', 'device', 'netmask', 'dns_name']
        def __init__(self, *args, **kwargs):
            for k in self.__slots__:
                setattr(self, k, kwargs.get(k, None))

    def __init__(self, cfg):
        self.cfg = cfg
        WBEMData.__init__(self, cfg.sfcbUrl)
        self.ips = []
        self.deviceName = ''

    @property
    def hardware(self):
        self.populate()
        return self.getData()

    def getIpAddresses(self):
        if self.ips:
            return self.ips
        else:
            for iface in self.hardware['Linux_IPProtocolEndpoint'].values():
                ipv4 = iface['IPv4Address']
                if ipv4 is not None and  ipv4 not in ('NULL', '127.0.0.1'):
                    device = iface['Name']
                    device = device.split('_')
                    if len(device) > 1:
                        deviceName = device[1]
                    else:
                        deviceName = device[0]
                    dnsName = self.resolve(ipv4) or ipv4
                    ip = self.IP(ipv4=ipv4, netmask=iface['SubnetMask'],
                        device=deviceName, dns_name=dnsName)
                    self.ips.append(ip)

        if utils.runningInEC2():
            self.ips.append(self._getExternalEC2Network())

        return self.ips


    def resolve(self, ipaddr):
        try:
            info = socket.gethostbyaddr(ipaddr)
            return info[0]
        except (socket.herror, socket.gaierror):
            return None

    def getHostname(self):
        return socket.gethostname()

    def getLocalIp(self, ipList):
        if ipList:
            return self._getLocalIp(ipList[0])
        # Hope for the best
        return self._getLocalIp('8.8.8.8')

    def getDeviceName(self, localIp):
        if self.deviceName:
            return self.deviceName
        else:
            ips = self.getIpAddresses()
            for ip in ips:
                active = (ip.ipv4 == localIp)
                if active:
                    self.deviceName = ip.device
                    return self.deviceName

    @classmethod
    def _getLocalIp(cls, destination):
        """Return my IP address visible to the destination host"""

        if utils.runningInEC2():
            return cls._getExternalEC2Ip()

        if "://" not in destination:
            destination = "http://%s" % destination
        hostname, port = util.urlSplit(destination, defaultPort=443)[3:5]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((hostname, int(port)))
        ret = s.getsockname()[0]
        s.close()
        return ret

    @classmethod
    def _getExternalEC2Ip(cls):
        try:
            from amiconfig import instancedata
            instanceData = instancedata.InstanceData()
        except ImportError:
            return

        return instanceData.getPublicIPv4()

    def _getExternalEC2Network(self):
        try:
            from amiconfig import instancedata
            instanceData = instancedata.InstanceData()
        except ImportError:
            return

        return self.IP(
            ipv4=instanceData.getPublicIPv4(),
            netmask='255.255.255.0',
            device='eth0-ec2',
            dns_name=instanceData.getPublicHostname())
        

def main(cfg=None):
    h = HardwareData(cfg)
    return h.hardware

if __name__ == '__main__':
    hwData = main()
    print hwData
