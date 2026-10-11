#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
# Copyright (C) 2026 by I.C.KaZe
"""Compare 0.13 and 0.14 built with identical compiler flags; no external packages."""
import ctypes as C
import json
import random
import sys
import time
import statistics
from pathlib import Path

class Event(C.Structure):
    _fields_ = [('clock_offset', C.c_uint32), ('address', C.c_uint32), ('value', C.c_uint32)]

def check(condition):
    if not condition:
        raise RuntimeError('Differential verification failed')

def library(path):
    lib = C.CDLL(str(Path(path).resolve()))
    h, u, f = C.c_void_p, C.c_uint32, C.POINTER(C.c_float)
    signatures = {
        'create': [u,u,C.POINTER(h)], 'destroy': [h], 'reset': [h],
        'clone': [h,C.POINTER(h)], 'write_register': [h,u,u],
        'set_measured_output_timing': [h,u], 'set_output_delays': [h,u,u,u],
        'render_f32': [h,f,u], 'render_s16': [h,C.POINTER(C.c_int16),u],
        'render_channels_f32': [h,f,f,u],
        'render_events_channels_f32': [h,f,f,u,C.POINTER(Event),u],
        'state_size': [h,C.POINTER(u)], 'save_state': [h,h,u,C.POINTER(u)],
        'load_state': [h,h,u]}
    for name, args in signatures.items():
        fn = getattr(lib, 'iopm_'+name)
        fn.argtypes = args
        fn.restype = None if name == 'destroy' else C.c_int32
    return lib

def create(lib, clock, rate):
    h=C.c_void_p()
    check(lib.iopm_create(clock,rate,C.byref(h))==0)
    return h

def state(lib,h):
    size=C.c_uint32()
    check(lib.iopm_state_size(h,C.byref(size))==0)
    buf=C.create_string_buffer(size.value)
    check(lib.iopm_save_state(h,buf,len(buf),C.byref(size))==0)
    return buf.raw

def setup(lib,h,lfo):
    writes=[(0x18,230),(0x19,127 if lfo else 0),(0x19,255 if lfo else 128)]
    for ch in range(8):
        writes += [(0x20+ch,0xc0|ch),(0x28+ch,0x40+ch),(0x38+ch,0x73 if lfo else 0)]
        for slot in range(4):
            offset=8*slot+ch
            writes += [(0x40+offset,1),(0x60+offset,slot*8),(0x80+offset,31),(0xa0+offset,128 if lfo else 0),(0xc0+offset,0),(0xe0+offset,0)]
        writes += [(8,0x78|ch)]
    for a,v in writes:check(lib.iopm_write_register(h,a,v)==0)

libs=[library(p) for p in sys.argv[1:3]]
check(len(libs)==2)
cases=[]
for case in range(16):
    clock=[3579545,4000000,8000000][case%3]
    rate=[8000,44100,48000,96000][case%4]
    handles=[create(lib,clock,rate) for lib in libs]
    for lib,h in zip(libs,handles):
        setup(lib,h,True)
        check(lib.iopm_set_measured_output_timing(h,case%2)==0)
        check(lib.iopm_set_output_delays(h,case%8,case%16,(case*3)%16)==0)
        check(lib.iopm_write_register(h,0x1b,case%4)==0)
        check(lib.iopm_write_register(h,0xf,0x80|case)==0)
        for a,v in [(0x10,251),(0x11,2),(0x12,254),(0x14,143)]:check(lib.iopm_write_register(h,a,v)==0)
    rng=random.Random(1400+case)
    frames=12288
    events=(Event*1000)(*sorted([Event(rng.randrange(frames*clock//rate),rng.randrange(256),rng.randrange(256)) for _ in range(1000)],key=lambda e:e.clock_offset))
    outputs=[]
    for lib,h in zip(libs,handles):
        mix=(C.c_float*(2*frames))();channels=(C.c_float*(16*frames))()
        check(lib.iopm_render_events_channels_f32(h,mix,channels,frames,events,len(events))==0)
        outputs.append((bytes(mix),bytes(channels),state(lib,h)))
    check(outputs[0]==outputs[1])
    for lib,h in zip(libs,handles):
        data=outputs[0][2]
        check(lib.iopm_load_state(h,data,len(data))==0)
    clones=[]
    for lib,h in zip(libs,handles):
        clone=C.c_void_p();check(lib.iopm_clone(h,C.byref(clone))==0);clones.append(clone)
    for method,ctype in [('render_f32',C.c_float),('render_s16',C.c_int16)]:
        out=[]
        for lib,h,clone in zip(libs,handles,clones):
            a=(ctype*4096)();b=(ctype*4096)()
            check(getattr(lib,'iopm_'+method)(h,a,2048)==0)
            check(getattr(lib,'iopm_'+method)(clone,b,2048)==0)
            check(bytes(a)==bytes(b));out.append((bytes(a),state(lib,h)))
        check(out[0]==out[1])
    for lib,h,clone in zip(libs,handles,clones):
        check(lib.iopm_reset(h)==0);lib.iopm_destroy(clone)
    check(state(libs[0],handles[0])==state(libs[1],handles[1]))
    for lib,h in zip(libs,handles):lib.iopm_destroy(h)
    cases.append({'case':case,'clock':clock,'rate':rate,'frames':frames,'equal':True})
bench=[]
for lfo in (False,True):
    for channels in (False,True):
        times=[[],[]]
        for run in range(5):
            for index in (range(2) if run%2==0 else range(1,-1,-1)):
                lib=libs[index];h=create(lib,4000000,48000);setup(lib,h,lfo)
                mix=(C.c_float*96000)();ch=(C.c_float*768000)()
                start=time.perf_counter()
                result=lib.iopm_render_channels_f32(h,mix,ch,48000) if channels else lib.iopm_render_f32(h,mix,48000)
                times[index].append((time.perf_counter()-start)*1000);check(result==0);lib.iopm_destroy(h)
        medians=[statistics.median(t) for t in times]
        bench.append({'lfo':lfo,'channels':channels,'baseline_ms':medians[0],'optimized_ms':medians[1],'speedup':medians[0]/medians[1],'runs_ms':times})
print(json.dumps({'cases':cases,'total_frames':196608,'benchmarks':bench},indent=2))
