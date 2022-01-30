#!/usr/bin/env python3
# 
# Cross Platform and Multi Architecture Advanced Binary Emulation Framework
#

from struct import pack
from functools import cached_property
from typing import Union

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_MODE_32, UC_MODE_64
from capstone import Cs, CS_ARCH_X86, CS_MODE_16, CS_MODE_32, CS_MODE_64
from keystone import Ks, KS_ARCH_X86, KS_MODE_16, KS_MODE_32, KS_MODE_64

from qiling import Qiling
from qiling.arch.arch import QlArch
from qiling.arch.msr import QlMsrManager
from qiling.arch.register import QlRegisterManager
from qiling.arch import x86_const
from qiling.arch.x86_const import *
from qiling.const import QL_ARCH, QL_ENDIAN
from qiling.exception import QlGDTError

class QlArchIntel(QlArch):
    @property
    def endian(self) -> QL_ENDIAN:
        return QL_ENDIAN.EL

    @cached_property
    def msr(self) -> QlMsrManager:
        """Model-Specific Registers.
        """

        return QlMsrManager(self.uc)

class QlArchA8086(QlArchIntel):
    type = QL_ARCH.A8086
    bits = 16

    @cached_property
    def uc(self) -> Uc:
        return Uc(UC_ARCH_X86, UC_MODE_16)

    @cached_property
    def regs(self) -> QlRegisterManager:
        regs_map = dict(
            **x86_const.reg_map_8,
            **x86_const.reg_map_16,
            **x86_const.reg_map_misc
        )

        pc_reg = 'ip'
        sp_reg = 'sp'

        return QlRegisterManager(self.uc, regs_map, pc_reg, sp_reg)

    @cached_property
    def disassembler(self) -> Cs:
        return Cs(CS_ARCH_X86, CS_MODE_16)

    @cached_property
    def assembler(self) -> Ks:
        return Ks(KS_ARCH_X86, KS_MODE_16)

class QlArchX86(QlArchIntel):
    type = QL_ARCH.X86
    bits = 32

    @cached_property
    def uc(self) -> Uc:
        return Uc(UC_ARCH_X86, UC_MODE_32)

    @cached_property
    def regs(self) -> QlRegisterManager:
        regs_map = dict(
            **x86_const.reg_map_8,
            **x86_const.reg_map_16,
            **x86_const.reg_map_32,
            **x86_const.reg_map_cr,
            **x86_const.reg_map_st,
            **x86_const.reg_map_misc
        )

        pc_reg = 'eip'
        sp_reg = 'esp'

        return QlRegisterManager(self.uc, regs_map, pc_reg, sp_reg)

    @cached_property
    def disassembler(self) -> Cs:
        return Cs(CS_ARCH_X86, CS_MODE_32)

    @cached_property
    def assembler(self) -> Ks:
        return Ks(KS_ARCH_X86, KS_MODE_32)

class QlArchX8664(QlArchIntel):
    type = QL_ARCH.X8664
    bits = 64

    @cached_property
    def uc(self) -> Uc:
        return Uc(UC_ARCH_X86, UC_MODE_64)

    @cached_property
    def regs(self) -> QlRegisterManager:
        regs_map = dict(
            **x86_const.reg_map_8,
            **x86_const.reg_map_16,
            **x86_const.reg_map_32,
            **x86_const.reg_map_64,
            **x86_const.reg_map_cr,
            **x86_const.reg_map_st,
            **x86_const.reg_map_misc,
            **x86_const.reg_map_64_b,
            **x86_const.reg_map_64_w,
            **x86_const.reg_map_64_d,
            **x86_const.reg_map_seg_base
        )

        pc_reg = 'rip'
        sp_reg = 'rsp'

        return QlRegisterManager(self.uc, regs_map, pc_reg, sp_reg)
    @cached_property
    def disassembler(self) -> Cs:
        return Cs(CS_ARCH_X86, CS_MODE_64)

    @cached_property
    def assembler(self) -> Ks:
        return Ks(KS_ARCH_X86, KS_MODE_64)

    # TODO: generalize this
    def __reg_bits(self, register: int) -> int:
        # all regs in reg_map_misc are 16 bits except of eflags
        if register == UC_X86_REG_EFLAGS:
            return 32

        regmaps = (
            (x86_const.reg_map_8, 8),
            (x86_const.reg_map_16, 16),
            (x86_const.reg_map_32, 32),
            (x86_const.reg_map_64, 64),
            (x86_const.reg_map_misc, 16),
            (x86_const.reg_map_cr, 64),         # 32 bits for x86
            (x86_const.reg_map_st, 32),
            (x86_const.reg_map_seg_base, 64),   # 32 bits for x86
        )

        return next((rsize for rmap, rsize in regmaps if register in rmap.values()), 0)

    # note: this method was not generalized for all archs since it requires a bookkeeping
    # of all registers, while it is used only by gdb and only for x86-64
    def reg_bits(self, reg: Union[str, int]) -> int:
        """Get register size in bits.
        """

        if type(reg) is str:
            reg = self.regs.register_mapping[reg]

        return self.__reg_bits(reg)

class GDTManager:
    # Added GDT management module.
    def __init__(self, ql: Qiling, GDT_ADDR = QL_X86_GDT_ADDR, GDT_LIMIT =  QL_X86_GDT_LIMIT, GDT_ENTRY_ENTRIES = 16):
        ql.log.debug(f"Map GDT at {hex(GDT_ADDR)} with GDT_LIMIT={GDT_LIMIT}")

        if not ql.mem.is_mapped(GDT_ADDR, GDT_LIMIT):
            ql.mem.map(GDT_ADDR, GDT_LIMIT, info="[GDT]")

        # setup GDT by writing to GDTR
        ql.arch.regs.write(UC_X86_REG_GDTR, (0, GDT_ADDR, GDT_LIMIT, 0x0))

        self.ql = ql
        self.gdt_number = GDT_ENTRY_ENTRIES
        # self.gdt_used = [False] * GDT_ENTRY_ENTRIES
        self.gdt_addr = GDT_ADDR
        self.gdt_limit = GDT_LIMIT


    def register_gdt_segment(self, index: int, SEGMENT_ADDR: int, SEGMENT_SIZE: int, SPORT, RPORT):
        # FIXME: Temp fix for FS and GS
        if index in (14, 15):
            if not self.ql.mem.is_mapped(SEGMENT_ADDR, SEGMENT_ADDR):
                self.ql.mem.map(SEGMENT_ADDR, SEGMENT_ADDR, info="[FS/GS]")

        if index < 0 or index >= self.gdt_number:
            raise QlGDTError("Ql GDT register index error!")
        # create GDT entry, then write GDT entry into GDT table
        gdt_entry = self._create_gdt_entry(SEGMENT_ADDR, SEGMENT_SIZE, SPORT, QL_X86_F_PROT_32)
        self.ql.mem.write(self.gdt_addr + (index << 3), gdt_entry)
        # self.gdt_used[index] = True
        self.ql.log.debug(f"Write to {hex(self.gdt_addr + (index << 3))} for new entry {gdt_entry}")


    def get_gdt_buf(self, start: int, end: int) -> bytearray:
        return self.ql.mem.read(self.gdt_addr + (start << 3), (end << 3) - (start << 3))


    def set_gdt_buf(self, start: int, end: int, buf: bytes) -> None:
        self.ql.mem.write(self.gdt_addr + (start << 3), buf[ : (end << 3) - (start << 3)])


    def get_free_idx(self, start: int = 0, end: int = -1) -> int:
        # The Linux kernel determines whether the segment is empty by judging whether the content in the current GDT segment is 0.
        if end == -1:
            end = self.gdt_number

        for i in range(start, end):
            if self.ql.unpack64(self.ql.mem.read(self.gdt_addr + (i << 3), 8)) == 0:
                return i

        return -1


    def _create_gdt_entry(self, base, limit, access, flags):
        to_ret = limit & 0xffff
        to_ret |= (base & 0xffffff) << 16
        to_ret |= (access & 0xff) << 40
        to_ret |= ((limit >> 16) & 0xf) << 48
        to_ret |= (flags & 0xff) << 52
        to_ret |= ((base >> 24) & 0xff) << 56
        return pack('<Q', to_ret)


    def _create_selector(self, idx, flags):
        to_ret = flags
        to_ret |= idx << 3
        return to_ret


    def create_selector(self, idx, flags):
        return self._create_selector(idx, flags)


def ql_x86_register_cs(self):
    # While debugging the linux kernel segment, the cs segment was found on the third segment of gdt.
    self.gdtm.register_gdt_segment(3, 0, 0xfffff000, QL_X86_A_PRESENT | QL_X86_A_CODE | QL_X86_A_CODE_READABLE | QL_X86_A_PRIV_3 | QL_X86_A_EXEC | QL_X86_A_DIR_CON_BIT, QL_X86_S_GDT | QL_X86_S_PRIV_3)
    self.ql.arch.regs.cs = self.gdtm.create_selector(3, QL_X86_S_GDT | QL_X86_S_PRIV_3)


def ql_x8664_register_cs(self):
    # While debugging the linux kernel segment, the cs segment was found on the sixth segment of gdt.
    self.gdtm.register_gdt_segment(6, 0, 0xfffffffffffff000, QL_X86_A_PRESENT | QL_X86_A_CODE | QL_X86_A_CODE_READABLE | QL_X86_A_PRIV_3 | QL_X86_A_EXEC | QL_X86_A_DIR_CON_BIT, QL_X86_S_GDT | QL_X86_S_PRIV_3)
    self.ql.arch.regs.cs = self.gdtm.create_selector(6, QL_X86_S_GDT | QL_X86_S_PRIV_3)


def ql_x86_register_ds_ss_es(self):
    # TODO : The section permission here should be QL_X86_A_PRIV_3, but I do n’t know why it can only be set to QL_X86_A_PRIV_0.
    # While debugging the Linux kernel segment, I found that the three segments DS, SS, and ES all point to the same location in the GDT table. 
    # This position is the fifth segment table of GDT.
    self.gdtm.register_gdt_segment(5, 0, 0xfffff000, QL_X86_A_PRESENT | QL_X86_A_DATA | QL_X86_A_DATA_WRITABLE | QL_X86_A_PRIV_0 | QL_X86_A_DIR_CON_BIT, QL_X86_S_GDT | QL_X86_S_PRIV_0)
    self.ql.arch.regs.ds = self.gdtm.create_selector(5, QL_X86_S_GDT | QL_X86_S_PRIV_0)
    self.ql.arch.regs.ss = self.gdtm.create_selector(5, QL_X86_S_GDT | QL_X86_S_PRIV_0)
    self.ql.arch.regs.es = self.gdtm.create_selector(5, QL_X86_S_GDT | QL_X86_S_PRIV_0)


def ql_x8664_register_ds_ss_es(self):
    # TODO : The section permission here should be QL_X86_A_PRIV_3, but I do n’t know why it can only be set to QL_X86_A_PRIV_0.
    # When I debug the Linux kernel, I find that only the SS is set to the fifth segment table, and the rest are not set.
    self.gdtm.register_gdt_segment(5, 0, 0xfffff000, QL_X86_A_PRESENT | QL_X86_A_DATA | QL_X86_A_DATA_WRITABLE | QL_X86_A_PRIV_0 | QL_X86_A_DIR_CON_BIT, QL_X86_S_GDT | QL_X86_S_PRIV_0)
    # ql.arch.regs.write(UC_X86_REG_DS, ql.os.gdtm.create_selector(5, QL_X86_S_GDT | QL_X86_S_PRIV_0))
    self.ql.arch.regs.ss = self.gdtm.create_selector(5, QL_X86_S_GDT | QL_X86_S_PRIV_0)
    # ql.arch.regs.write(UC_X86_REG_ES, ql.os.gdtm.create_selector(5, QL_X86_S_GDT | QL_X86_S_PRIV_0))


def ql_x86_register_gs(self):
    self.gdtm.register_gdt_segment(15, GS_SEGMENT_ADDR, GS_SEGMENT_SIZE, QL_X86_A_PRESENT | QL_X86_A_DATA | QL_X86_A_DATA_WRITABLE | QL_X86_A_PRIV_3 | QL_X86_A_DIR_CON_BIT, QL_X86_S_GDT |  QL_X86_S_PRIV_3)
    self.ql.arch.regs.gs = self.gdtm.create_selector(15, QL_X86_S_GDT | QL_X86_S_PRIV_0)


def ql_x86_register_fs(self):
    self.gdtm.register_gdt_segment(14, FS_SEGMENT_ADDR, FS_SEGMENT_SIZE, QL_X86_A_PRESENT | QL_X86_A_DATA | QL_X86_A_DATA_WRITABLE | QL_X86_A_PRIV_3 | QL_X86_A_DIR_CON_BIT, QL_X86_S_GDT |  QL_X86_S_PRIV_3)
    self.ql.arch.regs.fs = self.gdtm.create_selector(14,  QL_X86_S_GDT |  QL_X86_S_PRIV_3)


def ql_x8664_set_gs(ql: Qiling):
    if not ql.mem.is_mapped(GS_SEGMENT_ADDR, GS_SEGMENT_SIZE):
        ql.mem.map(GS_SEGMENT_ADDR, GS_SEGMENT_SIZE, info="[GS]")

    ql.arch.msr.write(GSMSR, GS_SEGMENT_ADDR)


def ql_x8664_get_gs(ql: Qiling):
    return ql.arch.msr.read(GSMSR)


def ql_x8664_set_fs(ql: Qiling, addr: int):
    ql.arch.msr.write(FSMSR, addr)


def ql_x8664_get_fs(ql: Qiling):
    return ql.arch.msr.read(FSMSR)
