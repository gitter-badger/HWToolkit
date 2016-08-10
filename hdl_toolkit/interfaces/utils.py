import math
from hdl_toolkit.hdlObjects.typeShortcuts import hInt
from hdl_toolkit.synthetisator.param import evalParam
from hdl_toolkit.interfaces.std import Clk, Rst_n, Rst
from hdl_toolkit.synthetisator.codeOps import Concat, connect


def log2ceil(x):
    if not isinstance(x, (int, float)):
        x = evalParam(x).val
    return hInt(math.ceil(math.log2(x)))

def isPow2(num):
    assert isinstance(num, int)
    return num != 0 and ((num & (num - 1)) == 0)


def binToGray(sigOrVal):
    l = sigOrVal._dtype.bit_length()
    return Concat(sigOrVal[l-1], sigOrVal[l-1:0] ^ sigOrVal[l:1])


def addClkRstn(self):
    self.clk = Clk(isExtern=True)
    self.rst_n = Rst_n(isExtern=True)

def addClkRst(self):
    self.clk = Clk(isExtern=True)
    self.rst = Rst(isExtern=True)


def _tryConnect(src, unit, intfName):
    try:
        dst = getattr(unit, intfName)
    except AttributeError:
            dst = None
    if dst is not None:
        connect(src, dst)

def propagateClk(self):
    clk = self.clk
    for u in self._units:
        _tryConnect(clk, u, 'clk')
    
def propagateClkRstn(self):
    clk = self.clk
    rst_n = self.rst_n
    
    for u in self._units:
        _tryConnect(clk, u, 'clk')
        _tryConnect(rst_n, u, 'rst_n')
        _tryConnect(~rst_n, u, 'rst')
        
def propagateClkRst(self):
    clk = self.clk
    rst = self.rst
    
    for u in self._units:
        _tryConnect(clk, u, 'clk')
        _tryConnect(~rst, u, 'rst_n')
        _tryConnect(rst, u, 'rst')