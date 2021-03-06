from hdl_toolkit.hdlObjects.operator import Operator
from hdl_toolkit.hdlObjects.operatorDefs import AllOps
from hdl_toolkit.hdlObjects.types.defs import BOOL
from hdl_toolkit.hdlObjects.types.eventCapableVal import EventCapableVal
from hdl_toolkit.hdlObjects.types.typeCast import toHVal
from hdl_toolkit.hdlObjects.value import Value, areValues
from hdl_toolkit.synthesizer.rtlLevel.signalUtils.exceptions import MultipleDriversExc
from hdl_toolkit.hdlObjects.types.bitVal_bitOpsVldMask import vldMaskForOr, \
    vldMaskForAnd
from operator import eq, ne

def boolLogOp__val(self, other, op, getVldFn):
    v = bool(op._evalFn(bool(self.val), (other.val)))
    return BooleanVal(v, BOOL,
            getVldFn(self, other),
            max(self.updateTime, other.updateTime))

def boolLogOp(self, other, op, getVldFn):
    other = toHVal(other)

    if areValues(self, other):
        return boolLogOp__val(self, other, op, getVldFn)
    else:
        return Operator.withRes(op, [self, other._convert(BOOL)], BOOL)

def boolCmpOp__val(self, other, op, evalFn):
    v = evalFn(bool(self.val), bool(other.val)) and (self.vldMask == other.vldMask == 1)
    return BooleanVal(v, BOOL,
            self.vldMask & other.vldMask,
            max(self.updateTime, other.updateTime))
    
def boolCmpOp(self, other, op, evalFn=None):
    other = toHVal(other)
    if evalFn is None:
        evalFn = op._evalFn
    
    if areValues(self, other):
        return boolCmpOp__val(self, other, op, evalFn)
    else:
        return Operator.withRes(op, [self, other._convert(BOOL)], BOOL)

class BooleanVal(EventCapableVal):
    
    @classmethod
    def fromPy(cls, val, typeObj):
        """
        @param val: value of python type bool or None
        @param typeObj: instance of HdlType
        """
        vld = int(val is not None)
        if not vld:
            val = False
        else:
            val = bool(val)
        return cls(val, typeObj, vld)

    def _eq__val(self, other):
        return boolCmpOp__val(self, other, AllOps.EQ, eq)
    def _eq(self, other):
        return boolCmpOp(self, other, AllOps.EQ, evalFn=eq)

    def _ne__val(self, other):
        return boolCmpOp__val(self, other, AllOps.NEQ, ne)
    def __ne__(self, other):
        return boolCmpOp(self, other, AllOps.NEQ)

    def _invert__val(self):
        v = self.clone()
        v.val = not v.val
        return v
    def __invert__(self):
        if isinstance(self, Value):
            return self._invert__val()
        else:
            try:
                # double negation
                d = self.singleDriver()
                if isinstance(d, Operator) and d.operator == AllOps.NOT:
                    return d.ops[0]
            except MultipleDriversExc:
                pass
            return Operator.withRes(AllOps.NOT, [self], BOOL)

    def _ternary__val(self, ifTrue, ifFalse):
        if self.val:
            if not self.vldMask:
                ifTrue.vldMask = 0
            return ifTrue
        else:
            if not self.vldMask:
                ifFalse.vldMask = 0
            return ifFalse
    def _ternary(self, ifTrue, ifFalse):
        ifTrue = toHVal(ifTrue)
        ifFalse = toHVal(ifFalse)
        
        if isinstance(self, Value):
            return self._ternary__val(ifTrue, ifFalse)
        else:
            return Operator.withRes(AllOps.TERNARY, [self, ifTrue, ifFalse], ifTrue._dtype)

    # logic
    def _and__val(self, other):
        return boolLogOp__val(self, other, AllOps.AND_LOG, vldMaskForAnd)
    def __and__(self, other):
        return boolLogOp(self, other, AllOps.AND_LOG, vldMaskForAnd)

    def _or__val(self, other):
        return boolLogOp__val(self, other, AllOps.OR_LOG, vldMaskForOr)
    def __or__(self, other):
        return boolLogOp(self, other, AllOps.OR_LOG, vldMaskForOr)


    # for evaluating only, not convertible to hdl
    def __bool__(self):
        assert isinstance(self, Value)
        return bool(self.val and self.vldMask)
    
