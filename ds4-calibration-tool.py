#!/usr/bin/env python3

import usb.core
import usb.util
import array
import struct
import sys
import binascii
import time
from construct import *

dev = None

VALID_DEVICE_IDS = [
    (0x054c, 0x05c4),
    (0x054c, 0x09cc)
]

def wait_for_device():
    global dev

    print("Waiting for a DualShock 4...")
    while True:
        for i in VALID_DEVICE_IDS:
            dev = usb.core.find(idVendor=i[0], idProduct=i[1])
            if dev is not None:
                print("Found a DualShock 4: vendorId=%04x productId=%04x" % (i[0], i[1]))
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

def dump_93_data():
    data = hid_get_report(dev, 0x93, 13)
    assert len(data) == 13
    deviceId, targetId, numChunks, curChunk, dataLen = struct.unpack('BBBBBxxxxxxxx', data)
    if deviceId == 0xff and targetId == 0xff:
        print("No data to read")
        return []

    theDeviceId, theTargetId = deviceId, targetId

    print("Data is split in %d chunks; we are at %d" % (numChunks, curChunk))
    if numChunks == 0:
        return []

    assert dataLen >= 0 and dataLen <= 8
    out = [data[5:5+dataLen]]

    while curChunk < numChunks - 1:
        data = hid_get_report(dev, 0x93, 13)
        assert len(data) == 13
        deviceId, targetId, numChunks, curChunk, dataLen = struct.unpack('BBBBBxxxxxxxx', data)
        if deviceId == 0xff or targetId == 0xff:
            print("No more data")
            return out

        assert (deviceId, targetId) == (theDeviceId, theTargetId)
        out += [data[5:5+dataLen]]
    return out

def do_trigger_calibration():
    print("Starting trigger calibration...")

    deviceId = 3

    hid_set_report(dev, 0x90, struct.pack('BBBB', 1, deviceId, 0, 3))

    for i in range(2):
        print("L2: release and press enter")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 1, 1))

    for i in range(2):
        print("L2: mid and press enter")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 2, 1))

    for i in range(2):
        print("L2: full and press enter")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 3, 1))

    for i in range(2):
        print("R2: release and press enter")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 1, 2))

    for i in range(2):
        print("R2: mid and press enter")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 2, 2))

    for i in range(2):
        print("R2: full and press enter")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 3, 2))

    print("Write.")
    hid_set_report(dev, 0x90, struct.pack('BBBB', 2, deviceId, 0, 3))

    print("Trigger calibration done!!")
    print()

    print("Here is some debug data from the DS4 about the calibration")
    data = dump_93_data()
    for i in range(len(data)):
        print("Sample %d, data=%s" % (i, binascii.hexlify(data[i]).decode('utf-8')))

def do_stick_center_calibration():
    print("Starting analog center calibration...")

    deviceId = 1
    targetId = 1

    hid_set_report(dev, 0x90, struct.pack('BBB', 1, deviceId, targetId))
    while True:
        assert hid_get_report(dev, 0x91, 3) == bytes([deviceId,targetId,1])
        assert hid_get_report(dev, 0x92, 3) == bytes([deviceId,targetId,0xff])
        print("Press S to sample data or W to store calibration (followed by enter)")
        X = input("> ").upper()
        if X == "S":
            hid_set_report(dev, 0x90, struct.pack('BBB', 3, deviceId, targetId))
        elif X == "W":
            hid_set_report(dev, 0x90, struct.pack('BBB', 2, deviceId, targetId))
            break
        else:
            print("Invalid command")

    assert hid_get_report(dev, 0x91, 3) == bytes([deviceId,targetId,2])
    assert hid_get_report(dev, 0x92, 3) == bytes([deviceId,targetId,1])

    print("Stick calibration done!!")
    print()

    print("Here is some debug data from the DS4 about the calibration")
    data = dump_93_data()
    for i in range(len(data)):
        print("Sample %d, data=%s" % (i, binascii.hexlify(data[i]).decode('utf-8')))

def do_stick_minmax_calibration():
    print("Starting analog min-max calibration...")

    deviceId = 1
    targetId = 2

    hid_set_report(dev, 0x90, struct.pack('BBB', 1, deviceId, targetId))
    assert hid_get_report(dev, 0x91, 3) == bytes([deviceId,targetId,1])
    assert hid_get_report(dev, 0x92, 3) == bytes([deviceId,targetId,0xff])

    print("DualShock 4 is now sampling data. Move the analogs all around their range")
    print("When done, press any key to store calibration.")

    input()

    hid_set_report(dev, 0x90, struct.pack('BBB', 2, deviceId, targetId))

    assert hid_get_report(dev, 0x91, 3) == bytes([deviceId,targetId,2])
    assert hid_get_report(dev, 0x92, 3) == bytes([deviceId,targetId,1])

    print("Stick calibration done!!")
    print()

    print("Here is some debug data from the DS4 about the calibration")
    data = dump_93_data()
    for i in range(len(data)):
        print("Sample %d, data=%s" % (i, binascii.hexlify(data[i]).decode('utf-8')))

def menu():
    print("")
    print("Choose what you want to calibrate:")
    print("1. Analog stick center")
    print("2. Analog stick range (min-max)")
    print("3. L2 / R2 (beta, let me know if works)")

    choice_int = -1
    try:
        choice_int = int(input("> "))
    except:
        print("Invalid choice.")
        return

    if choice_int == 1:
        do_stick_center_calibration()
    if choice_int == 2:
        do_stick_minmax_calibration()
    if choice_int == 3:
        do_trigger_calibration()


if __name__ == "__main__":
    print("*********************************************************")
    print("* Welcome to the fantastic DualShock 4 Calibration Tool *")
    print("*                                                       *")
    print("* This tool may break your controller.                  *")
    print("* Use at your own risk. Good luck! <3                   *")
    print("*                                                       *")
    print("* Version 0.01                            ~ by the_al ~ *")
    print("*********************************************************")

    wait_for_device()

    # Detach kernel driver
    if sys.platform != 'win32' and dev.is_kernel_driver_active(0):
        try:
            dev.detach_kernel_driver(0)
        except usb.core.USBError as e:
            sys.exit('Could not detatch kernel driver: %s' % str(e))

    if dev != None:
        print("DualShock 4 online!")
        menu()
