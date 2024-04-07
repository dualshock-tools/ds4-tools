#!/usr/bin/env python3

import usb.core
import usb.util
import array
import struct
import sys
import binascii
import time
from construct import *
import argparse

dev = None

VALID_DEVICE_IDS = [
    (0x054c, 0x0ce6)
]

def wait_for_device():
    global dev

    print("Waiting for a DualSense...")
    while True:
        for i in VALID_DEVICE_IDS:
            dev = usb.core.find(idVendor=i[0], idProduct=i[1])
            if dev is not None:
                print("Found a DualSense: vendorId=%04x productId=%04x" % (i[0], i[1]))
                return
        time.sleep(1)

class HID_REQ:
    DEV_TO_HOST = usb.util.build_request_type(
        usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
    HOST_TO_DEV = usb.util.build_request_type(
        usb.util.CTRL_OUT, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
    GET_REPORT = 0x01
    SET_REPORT = 0x09

def hid_get_report(dev, report_id, size):
    assert isinstance(size, int), 'get_report size must be integer'
    assert report_id <= 0xff, 'only support report_type == 0'
    return dev.ctrl_transfer(HID_REQ.DEV_TO_HOST, HID_REQ.GET_REPORT, report_id, 0, size + 1)[1:].tobytes()


def hid_set_report(dev, report_id, buf):
    assert isinstance(buf, (bytes, array.array)
                      ), 'set_report buf must be buffer'
    assert report_id <= 0xff, 'only support report_type == 0'
    buf = struct.pack('B', report_id) + buf
    return dev.ctrl_transfer(HID_REQ.HOST_TO_DEV, HID_REQ.SET_REPORT, (3 << 8) | report_id, 0, buf)

def do_stick_center_calibration():
    print("Starting analog center calibration...")

    deviceId = 1
    targetId = 1

    hid_set_report(dev, 0x82, struct.pack('BBB', 1, deviceId, targetId))

    k = hid_get_report(dev, 0x83, 4)
    if k != bytes([deviceId,targetId,1,0xff]):
        print("ERROR: DualSense is in invalid state: %s. Try to reset it" % (binascii.hexlify(k)))
        return

    while True:
        print("Press S to sample data or W to store calibration (followed by enter)")
        X = input("> ").upper()
        if X == "S":
            hid_set_report(dev, 0x82, struct.pack('BBB', 3, deviceId, targetId))
            assert hid_get_report(dev, 0x83, 4) == bytes([deviceId,targetId,1,0xff])
        elif X == "W":
            hid_set_report(dev, 0x82, struct.pack('BBB', 2, deviceId, targetId))
            break
        else:
            print("Invalid command")

    print("Stick calibration done!!")

def do_stick_minmax_calibration():
    print("Starting analog min-max calibration...")

    deviceId = 1
    targetId = 2

    hid_set_report(dev, 0x82, struct.pack('BBB', 1, deviceId, targetId))
    k = hid_get_report(dev, 0x83, 4)
    if k != bytes([deviceId,targetId,1,0xff]):
        print("ERROR: DualSense is in invalid state: %s. Try to reset it" % (binascii.hexlify(k)))
        return

    print("DualSense is now sampling data. Move the analogs all around their range")
    print("When done, press any key to store calibration.")

    input()

    hid_set_report(dev, 0x82, struct.pack('BBB', 2, deviceId, targetId))

    print("Stick calibration done!!")

if __name__ == "__main__":
    print("*********************************************************")
    print("* Welcome to the fantastic DualSense Calibration Tool   *")
    print("*                                                       *")
    print("* This tool may break your controller.                  *")
    print("* Use at your own risk. Good luck! <3                   *")
    print("*                                                       *")
    print("* Version 0.01 (C) 2024                   ~ by the_al ~ *")
    print("*********************************************************")

    parser = argparse.ArgumentParser(prog='ds5-calibration-tool')

    parser.add_argument('-p', '--permanent', help="make changes permanent", action='store_true')
    subparsers = parser.add_subparsers(dest="action")

    p = subparsers.add_parser('analog-center', help="calibrate the center the analog sticks")
    p.set_defaults(func=do_stick_center_calibration)

    p = subparsers.add_parser('analog-range', help="calibrate the range of analog sticks")
    p.set_defaults(func=do_stick_minmax_calibration)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        exit(1)

    wait_for_device()

    # Detach kernel driver
    if sys.platform != 'win32' and dev.is_kernel_driver_active(0):
        try:
            dev.detach_kernel_driver(0)
        except usb.core.USBError as e:
            sys.exit('Could not detatch kernel driver: %s' % str(e))

    if dev == None:
        print("Cannot find a DualSense")
        exit(-1)

    print("== DualSense online! ==")

    if args.permanent:
        print("Unlocking NVS")
        hid_set_report(dev, 0x80, struct.pack('BBBBBB', 3, 2, 101, 50, 64, 12))

    try:
        args.func()
    except Exception as e:
        print(e)

    if args.permanent:
        print("Re-locking NVS")
        hid_set_report(dev, 0x80, struct.pack('BB', 3, 1))
