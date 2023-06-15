#!/usr/bin/env python3

import usb.core
import usb.util

import array
import struct
import sys
import binascii
import time
import argparse
from construct import *

class HID_REQ:
    DEV_TO_HOST = usb.util.build_request_type(
        usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
    HOST_TO_DEV = usb.util.build_request_type(
        usb.util.CTRL_OUT, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
    GET_REPORT = 0x01
    SET_REPORT = 0x09

VALID_DEVICE_IDS = [
    (0x054c, 0x05c4),
    (0x054c, 0x09cc)
]

class DS4:

    def __init__(self):
        self.wait_for_device()

        if sys.platform != 'win32' and self.__dev.is_kernel_driver_active(0):
            try:
                self.__dev.detach_kernel_driver(0)
            except usb.core.USBError as e:
                sys.exit('Could not detatch kernel driver: %s' % str(e))

    def wait_for_device(self):
        print("Waiting for a DualShock 4...")
        while True:
            for i in VALID_DEVICE_IDS:
                self.__dev = usb.core.find(idVendor=i[0], idProduct=i[1])
                if self.__dev is not None:
                    print("Found a DualShock 4: vendorId=%04x productId=%04x" % (i[0], i[1]))
                    return
            time.sleep(1)
    
    def hid_get_report(self, report_id, size):
        dev = self.__dev
        #ctrl_transfer(bmRequestType, bRequest, wValue=0, wIndex=0, data_or_wLength=None, timeout=None)
        assert isinstance(size, int), 'get_report size must be integer'
        assert report_id <= 0xff, 'only support report_type == 0'
        return dev.ctrl_transfer(HID_REQ.DEV_TO_HOST, HID_REQ.GET_REPORT, report_id, 0, size + 1)[1:].tobytes()
    
    
    def hid_set_report(self, report_id, buf):
        dev = self.__dev
        assert isinstance(buf, (bytes, array.array)), 'set_report buf must be buffer'
        assert report_id <= 0xff, 'only support report_type == 0'
        buf = struct.pack('B', report_id) + buf
        return dev.ctrl_transfer(HID_REQ.HOST_TO_DEV, HID_REQ.SET_REPORT, (3 << 8) | report_id, 0, buf)

class Handlers:
    def __init__(self, dev):
        self.__dev = dev

    class VersionInfo:
        version_info_t = Struct(
            'compile_date' / PaddedString(0x10, encoding='ascii'),
            'compile_time' / PaddedString(0x10, encoding='ascii'),
            'hw_ver_major' / Int16ul,
            'hw_ver_minor' / Int16ul,
            'sw_ver_major' / Int32ul,
            'sw_ver_minor' / Int16ul,
            'sw_series' / Int16ul,
            'code_size' / Int32ul,
        )
    
        def __init__(s, buf):
            s.info = s.version_info_t.parse(buf)
    
        def __repr__(s):
            l = 'Compiled at: %s %s\n'\
                'hw_ver:%04x.%04x\n'\
                'sw_ver:%08x.%04x sw_series:%04x\n'\
                'code size:%08x' % (
                    s.info.compile_date, s.info.compile_time,
                    s.info.hw_ver_major, s.info.hw_ver_minor,
                    s.info.sw_ver_major, s.info.sw_ver_minor, s.info.sw_series,
                    s.info.code_size
                )
            return l


    def dump_flash(self, args):
        def flash_mirror_read(offset):
            assert offset < 0x800, 'flash mirror offset out of bounds'
            self.__dev.hid_set_report(0x08, struct.pack('>BH', 0xff, offset))
            return self.__dev.hid_get_report(0x11, 2)
        
        
        def dump_flash_mirror(path):
            # TODO can't correctly calc checksum for some reason
            if sys.platform == 'win32':
                path = path.translate({ord(i): None for i in '*<>?:|'})
            print('Dumping flash mirror to %s...' % (path))
            with open(path, 'wb') as f:
                for i in range(0, 0x800, 2):
                    word = flash_mirror_read(i)
                    #print('%03x : %s' % (i, binascii.hexlify(word)))
                    f.write(word)
            print('done')

        dump_flash_mirror(args.output_file)

    def info(self, args):
        info = self.VersionInfo(self.__dev.hid_get_report(0xa3, 0x30))
        print(info)

    def reset(self, args):
        try:
            print("Send reset command...")
            self.__dev.hid_set_report(0xa0, struct.pack('BBB', 4, 1, 0))
        except usb.core.USBError as e:
            # Reset worked
            self.wait_for_device()
            print("Reset completed")

    def get_bt_mac_addr(self, args):
        ds4_mac = self.__dev.hid_get_report(0x81, 8)
        ds4_mac_str = "%02x:%02x:%02x:%02x:%02x:%02x" % struct.unpack("BBBBBB", ds4_mac)
        print("DS4 MAC: %s" % (ds4_mac_str, ))

    def set_bt_mac_addr(self, args):
        new_mac_addr = binascii.unhexlify(args.new_mac_addr)
        assert(len(new_mac_addr) == 6)
        self.__dev.hid_set_report(0x80, new_mac_addr)

    def get_bt_link_info(self, args):
        buf = self.__dev.hid_get_report(0x12, 6 + 3 + 6)
        ds4_mac, unk, host_mac = buf[0:6], buf[6:9], buf[9:15]
        assert unk == b'\x08\x25\x00'
        ds4_mac_str = "%02x:%02x:%02x:%02x:%02x:%02x" % struct.unpack("BBBBBB", ds4_mac)
        host_mac_str = "%02x:%02x:%02x:%02x:%02x:%02x" % struct.unpack("BBBBBB", host_mac)
        print("DS4 MAC: %s" % (ds4_mac_str, ))
        print("Host MAC: %s" % (host_mac_str, ))

    def set_bt_link_info(self, args):
        host_addr = binascii.unhexlify(args.host_addr)
        link_key = binascii.unhexlify(args.link_key)

        if len(host_addr) != 6 or len(link_key) != 16:
            print("Usage: set-bt-link-info <6-bytes host addr> <16-bytes link key>")

            print("Host addr len: %d" % (len(host_addr), ))
            print("Link key len: %d" % (len(link_key), ))
            exit(1)

        assert len(host_addr) == 6
        assert len(link_key) == 16

        host_addr_str = "%02x:%02x:%02x:%02x:%02x:%02x" % struct.unpack("BBBBBB", host_addr)
        link_key_str  = binascii.hexlify(link_key).decode('utf-8')

        print("Setting host_addr=%s link_key=%s" % (host_addr_str, link_key_str))
        self.__dev.hid_set_report(0x13, host_addr + link_key)

    def get_imu_calibration(self, args):
        data = self.__dev.hid_get_report(0x02, 41)
        print("Raw data: %s" % (binascii.hexlify(data).decode('utf-8'), ))

    def set_imu_calibration(self, args):
        data = binascii.unhexlify(args.data)
        assert len(data) == 36

        print("Update IMU calibration data to: %s" % (binascii.hexlify(data).decode('utf-8')))
        data = self.__dev.hid_set_report(0x04, data)

    def get_flash_mirror_status(self, args):
        # Read byte 12
        self.__dev.hid_set_report(0x08, struct.pack('>BH', 0xff, 12))
        status = self.__dev.hid_get_report(0x11, 2)
        print("Changes in flash mirror are temporary: %d" % (status[0], ))

    def set_flash_mirror_status(self, args):
        if args.temporary not in [0,1]:
            print("Error: argument must be 0 or 1")
            exit(1)
        if args.temporary == 1:
            print("Set to: temporary")
            self.__dev.hid_set_report(0xa0, struct.pack('BBB', 10, 1, 0))
        else:
            print("Set to: permanent")
            code = binascii.unhexlify("3e717f89")
            self.__dev.hid_set_report(0xa0, struct.pack('BB', 10, 2) + code )

        print("Re-reading flash mirror status..")
        self.get_flash_mirror_status([])

    def get_pcba_id(self, args):
        # Read byte 12
        pcba_id = self.__dev.hid_get_report(0x86, 6)
        print("PCBA Id: %s" % (binascii.hexlify(pcba_id).decode('utf-8'), ))

    def set_pcba_id(self, args):
        data = binascii.unhexlify(args.data)
        assert len(data) == 6

        print("Set to: %s" % (binascii.hexlify(data).decode('utf-8')))
        self.__dev.hid_set_report(0x85, data)

    def get_bt_enable(self, args):
        # Read byte 0x700
        self.__dev.hid_set_report(0x08, struct.pack('>BH', 0xff, 0x700))
        status = self.__dev.hid_get_report(0x11, 2)
        print("BT Enable: %s" % (status[0], ))

    def set_bt_enable(self, args):
        raw = struct.pack('B', 1 if args.enable else 0)
        print("Set to: %s" % (binascii.hexlify(raw).decode('utf-8')))
        self.__dev.hid_set_report(0xa1, raw)

    def get_serial_number(self, args):
        print('get_serial_number() isn\'t implemented yet')
        # Read byte 0x700
        #self.__dev.hid_set_report(0x08, struct.pack('>BH', 0xff, 0x700))
        #status = self.__dev.hid_get_report(0x11, 2)
        #print("BT Enable: %s" % (status[0], ))

    def set_serial_number(self, args):
        data = binascii.unhexlify(args.data)
        assert len(data) == 2

        self.__dev.hid_set_report(0x08, struct.pack('>B', 0x10) + data)
        print("Change serial number to: %s" % (binascii.hexlify(data).decode('utf-8')))

ds4 = DS4()
handlers = Handlers(ds4)

parser = argparse.ArgumentParser(description="Play with the DS4 controller",
                                 epilog="By the_al")

subparsers = parser.add_subparsers(dest="action")

# Dump flash mirror
p = subparsers.add_parser('dump-flash', help="Dump the flash mirror")
p.add_argument('output_file', help="Output file to write the dump to")
p.set_defaults(func=handlers.dump_flash)

# Info
p = subparsers.add_parser('info', help="Print info about the DS4")
p.set_defaults(func=handlers.info)

# Reset
p = subparsers.add_parser('reset', help="Reset the DS4")
p.set_defaults(func=handlers.reset)

# GET Mac Addr + SET Mac Addr
p = subparsers.add_parser('get-bt-mac-addr', help="Get the Bluetooth MAC Address")
p.set_defaults(func=handlers.get_bt_mac_addr)

p = subparsers.add_parser('set-bt-mac-addr', help="Set the Bluetooth MAC Address")
p.add_argument('new_mac_addr', help="New MAC address to store")
p.set_defaults(func=handlers.set_bt_mac_addr)

# GET BT Link Info + SET BT Link Info
p = subparsers.add_parser('get-bt-link-info', help="Get Bluetooth link information")
p.set_defaults(func=handlers.get_bt_link_info)

p = subparsers.add_parser('set-bt-link-info', help="Update Bluetooth link information")
p.add_argument('host_addr', help="Host MAC Address to connect to")
p.add_argument('link_key', help="Bluetooth link key")
p.set_defaults(func=handlers.set_bt_link_info)

# GET IMU Calibration + SET IMU Calibration
p = subparsers.add_parser('get-imu-calibration', help="Retrieve IMU calibration data")
p.set_defaults(func=handlers.get_imu_calibration)

p = subparsers.add_parser('set-imu-calibration', help="Change IMU calibration data")
p.add_argument('data', help="New calibration data to store")
p.set_defaults(func=handlers.set_imu_calibration)

# GET Flash Mirror Enable + SET Flash Mirror Enable
p = subparsers.add_parser('get-flash-mirror-status', help="Get flash-mirror status")
p.set_defaults(func=handlers.get_flash_mirror_status)

p = subparsers.add_parser('set-flash-mirror-status', help="Change how flash mirror works")
p.add_argument('temporary', type=int, help="Set if changes in configuration are temporary(1) or permanent(0)")
p.set_defaults(func=handlers.set_flash_mirror_status)

# GET PCBA Id + SET PCBA Id
p = subparsers.add_parser('get-pcba-id', help="Get the PCBA manifacturer ID")
p.set_defaults(func=handlers.get_pcba_id)

p = subparsers.add_parser('set-pcba-id', help="Change the PCBA manifacturer ID")
p.add_argument('data', help="New manifacturer ID (6 bytes)")
p.set_defaults(func=handlers.set_pcba_id)

# "BT ENABLE"
p = subparsers.add_parser('get-bt-enable', help="Read BT enable bit")
p.set_defaults(func=handlers.get_bt_enable)

p = subparsers.add_parser('set-bt-enable', help="Change the BT enable bit")
p.add_argument('enable', type=int, help="0 to disable and 1 to enable")
p.set_defaults(func=handlers.set_bt_enable)

# GET Serial Number + SET Serial Number
p = subparsers.add_parser('get-serial-number', help="Read the serial number")
p.set_defaults(func=handlers.get_serial_number)

p = subparsers.add_parser('set-serial-number', help="Set the serial number")
p.add_argument('data', help="2 bytes hex")
p.set_defaults(func=handlers.set_serial_number)

args = parser.parse_args()
if not hasattr(args, "func"):
    parser.print_help()
    exit(1)
args.func(args)
