# What a worker on a lent machine keeps to, so it never gets in its owner's way
# (docs/compute.md): it only trains when nobody has touched the machine for a
# while and it's on mains power, uses at most half the CPU at low priority,
# pauses when the GPU runs hot, and gives the job back when another program
# (a game) starts using the GPU. Rented machines skip all of it.
#
# Rules are the settings; Watch reads the machine every few seconds and says
# what the worker may do right now: go, pause (suspend the job) or stop (hand
# it back to the queue). The readers for each OS are in Probes.

import ctypes
import re
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, NamedTuple

import psutil

from .log import Logger

log = Logger('machine')

EVERY = 2
# another program on the GPU: this share of its 3D engine or this much of its memory, for this long
OTHERS_SHARE = 0.2
OTHERS_GB = 1.0
OTHERS_SECONDS = 10
COOL = 5


@dataclass(frozen=True)
class Rules:
    cooldown: float = 10      # minutes without keyboard or mouse before training; 0 = while in use too
    battery: bool = False     # also train on battery
    cpu: float = 0.5          # share of the cores
    gpu_temp: float = 85      # pause above this (°C) until it's COOL below; 0 = no limit
    share_gpu: bool = False   # keep training while other programs use the GPU
    suspended: float = 30     # minutes a job may sit paused before it goes back to the queue
    keep_gb: float = 2        # space for the runs this machine made, oldest deleted first

    @classmethod
    def anytime(cls) -> 'Rules':
        """A rented machine: nobody else is using it."""
        return cls(cooldown=0, battery=True, cpu=1, gpu_temp=0, share_gpu=True)



def load(path: Path, **overrides) -> Rules:
    """Defaults, then the settings file, then flags. Unknown or mistyped keys are an error, like the sim's configs."""
    rules = Rules()
    if path.exists():
        with open(path, 'rb') as f:
            raw = tomllib.load(f)
        types = {f.name: f.type for f in fields(Rules) if isinstance(f.type, type)}
        for key, value in raw.items():
            if key not in types:
                raise ValueError(f'{path.name}: unknown setting {key!r} (known: {", ".join(types)})')
            if types[key] is float and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            if not isinstance(value, types[key]):
                raise ValueError(f'{path.name}: {key} should be {types[key].__name__}')
        rules = replace(rules, **raw)
    rules = replace(rules, **{k: v for k, v in overrides.items() if v is not None})
    if not 0 < rules.cpu <= 1:
        raise ValueError(f'cpu is a share of the cores, above 0 and at most 1, not {rules.cpu}')
    return rules


class Seen(NamedTuple):
    idle: float | None          # seconds since the last key or mouse input; None: can't tell
    plugged: bool | None        # None: no battery
    temp: float | None          # hottest GPU, °C
    others: tuple[float, float] | None  # other programs on the GPU: (3D share, GB); None: can't tell
    fullscreen: bool            # a game or presentation has the screen


class Verdict(NamedTuple):
    action: str  # go, pause, stop
    reason: str


class Watch:
    def __init__(self, rules: Rules, probes: 'Probes | None' = None):
        self.rules, self.probes = rules, probes
        self.busy_since: float | None = None
        self.hot = False
        self.seen: Seen | None = None
        if rules != Rules.anytime() and probes is None:
            self.probes = Probes()

    def check(self, ours: frozenset[int] = frozenset(), now: float | None = None) -> Verdict:
        if self.probes is None:
            return Verdict('go', 'rented: no rules')
        now = time.time() if now is None else now
        r, seen = self.rules, self.probes.read(ours)
        self.seen = seen
        busy = seen.others is not None and (seen.others[0] > OTHERS_SHARE or seen.others[1] > OTHERS_GB)
        since = self.busy_since = (self.busy_since or now) if busy else None
        if seen.temp is not None and r.gpu_temp:
            self.hot = seen.temp > r.gpu_temp or (self.hot and seen.temp > r.gpu_temp - COOL)
        if not r.share_gpu:
            if seen.fullscreen:
                return Verdict('stop', 'something is running full screen')
            if since is not None and (not ours or now - since >= OTHERS_SECONDS):
                return Verdict('stop', 'another program is using the GPU')
        if not r.battery and seen.plugged is False:
            return Verdict('pause', 'on battery')
        if r.cooldown and seen.idle is not None and seen.idle < r.cooldown * 60:
            return Verdict('pause', f'in use (idle {seen.idle / 60:.0f} of {r.cooldown:g} min)')
        if self.hot:
            return Verdict('pause', f'GPU at {seen.temp:.0f} °C')
        return Verdict('go', 'idle' if r.cooldown else 'allowed while in use')


class Probes:
    """Reads the machine. Anything that can't be read comes back None and its rule is skipped."""

    def __init__(self):
        self.smi = shutil.which('nvidia-smi')
        self.gpu = Pdh() if sys.platform == 'win32' else None

    def read(self, ours: frozenset[int]) -> Seen:
        return Seen(idle(), plugged(), self.temp(), self.others(ours), fullscreen())

    def temp(self) -> float | None:
        if not self.smi:
            return None
        out = run([self.smi, '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'])
        temps = [float(t) for t in out.split() if re.fullmatch(r'\d+(\.\d+)?', t)]
        return max(temps) if temps else None

    def others(self, ours: frozenset[int]) -> tuple[float, float] | None:
        if self.gpu:
            return self.gpu.others(ours)
        if self.smi and sys.platform == 'linux':
            return pmon(run([self.smi, 'pmon', '-c', '1', '-s', 'um']), ours)
        return None


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def idle() -> float | None:
    if sys.platform == 'win32':
        class LastInput(ctypes.Structure):
            _fields_ = [('size', ctypes.c_uint), ('time', ctypes.c_uint)]
        last = LastInput(ctypes.sizeof(LastInput), 0)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last)):
            return None
        # both are 32-bit milliseconds since boot, which wrap after 49 days
        return ((ctypes.windll.kernel32.GetTickCount() - last.time) & 0xFFFFFFFF) / 1000
    if sys.platform == 'darwin':
        found = re.search(r'"HIDIdleTime" = (\d+)', run(['ioreg', '-c', 'IOHIDSystem', '-d', '4']))
        return int(found.group(1)) / 1e9 if found else None
    # X and Wayland have no one way to ask; Linux machines count as idle
    return None


def plugged() -> bool | None:
    battery = psutil.sensors_battery()
    return None if battery is None or battery.power_plugged is None else bool(battery.power_plugged)


def fullscreen() -> bool:
    if sys.platform != 'win32':
        return False
    state = ctypes.c_int(0)
    if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    # QUNS_BUSY (a full-screen app), QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE
    return state.value in (2, 3, 4)


def pmon(text: str, ours: frozenset[int]) -> tuple[float, float] | None:
    """nvidia-smi pmon -s um: the sm % and frame-buffer MB of every process but ours. Columns vary by driver."""
    header = next((line[1:].split() for line in text.splitlines() if line.startswith('#')), None)
    if not header or not {'pid', 'sm', 'fb'} <= set(header):
        return None
    share = gb = 0.0
    for line in text.splitlines():
        cols = line.split()
        if line.startswith('#') or len(cols) < len(header) - 1 or not cols[header.index('pid')].isdigit():
            continue
        if int(cols[header.index('pid')]) in ours:
            continue
        sm, fb = cols[header.index('sm')], cols[header.index('fb')]
        share = max(share, int(sm) / 100 if sm.isdigit() else 0)
        gb += int(fb) / 1024 if fb.isdigit() else 0
    return share, gb


# Windows: who's on the GPU, from the counters Task Manager shows

PDH_MORE_DATA = 0x800007D2
PDH_FMT_DOUBLE = 0x200
INSTANCE = re.compile(r'pid_(\d+)_luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)')


class Pdh:
    def __init__(self):
        self.ok, self.luids = False, set()
        self.pdh: Any = None
        self.query, self.engine, self.memory = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            assert sys.platform == 'win32'
            self.pdh = ctypes.windll.pdh
            for name in ('PdhOpenQueryW', 'PdhAddEnglishCounterW', 'PdhCollectQueryData', 'PdhGetFormattedCounterArrayW'):
                # PDH_STATUS is unsigned; PDH_MORE_DATA would come back negative
                getattr(self.pdh, name).restype = ctypes.c_uint
            # English counter names, so a German or Japanese Windows works too
            if self.pdh.PdhOpenQueryW(None, None, ctypes.byref(self.query)) or \
                    self.pdh.PdhAddEnglishCounterW(self.query, r'\GPU Engine(*)\Utilization Percentage', None,
                                                   ctypes.byref(self.engine)) or \
                    self.pdh.PdhAddEnglishCounterW(self.query, r'\GPU Process Memory(*)\Dedicated Usage', None,
                                                   ctypes.byref(self.memory)):
                raise OSError('GPU counters unavailable')
            self.pdh.PdhCollectQueryData(self.query)
            self.luids = nvidia_luids()
            self.ok = True
            log.info('watching the GPU through its performance counters', nvidia=sorted(self.luids) or 'not found')
        except (OSError, AttributeError) as e:
            log.warn("can't read GPU counters; only full-screen programs will stop a job", error=str(e))

    def others(self, ours: frozenset[int]) -> tuple[float, float] | None:
        if not self.ok or self.pdh.PdhCollectQueryData(self.query):
            return None
        return gpu_use(self.values(self.engine), self.values(self.memory), self.luids, ours)

    def values(self, counter) -> list[tuple[str, float]]:
        class Item(ctypes.Structure):
            _fields_ = [('name', ctypes.c_wchar_p), ('status', ctypes.c_uint), ('value', ctypes.c_double)]
        size, count = ctypes.c_uint(0), ctypes.c_uint(0)
        if self.pdh.PdhGetFormattedCounterArrayW(counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count),
                                                 None) != PDH_MORE_DATA:
            return []
        buf = ctypes.create_string_buffer(size.value)
        if self.pdh.PdhGetFormattedCounterArrayW(counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count),
                                                 buf):
            return []
        items = ctypes.cast(buf, ctypes.POINTER(Item))
        return [(items[i].name, items[i].value) for i in range(count.value) if items[i].status == 0]


def gpu_use(engines: list[tuple[str, float]], memory: list[tuple[str, float]], luids: set[str],
            ours: frozenset[int], name=None) -> tuple[float, float]:
    """The busiest other process's share of a 3D engine, and all other processes' dedicated GPU memory in GB,
    on the NVIDIA GPU. dwm.exe, the desktop itself, never counts."""
    name = name or process_name
    seen = {m.group(2).lower() for n, _ in engines + memory if (m := INSTANCE.search(n))}
    # if the adapter ids don't match the counters' at all, count every adapter rather than none
    keep = luids & seen

    def who(instance: str) -> int | None:
        found = INSTANCE.search(instance)
        if not found:
            return None
        pid, luid = int(found.group(1)), found.group(2).lower()
        if pid in ours or (keep and luid not in keep) or name(pid) == 'dwm.exe':
            return None
        return pid

    share: dict[int, float] = {}
    for instance, value in engines:
        if 'engtype_3D' in instance and (pid := who(instance)) is not None:
            share[pid] = share.get(pid, 0) + value / 100
    gb = sum(value / 2**30 for instance, value in memory if who(instance) is not None)
    return max(share.values(), default=0.0), gb


def process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name().lower()
    except psutil.Error:
        return ''


def nvidia_luids() -> set[str]:
    """The adapter ids of NVIDIA GPUs (vendor 0x10de), as the counters name them. Empty: count every adapter."""
    class Guid(ctypes.Structure):
        _fields_ = [('a', ctypes.c_uint), ('b', ctypes.c_ushort), ('c', ctypes.c_ushort), ('d', ctypes.c_ubyte * 8)]

    class Desc(ctypes.Structure):
        _fields_ = [('description', ctypes.c_wchar * 128), ('vendor', ctypes.c_uint), ('device', ctypes.c_uint),
                    ('subsys', ctypes.c_uint), ('revision', ctypes.c_uint), ('video', ctypes.c_size_t),
                    ('system', ctypes.c_size_t), ('shared', ctypes.c_size_t), ('low', ctypes.c_uint),
                    ('high', ctypes.c_int), ('flags', ctypes.c_uint)]

    assert sys.platform == 'win32'

    def method(obj, index, *types):
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(vtable[index])

    # IDXGIFactory1 {770aae78-f26f-4dba-a829-253c83d1b387}
    iid = Guid(0x770aae78, 0xf26f, 0x4dba, (ctypes.c_ubyte * 8)(0xa8, 0x29, 0x25, 0x3c, 0x83, 0xd1, 0xb3, 0x87))
    factory, luids = ctypes.c_void_p(), set()
    try:
        if ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)):
            return luids
        i = 0
        while True:
            adapter = ctypes.c_void_p()
            # IDXGIFactory1::EnumAdapters1 is vtable slot 12, IDXGIAdapter1::GetDesc1 slot 10, Release slot 2
            if method(factory, 12, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(factory, i, ctypes.byref(adapter)):
                break
            desc = Desc()
            if not method(adapter, 10, ctypes.POINTER(Desc))(adapter, ctypes.byref(desc)) and desc.vendor == 0x10DE:
                luids.add(f'0x{desc.high & 0xFFFFFFFF:08x}_0x{desc.low:08x}')
            method(adapter, 2)(adapter)
            i += 1
        method(factory, 2)(factory)
    except (OSError, AttributeError) as e:
        log.warn("couldn't list the GPUs; counting every adapter", error=str(e))
    return luids


# CPU share and priority

_job = None


def limit(rules: Rules):
    """Low priority, and on Windows a job object (job_object). Elsewhere the CPU share is kept by how many
    threads and rollout processes a job gets."""
    if rules == Rules.anytime():
        return
    if sys.platform == 'win32':
        global _job
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        _job = job_object(rules.cpu)
    else:
        psutil.Process().nice(10)


def job_object(share: float):
    """Puts the worker, and so everything it starts, in a job object: capped at share of all cores (if under 1),
    and killed with the worker, so a job can't outlive a worker that crashed and keep the GPU from a game."""
    assert sys.platform == 'win32'

    class Basic(ctypes.Structure):
        _fields_ = [('user_time', ctypes.c_int64), ('job_time', ctypes.c_int64), ('flags', ctypes.c_uint),
                    ('min_set', ctypes.c_size_t), ('max_set', ctypes.c_size_t), ('processes', ctypes.c_uint),
                    ('affinity', ctypes.c_size_t), ('priority', ctypes.c_uint), ('scheduling', ctypes.c_uint)]

    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

    class Rate(ctypes.Structure):
        _fields_ = [('flags', ctypes.c_uint), ('rate', ctypes.c_uint)]

    kernel = ctypes.windll.kernel32
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    job = kernel.CreateJobObjectW(None, None)
    handle = ctypes.c_void_p(job)
    # JobObjectExtendedLimitInformation with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    limits = Extended(Basic(flags=0x2000))
    ok = job and kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
    if ok and share < 1:
        # JobObjectCpuRateControlInformation, ENABLE | HARD_CAP; the rate is hundredths of a percent of all cores
        rate = Rate(0x1 | 0x4, max(1, int(share * 10000)))
        ok = kernel.SetInformationJobObject(handle, 15, ctypes.byref(rate), ctypes.sizeof(rate))
    ok = ok and kernel.AssignProcessToJobObject(handle, ctypes.c_void_p(kernel.GetCurrentProcess()))
    if ok:
        log.info('in a job object', cpu=share)
    else:
        log.warn("couldn't make a job object; only the thread count keeps the CPU down", error=ctypes.GetLastError())
    return job


def tree(pid: int) -> list[psutil.Process]:
    try:
        top = psutil.Process(pid)
        return [top, *top.children(recursive=True)]
    except psutil.Error:
        return []


def suspend(pid: int):
    for p in reversed(tree(pid)):
        try:
            p.suspend()
        except psutil.Error:
            pass


def resume(pid: int):
    for p in tree(pid):
        try:
            p.resume()
        except psutil.Error:
            pass


def kill(pid: int, wait: float = 10):
    procs = tree(pid)
    for p in procs:
        try:
            p.resume()
            p.terminate()
        except psutil.Error:
            pass
    _, left = psutil.wait_procs(procs, timeout=wait)
    for p in left:
        try:
            p.kill()
        except psutil.Error:
            pass
