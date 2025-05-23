import math
import random
import re
import signal
import socket
import statistics
import string
import subprocess
import sys
import time
from contextlib import nullcontext

import cypcap

from asd_stan_parser import RemoteId
from rid_capture_test import rid_listen
from wlan_management import InterfaceManagementError, ensure_monitor_mode_enabled, get_hardware_mac_address, get_physical_device_name, print_available_interfaces, set_channel


# Channel used for sending and receiving packets
CHANNEL = 6

# Operator ID so that we can distinguish packets that come from a txpower tester from other RID packets
# NB: Must be at most 20 ASCII characters
SENDER_OPERATOR_ID = 'txpower_tester v3'

# RID packet in a beacon frame for testing
PACKET = bytes.fromhex(
    '000024002f4000a02008000000000000db19fd1200000000100c8509c000c6000000c600' # Radiotap header
    '80000000ffffffffffff60601f789d7960601f789d790000009a433600000000a000200400185249442d3135383146364e38433233374c30303332345854dd85fa0bbc0d28' # Beacon frame
    'f11905' # Message Pack (15)
    '01123135383146364e38433233374c30303332345854000000' # Basic ID Message (0)
    '1122b500006872cd222edaee0fad075808cc07454023890100' # Location/Vector Message (1)
    '31000000000000000000000000000000000000000000000000' # Self-ID Message (3)
    '41059870cd229cd8ee0f050000000000000260080000000000' # System Message (4)
    '5100' + SENDER_OPERATOR_ID.encode('ascii').ljust(20, b'\0').hex() + '000000' # Operator ID Message (5)
    '8d9ba515' # FCS
)

# Offset and length for self-id, wich we use to send a general purpose string payload
PACKET_PAYLOAD_OFFSET = 160
PACKET_PAYLOAD_MAX_LENGTH = 23

def packet_with_payload(payload: str):
    encoded = payload.encode('ascii')
    if len(encoded) > PACKET_PAYLOAD_MAX_LENGTH:
        raise AssertionError("Payload too long")
    return PACKET[:PACKET_PAYLOAD_OFFSET] + encoded + PACKET[PACKET_PAYLOAD_OFFSET + len(encoded):]

def send_payload(send_pcap: cypcap.Pcap, payload: str):
    send_pcap.sendpacket(packet_with_payload(payload))


# Background:
#
# This testing setup depends on setting the transmit power (txpower) of the WiFi device.
# The txpower setting is somewhat poorly documented and not supported on all cards.
# For example, our *redacted* card does not seem to support any fixed txpower settings.
# Our *redacted* cards with the old *redacted* driver seem to support setting txpower,
# but reading txpower with 'iw dev' will always report txpower as -100.00 dBm.
#
# According to the documentation, txpower should use units of mBm (1 dBm = 100 mBm).
# For *redacted* the usable range seems to be about 2000 mBm (txpower values 200-2200).
# Very large negative values behave the same as large positive values. Presumably there is some internal underflow.
# Various txpower values and measured signal strength with *redacted* (sending) and *redacted* (receiving):
# -1000: -45 dBm
#  -500: -45 dBm
#     0: -45 dBm
#   500: -41 dBm
#  1000: -36 dBm
#  1500: -31 dBm
#  2000: -26 dBm
#  2500: -25 dBm
#  3000: -24 dBm

_channel_txpower_regex = re.compile(r"(\d+) mhz\s+\[(\d+)\]\s+maximum tx power: ([\d.]+) dbm", re.IGNORECASE)

def get_max_txpowers(iface: str) -> dict[int, float]:
    """
    Gets maximum txpower for each channel supported by interface. Returns mapping from channel number to maximum txpower in dBm.
    """
    phy = get_physical_device_name(iface)

    phy_channels = subprocess.run(['iw', 'phy', phy, 'channels'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if phy_channels.returncode != 0:
        raise InterfaceManagementError(f"Failed to query channels for physical device {phy}, which should correspond to interface {iface}", phy_channels.stderr)

    txpowers: dict[int, float] = {}

    for freq, channel, txpower in _channel_txpower_regex.findall(phy_channels.stdout):
        if int(freq) >= 5935:
            # 6 GHz WiFi or some other newer standard. We want to skip these because the channel numbers used conflict with 2.4 and 5 GHz channel numbers.
            continue
        channel = int(channel)
        txpower = float(txpower)
        if channel in txpowers:
            raise AssertionError(f"Channel {channel} appears multiple times in the list of supported channels")
        txpowers[channel] = txpower
    
    if not txpowers:
        raise AssertionError("No enabled channels found in output from iw. This probably indicates a problem in the output parsing logic")
    
    return txpowers

def set_txpower(iface: str, txpower: int):
    if len(iface) == 0:
        raise AssertionError("Interface name must not be empty")
    try:
        subprocess.run(['ip', 'link', 'set', 'dev', iface, 'down'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
        subprocess.run(['/sbin/iw', 'dev', iface, 'set', 'txpower', 'fixed', str(txpower)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
        subprocess.run(['ip', 'link', 'set', 'dev', iface, 'up'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
    except subprocess.CalledProcessError as err:
        raise InterfaceManagementError(f"Failed to set txpower for interface {iface}. Error calling {err.cmd}", err.stdout) from None


# CLI utilities

def validate_txpower_argument(iface: str, channel: int, txpower: int):
    txpowers_dbm = get_max_txpowers(iface)
    max_txpower_mbm = math.ceil(txpowers_dbm[channel] * 100)
    if not (0 <= txpower <= max_txpower_mbm):
        print(f"ERROR: Requested txpower is outside allowed range (allowed: 0-{max_txpower_mbm}, requested: {txpower})")
        print("Larger txpower values may be allowed if you adjust your regulatory domain")
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage:")
        print(f"python {sys.argv[0]} listen <interface>")
        print(f"python {sys.argv[0]} send <interface> <txpower> [count] [delay]")
        print(f"python {sys.argv[0]} send_cycles <interface> <cycle count> [max txpower]")
        print()
        print_available_interfaces()
        sys.exit(1)

    mode = sys.argv[1].strip().lower()

    if mode == 'listen':
        if len(sys.argv) != 4:
            print(f"Usage:")
            print(f"python {sys.argv[0]} listen <interface> <logfile>")
            print("Use '-' as logfile path to disable logging.")
            print()
            print_available_interfaces()
            sys.exit(1)

        iface = sys.argv[2].strip()
        logfile_path = sys.argv[3].strip()
        if logfile_path == "":
            print("ERROR: Logfile path must not be empty. Use '-' as logfile path to disable logging.")
            sys.exit(1)
        if logfile_path == "-":
            logfile_path = None
        elif not logfile_path.endswith('.tsv'):
            logfile_path += '.tsv'

        ensure_monitor_mode_enabled(iface)

        with open(logfile_path, mode='x', encoding='utf8') if logfile_path is not None else nullcontext() as logfile:
            if logfile:
                print(f"Writing logs to file {logfile_path}")
                logfile.write(f"start_timestamp={time.time()}\trx_mac={get_hardware_mac_address(iface)}\thostname={socket.gethostname()}\n")
                logfile.write("timestamp\trun_hash\tcycle\ttxpower\tsignal_strength\n")

            prev_self_id = None
            signal_strengths = []

            def on_rid(rid: RemoteId):
                global prev_self_id, signal_strengths

                if not rid.self_id or rid.operator_id != SENDER_OPERATOR_ID:
                    return

                if prev_self_id != rid.self_id:
                    if prev_self_id is not None:
                        print()
                    prev_self_id = rid.self_id
                    signal_strengths = []
                signal_strengths.append(rid.signal_strength)

                run_hash, cycle, txpower = rid.self_id.split(' ', maxsplit=2)
                if logfile:
                    logfile.write(f"{rid.timestamp.timestamp()}\t{run_hash}\t{cycle}\t{txpower}\t{rid.signal_strength}\n")
                print(f"\rtxpower={txpower} cycle={cycle} count={len(signal_strengths)} avg_strength={statistics.fmean(signal_strengths):.2f} dBm", end='')

            rid_listen(iface, None, CHANNEL, callback=on_rid)
    elif mode == 'send':
        if not (4 <= len(sys.argv) <= 6):
            print(f"Usage:")
            print(f"python {sys.argv[0]} send <interface> <txpower> [count] [delay]")
            print()
            print_available_interfaces()
            sys.exit(1)

        iface = sys.argv[2].strip()
        txpower = int(sys.argv[3])
        count = int(sys.argv[4]) if len(sys.argv) >= 5 else 10
        delay = float(sys.argv[5]) if len(sys.argv) >= 6 else 0.2

        # validate_txpower_argument(iface, CHANNEL, txpower)

        ensure_monitor_mode_enabled(iface)
        set_channel(iface, CHANNEL, 'HT20')
        set_txpower(iface, txpower)

        # We prefix all payloads with a short random hash so that it is possible to distinguish different runs
        hash_chars = string.digits + string.ascii_letters
        run_hash = ''.join(random.choices(hash_chars, k=8))

        with cypcap.create(iface) as send_pcap:
            send_pcap.activate()

            send_datalink = send_pcap.datalink()
            if send_datalink != cypcap.DatalinkType.IEEE802_11_RADIO:
                raise RuntimeError(f"Unsupported linktype for sending: {send_datalink}")
            
            for packet_idx in range(count):
                print(f"Sending packet {packet_idx + 1}")
                send_payload(send_pcap, f'{run_hash}  {txpower}')
                time.sleep(delay)
    elif mode == 'send_cycles':
        if not (4 <= len(sys.argv) <= 5):
            print(f"Usage:")
            print(f"python {sys.argv[0]} send_cycles <interface> <cycle count> [max txpower]")
            print()
            print_available_interfaces()
            sys.exit(1)

        iface = sys.argv[2].strip()
        cycle_count = int(sys.argv[3])
        # Use usable range of ACH as default min and max txpower
        min_txpower = 200
        max_txpower = int(sys.argv[4]) if len(sys.argv) >= 5 else 2200

        # validate_txpower_argument(iface, CHANNEL, max_txpower)

        # Time estimate: 
        # Each txpower level is 10 packets with a gap of 0.2 seconds after each packet.
        # Each cycle is n levels with a gap of 1 second after the end of the cycle.
        # In practice sending each txpower level was measured to take an additional ~0.2 seconds.
        est_time = cycle_count * (len(range(min_txpower, max_txpower + 1, 100)) * 2.2 + 1)

        print(f"Sending {cycle_count} cycles with txpower range {min_txpower}-{max_txpower}")
        print(f"Estimated time: {est_time / 60:.1f} minutes")

        # We prefix all payloads with a short random hash so that it is possible to distinguish different runs
        hash_chars = string.digits + string.ascii_letters
        run_hash = ''.join(random.choices(hash_chars, k=8))

        running = True
        def handler(s, f):
            global running
            running = False
            print("Ctrl+C pressed. Exiting at the end of the current cycle.")
        signal.signal(signal.SIGINT, handler)

        for cycle_idx in range(cycle_count):
            print(f"Sending cycle {cycle_idx + 1}")

            for txpower in range(min_txpower, max_txpower + 1, 100):
                ensure_monitor_mode_enabled(iface)
                set_channel(iface, CHANNEL, 'HT20')
                set_txpower(iface, txpower)

                print(f"Sending with txpower {txpower}")

                with cypcap.create(iface) as send_pcap:
                    send_pcap.activate()

                    send_datalink = send_pcap.datalink()
                    if send_datalink != cypcap.DatalinkType.IEEE802_11_RADIO:
                        raise RuntimeError(f"Unsupported linktype for sending: {send_datalink}")
                    
                    for packet_idx in range(10):
                        # print(f"Sending packet {packet_idx + 1}")
                        send_payload(send_pcap, f'{run_hash} {cycle_idx + 1} {txpower}')
                        time.sleep(0.2)

            time.sleep(1)

            if not running:
                break
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
