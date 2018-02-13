from copy import copy
from itertools import compress
from typing import List, Generator

from hwt.code import If
from hwt.hdl.architecture import Architecture
from hwt.hdl.assignment import Assignment
from hwt.hdl.entity import Entity
from hwt.hdl.ifContainter import IfContainer
from hwt.hdl.operator import Operator
from hwt.hdl.portItem import PortItem
from hwt.hdl.process import HWProcess
from hwt.hdl.statements import WaitStm, HdlStatement, HwtSyntaxError
from hwt.hdl.switchContainer import SwitchContainer
from hwt.hdl.types.defs import BIT
from hwt.hdl.value import Value
from hwt.pyUtils.arrayQuery import distinctBy
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.exceptions import SigLvlConfErr
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.memory import RtlSyncSignal
from hwt.synthesizer.rtlLevel.optimalizator import removeUnconnectedSignals, \
    reduceProcesses
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.signalUtils.exceptions import MultipleDriversErr,\
    NoDriverErr
from hwt.synthesizer.rtlLevel.utils import portItemfromSignal


def _isEnclosed(objList):
    if not objList:
        return False
    for o in objList:
        if not isEnclosed(o):
            return False
    return True


def isEnclosed(obj):
    """
    Check if statement has any not used branch
    """
    if isinstance(obj, (Assignment, WaitStm)):
        return True
    elif isinstance(obj, IfContainer):
        for ol in [obj.ifTrue, obj.ifFalse]:
            if not _isEnclosed(ol):
                return False
        for _, ol in obj.elIfs:
            if not _isEnclosed(ol):
                return False

        return True
    elif isinstance(obj, SwitchContainer):
        allCasesCovered = True
        for cond, ol in obj.cases:
            if cond is None:
                allCasesCovered = True
            if not _isEnclosed(ol):
                return False

        return allCasesCovered
    else:
        raise NotImplementedError(obj)


def inject_nop_values(statements: List[HdlStatement])\
        -> Generator[Assignment, None, None]:
    """
    Generate initialization assignments with default values to assignments
    """
    for stm in statements:
        for sig in stm._outputs:
            # inject nopVal if needed
            if sig._useNopVal and not isEnclosed(stm):
                n = sig._nopVal
                yield Assignment(n, sig)


def name_for_process_and_mark_outputs(statements: List[HdlStatement])\
        -> str:
    """
    Resolve name for process and mark outputs of statemens as not hidden
    """
    out_names = []
    for stm in statements:
        for sig in stm._outputs:
            if not sig.hasGenericName:
                out_names.append(sig.name)
            sig.hidden = False

    if out_names:
        return min(out_names)
    else:
        return ""


def cut_off_drivers_of(dstSignal, statements):
    """
    Cut off drivers from statements
    """
    separated = []
    stm_filter = []
    for stm in statements:
        d = stm._cut_off_drivers_of(dstSignal)
        if d is not None:
            separated.append(d)

        f = d is not stm
        stm_filter.append(f)

    return list(compress(statements, stm_filter)), separated


def _statements_to_HWProcesses(_statements, tryToSolveCombLoops)\
        -> Generator[HWProcess, None, None]:
    # try to simplify statements
    proc_statements = []
    for _stm in _statements:
        stms, _ = _stm._try_reduce()
        proc_statements.extend(stms)

    outputs = UniqList()
    _inputs = UniqList()
    sensitivity = UniqList()
    for _stm in proc_statements:
        seen = set()
        _stm._discover_sensitivity(seen)
        outputs.extend(_stm._outputs)
        _inputs.extend(_stm._inputs)
        sensitivity.extend(_stm._sensitivity)

    if proc_statements:
        for o in outputs:
            assert not o.hidden, o
        seen = set()
        inputs = UniqList()
        for i in _inputs:
            inputs.extend(i._walk_public_drivers(seen))

        intersect = outputs.intersection_set(inputs)
        if intersect:
            if not tryToSolveCombLoops:
                raise HwtSyntaxError(
                    "Combinational loop on signal(s)", intersect)
            for sig in intersect:
                proc_statements, proc_stms_select = cut_off_drivers_of(
                    sig, proc_statements)

                assert proc_stms_select, (
                    "Result of stm separation is empty", sig)
                yield from _statements_to_HWProcesses(proc_stms_select, False)

            if proc_statements:
                yield from _statements_to_HWProcesses(proc_statements, False)
                return

        assert not intersect, intersect
        name = name_for_process_and_mark_outputs(proc_statements)
        yield HWProcess("assig_process_" + name,
                        proc_statements, sensitivity,
                        inputs, outputs)
    else:
        assert not outputs
        # this can happend f.e. when If does not contains any Assignment
        pass


def statements_to_HWProcesses(statements)\
        -> Generator[HWProcess, None, None]:
    """
    Pack statements into HWProcess instances,
    * for each out signal resolve it's drivers and collect them
    * split statements if there is and combinational loop
    * merge statements if it is possible
    * resolve sensitivitilists
    * wrap into HWProcess instance
    * for every IO of process generate name if signal has not any
    """
    # create copy because this set will be reduced
    statements = copy(statements)

    # process ranks = how many assignments is probably in process
    # used to minimize number of merge tries
    procRanks = {}

    processes = []
    while statements:
        stm = statements.pop()
        _statements = [stm, ]
        proc_statements = []
        for nop_initialier in inject_nop_values(_statements):
            proc_statements.append(nop_initialier)
        if proc_statements:
            proc_statements.extend(_statements)
        else:
            proc_statements = _statements

        yield from _statements_to_HWProcesses(proc_statements, True)

    yield from reduceProcesses(processes, procRanks)


def walk_assignments(stm, dst) -> Generator[Assignment, None, None]:
    if isinstance(stm, Assignment):
        if dst is stm.dst:
            yield stm
    else:
        for _stm in stm._iter_stms():
            yield from walk_assignments(_stm, dst)


class RtlNetlist():
    """
    Hierarchical container for signals

    :ivar signals: dict of all signals in context
    :ivar statements: is set of statements and nodes where datapaths starts
    :ivar subUnits: is set of all units in this context
    """

    def __init__(self, parentForDebug=None):
        self.parentForDebug = parentForDebug
        self.params = {}
        self.signals = set()
        self.statements = set()
        self.subUnits = set()
        self.synthesised = False

    def sig(self, name, dtype=BIT, clk=None, syncRst=None, defVal=None):
        """
        generate new signal in context

        :param clk: clk signal, if specified signal is synthesized
            as SyncSignal
        :param syncRst: reset
        """
        if isinstance(defVal, RtlSignal):
            assert defVal._const, \
                "Initial value of register has to be constant"
            _defVal = defVal._auto_cast(dtype)
        elif isinstance(defVal, Value):
            _defVal = defVal._auto_cast(dtype)
        elif isinstance(defVal, InterfaceBase):
            _defVal = defVal._sig
        else:
            _defVal = dtype.fromPy(defVal)

        if clk is not None:
            s = RtlSyncSignal(self, name, dtype, _defVal)
            if syncRst is not None and defVal is None:
                raise Exception(
                    "Probably forgotten default value on sync signal %s", name)
            if syncRst is not None:
                r = If(syncRst._isOn(),
                       RtlSignal.__call__(s, _defVal)
                       ).Else(
                    RtlSignal.__call__(s, s.next)
                )
            else:
                r = [RtlSignal.__call__(s, s.next)]

            If(clk._onRisingEdge(),
               r
               )
        else:
            if syncRst:
                raise SigLvlConfErr(
                    "Signal %s has reset but has no clk" % name)
            s = RtlSignal(self, name, dtype, defaultVal=_defVal)

        self.signals.add(s)

        return s

    def mergeWith(self, other):
        """
        Merge other instances into this instance

        :attention: "others" becomes invalid because all signals etc.
            will be transferred into this
        """
        assert not other.synthesised
        self.params.update(other.params)
        self.signals.update(other.signals)
        self.statements.update(other.statements)
        self.subUnits.update(other.subUnits)

        for s in other.signals:
            s.ctx = self

    def synthesize(self, name, interfaces):
        """
        Build Entity and Architecture instance out of netlist representation
        """
        ent = Entity(name)
        ent._name = name + "_inst"  # instance name

        # create generics
        for _, v in self.params.items():
            ent.generics.append(v)

        # create ports
        for s in interfaces:
            pi = portItemfromSignal(s, ent)
            pi.registerInternSig(s)
            ent.ports.append(pi)
            s.hidden = False

        removeUnconnectedSignals(self)

        # check if all signals are driver by something
        _interfaces = set(interfaces)
        for sig in self.signals:
            driver_cnt = len(sig.drivers)
            if not driver_cnt and sig not in _interfaces:
                if not sig.defaultVal._isFullVld():
                    raise NoDriverErr(
                        sig, "Signal without any driver or value in ", name)
                sig._const = True

            has_comb_driver = False
            if driver_cnt > 1:
                sig.hidden = False
                for d in sig.drivers:
                    if not isinstance(d, Operator):
                        sig.hidden = False

                    is_comb_driver = False
                    if isinstance(d, PortItem):
                        is_comb_driver = True
                    elif not d._now_is_event_dependent:
                        for a in walk_assignments(d, sig):
                            if not a.indexes and not a._is_completly_event_dependent:
                                is_comb_driver = True
                                break

                    if has_comb_driver and is_comb_driver:
                        raise MultipleDriversErr(
                            "%s: Signal %s has multiple combinational drivers" %
                            (self.getDebugScopeName(), name))

                    has_comb_driver = has_comb_driver or is_comb_driver
            else:
                if not sig.drivers or not isinstance(sig.drivers[0], Operator):
                    sig.hidden = False

        arch = Architecture(ent)
        for p in statements_to_HWProcesses(self.statements):
            arch.processes.append(p)

        # add signals, variables etc. in architecture
        for s in self.signals:
            if s.hidden and s.defaultVal.vldMask and not s.drivers:
                # constant
                s.hidden = False

            if s not in interfaces and not s.hidden:
                arch.variables.append(s)

        # instantiate subUnits in architecture
        for u in self.subUnits:
            arch.componentInstances.append(u)

        # add components in architecture
        for su in distinctBy(self.subUnits, lambda x: x.name):
            arch.components.append(su)

        self.synthesised = True

        return [ent, arch]

    def getDebugScopeName(self):
        scope = []
        p = self.parentForDebug
        while p is not None:
            scope.append(p._name)
            try:
                p = p._parent
            except AttributeError:
                break

        return ".".join(reversed(scope))
