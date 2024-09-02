## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.
##

# Adapted from https://github.com/CamiAlfa/M365_DRV_STLINK.git

import sys
import argparse
import openocd
from os import path, remove
from util import Util
from struct import pack, unpack
import re


class Flasher(object):
    def __init__(self, oocd, packfile, binfile, outfile, tmpfile="data.tmp"):
        self.oocd = oocd
        self.UUID = [0x12345678, 0x9ABCDEF0, 0x12345678]
        if not path.isfile(packfile):
            raise Exception("Resource pack not found")
        self.data = Util.unpack_res(packfile)
        self.binfile = binfile
        self.outfile = outfile
        self.tmpfile = tmpfile

    def init(self):
        print("halting device...")
        if self.oocd:
            self.oocd.send("init")
            self.oocd.send("reset halt")

    def reset(self):
        print("resetting device...")
        if self.oocd:
            self.oocd.send("reset run")

    def unlock_stm32(self):
        print("unsecuring device...")
        if self.oocd:
            self.oocd.send("stm32f1x unlock 0")
            self.oocd.send("reset halt")

    def unlock_gd32(self):
        print("unsecuring device...")
        if self.oocd:
            self.oocd.read_memory(0x40022100, 1)
            self.oocd.write_memory(0x40022004, 0x45670123)
            self.oocd.write_memory(0x40022004, 0xCDEF89AB)
            self.oocd.write_memory(0x4002200C, 0x34)
            self.oocd.write_memory(0x4002200C, 1)
            self.oocd.write_memory(0x40022008, 0x45670123)
            self.oocd.write_memory(0x40022008, 0xCDEF89AB)
            self.oocd.read_memory(0x40022100, 1)
            self.oocd.write_memory(0x40022100, 0x220)
            self.oocd.write_memory(0x40022100, 0x260)
            self.oocd.read_memory(0x4002200C, 1)
            self.oocd.write_memory(0x4002200C, 0x200)
            self.oocd.write_memory(0x4002200C, 0x210)
            self.oocd.write_memory(0x1FFFF800, 0xFFFF00A5)
            self.oocd.read_memory(0x4002200C, 1)
            self.oocd.write_memory(0x40022010, 0x80)

    def mass_erase(self):
        print("erasing device...")
        if self.oocd:
            self.oocd.send("nrf51 mass_erase")
            self.oocd.send("reset halt")

    def read_uuid(self):
        print("reading UUID...")
        if self.oocd:
            self.UUID = self.oocd.read_memory(0x1FFFF7E8, 3)
        print("UUID (chip): %s" % " ".join([Util.word2bytes(uuid).hex() for uuid in self.UUID]))
        
    def set_uuid(self, uuid):
        uuid = bytes.fromhex(args.uuid)
        flasher.UUID[0] = unpack("<L", uuid[:4])[0]
        flasher.UUID[1] = unpack("<L", uuid[4:8])[0]
        flasher.UUID[2] = unpack("<L", uuid[8:])[0]
        print("UUID (user): %s" % " ".join([Util.word2bytes(uuid).hex() for uuid in flasher.UUID]))

    def prep_data(self, serial="00000/0000000", km=0):
        print("preparing sooter data...")
        sn = serial.encode()
        self.scooter_data = None
        pattern_4pro = r'[0-9]{5}/[A-Z0-9]{14}'
        if re.match(pattern_4pro, serial):
            print("opt: 4 pro data section")
            self.scooter_data = self.data['res/esc/data_4pro'].copy()
            self.scooter_data[0xa8:0xa8+len(sn)] = sn
        else:
            self.scooter_data = self.data['res/esc/data'].copy()
            self.scooter_data[0x20:0x20+len(sn)] = sn
        self.scooter_data[0x1b4:0x1b4+4] = Util.word2bytes(self.UUID[0])
        self.scooter_data[0x1b8:0x1b8+4] = Util.word2bytes(self.UUID[1])
        self.scooter_data[0x1bc:0x1bc+4] = Util.word2bytes(self.UUID[2])
        self.scooter_data[0x52:0x52+4] = Util.word2bytes(km * 1000)

    def flash_esc(self, gd32=False, at32=False, nb=False, remove_rdp=False):
        print("flashing...")
        boot = self.data['res/esc/bootldr_stm32']
        if gd32:
            print("opt: gd32")
            boot = self.data['res/esc/bootldr_gd32']
        elif nb and at32:
            print("opt: nb at32")
            boot = self.data['res/esc/bootldr_at32_nb']
        elif nb:
            print("opt: nb")
            boot = self.data['res/esc/bootldr_stm32_nb']
        data = self.scooter_data
        bin_offs = 0x1000
        data_offs = 0xf800
        if nb:
            data_offs = 0x1c000
        bin_ = Util.read_bin(self.binfile)
        if self.oocd:
            Util.write_bin(self.tmpfile, boot)
            self.oocd.write_binary(0x08000000, self.tmpfile)
            Util.write_bin(self.tmpfile, bin_)
            self.oocd.write_binary(0x08000000 + bin_offs, self.tmpfile)
            Util.write_bin(self.tmpfile, data)
            self.oocd.write_binary(0x08000000 + data_offs, self.tmpfile)
        else:
            with open(self.outfile, "wb") as f:
                for _ in range(0, data_offs + len(data)):
                    f.write(bytes.fromhex("FF"))
                f.seek(0)
                f.write(boot)
                f.seek(bin_offs)
                f.write(bin_)
                f.seek(data_offs)
                f.write(data)
        #if remove_rdp:
        #    self.oocd.write_byte(0x1FFFF800, 0xA5)

    def flash_ble(self, nb=False, ram16=False):
        if nb:
            raise Exception("NB BLE not implemented")

        print("flashing...")
        bin_addr = 0x0
        bin_upd_addr = 0x0
        boot_addr = 0x0
        data_addr = 0x0
        soft = None
        boot = None

        uicr = self.data['res/ble/uicr_32k']
        if ram16:
            uicr = self.data['res/ble/uicr_16k']
        uicr_addr = 0x10001000

        addr = uicr[0x14:0x14+4]
        if addr.hex() == "00c00300":
            print("opt: 16k")
            boot_addr = 0x3c000
            data_addr = 0x3b400
            bin_addr = 0x18000
            bin_upd_addr = 0x29800
            soft = self.data['res/ble/s110']
            boot = self.data['res/ble/bootldr_pro']
        elif addr.hex() == "00d00300":
            print("opt: 32k")
            boot_addr = 0x3d000
            data_addr = 0x3b800
            bin_addr = 0x1b000
            bin_upd_addr = 0x2b400
            soft = self.data['res/ble/s130']
            boot = self.data['res/ble/bootldr_pro2']
        else:
            raise Exception("UICR messed up")

        bin_ = Util.read_bin(self.binfile)
        if self.oocd:
            Util.write_bin(self.tmpfile, soft)
            self.oocd.write_binary(0x0, self.tmpfile)
            Util.write_bin(self.tmpfile, bin_)
            self.oocd.write_binary(bin_addr, self.tmpfile)
            Util.write_bin(self.tmpfile, boot)
            self.oocd.write_binary(boot_addr, self.tmpfile)
            Util.write_bin(self.tmpfile, uicr)
            self.oocd.write_binary(uicr_addr, self.tmpfile)
        else:
            with open(self.outfile, "wb") as f:
                for _ in range(0, boot_addr+len(boot)):
                    f.write(bytes.fromhex("FF"))
                f.seek(0x0)
                f.write(soft)
                #f.seek(data_addr)
                #f.write(data)
                f.seek(bin_addr)
                f.write(bin_)
                #f.seek(bin_upd_addr)
                #f.write(bin_)
                f.seek(boot_addr)
                f.write(boot)

    def verify(self, nb=False):
        print("verifying...")
        if self.oocd:
            uuid_offs = 0x08000000 + 0xf800 + 0x1b4
            if nb:
                uuid_offs = 0x08000000 + 0x1c000 + 0x1b4

            UUID2 = self.oocd.read_memory(uuid_offs, 3)
            if not UUID2:
                print("verify UUID failed: power cycle controller and try again")
                return


            print("UUID (flash): %s" % " ".join([Util.word2bytes(uuid).hex() for uuid in UUID2]))
            self.oocd.send("reset")
            if self.UUID[0] == UUID2[0] and self.UUID[1] == UUID2[1] and self.UUID[2] == UUID2[2]:
                print("verify UUID success")
            else:
                print("verify UUID failed: power cycle controller and try again")

    def cleanup(self):
        print("cleaning up...")
        if path.isfile(self.tmpfile):
            remove(self.tmpfile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(title="subcommands", dest="sub")
    bleparser = subparser.add_parser("ble", help="type 'ble --help' for more info")
    escparser = subparser.add_parser("esc", help="type 'esc --help' for more info")

    parser.add_argument("binfile", help="path to firmware binary to flash")
    parser.add_argument("-s", "--simulate", action="store_true", help="simulate flashing and generate OUTFILE", default=False)
    parser.add_argument("-o", "--outfile", help="path to output file", default="out.bin")
    parser.add_argument("-p", "--packfile", help="path to resource pack file", default="res.pack")

    
    bleparser.add_argument("--16k", dest="ram16", action="store_true", help="16k RAM instead of 32k RAM (m365/pro/clones)", default=False)
    bleparser.add_argument("--nb", action="store_true", help="NB instead of MI bootloaders", default=False)
    bleparser.add_argument("--norst", action="store_true", help="Don't reset after flash", default=False)
    
    escparser.add_argument("--nb", action="store_true", help="NB instead of MI bootloaders", default=False)
    escparser.add_argument("--gd32", action="store_true", help="GD32 instead of STM32 chip", default=False)
    escparser.add_argument("--at32", action="store_true", help="AT32 instead of STM32 chip", default=False)
    escparser.add_argument("--sn", help="serial number to set when flashing controller", default="13678/00110029")
    escparser.add_argument("--km", type=int, help="km to set when flashing controller", default="0")
    escparser.add_argument("--uuid", help="", default="")
    escparser.add_argument("--nordp", action="store_true", help="Remove readout protection", default=False)
    escparser.add_argument("--norst", action="store_true", help="Don't reset after flash", default=False)

    args = parser.parse_args()
    print(args)

    if not args.simulate:
        oocd = openocd.OpenOcd("localhost", 6666)
        try:
            oocd.connect()
        except Exception:
            sys.exit("Failed to connect to OpenOCD. Connect to device with OpenOCD first!")
    else:
        oocd = None

    flasher = Flasher(oocd, args.packfile, args.binfile, args.outfile)
    flasher.init()
    if args.sub == "esc":
        if not args.gd32:
            flasher.unlock_stm32()
        else:
            flasher.unlock_gd32()
        if not args.uuid:
            flasher.read_uuid()
        else:
            flasher.set_uuid(args.uuid)

        flasher.prep_data(serial=args.sn, km=args.km)
        flasher.flash_esc(nb=args.nb, gd32=args.gd32, at32=args.at32, remove_rdp=args.nordp)
        if not args.norst:
            flasher.verify(nb=args.nb)
    elif args.sub == "ble":
        flasher.mass_erase()
        flasher.flash_ble(nb=args.nb, ram16=args.ram16)
    if not args.norst:
        flasher.reset()
    flasher.cleanup()
