
from hdl_toolkit.formater import formatVhdl
from hdl_toolkit.synthetisator.rtlLevel.context import Context
from hdl_toolkit.hdlObjects.typeShortcuts import vecT, vec, hBit
from hdl_toolkit.synthetisator.rtlLevel.signal.utils import connect
from hdl_toolkit.synthetisator.rtlLevel.codeOp import If

w = connect


def LeadingZero():
    t = vecT(8)
    c = Context("LeadingZero")
    
    s_in = c.sig("s_in", t)
    index = c.sig("s_indexOfFirstZero", t)
    
    leadingZeroTop = None  # index is index of first empty record or last one
    for i in reversed(range(8)):
        connections = w(vec(i, 8), index)
        if leadingZeroTop is None:
            leadingZeroTop = connections 
        else:
            leadingZeroTop = If(s_in[i]._eq(hBit(False)),
               connections
               ,
               leadingZeroTop
            )    
    
    interf = [s_in, index]
    
    return c, interf

if __name__ == "__main__":
    c, interf = LeadingZero()
    
    for o in c.synthetize(interf):
            print(formatVhdl(str(o)))
