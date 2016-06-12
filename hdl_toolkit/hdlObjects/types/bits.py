from hdl_toolkit.hdlObjects.types.hdlType import HdlType 
from hdl_toolkit.hdlObjects.specialValues import Unconstrained
from copy import copy

class Bits(HdlType):
    
    def __init__(self, widthConstr=None, forceVector=False, signed=None):
        """
        @param forceVector: use always hdl vector type 
            (for example std_logic_vector(0 downto 0) instead of std_logic)
        """
        self.forceVector = forceVector
        self.signed = signed
        if widthConstr is None:
            self.constrain = Unconstrained()
        else:
            self.constrain = widthConstr
    
    def __eq__(self, other):
        return isinstance(other, Bits) and other.bit_length() == self.bit_length()\
            and self.signed == other.signed and self.forceVector == other.forceVector
    
    def __hash__(self):
        return hash((self.name, self.signed, self.bit_length(), self.forceVector))
    
    def asVhdl(self, serializer):
        disableRange = False
        if self.signed is None:
            if self.forceVector or self.bit_length() > 1:
                name = 'STD_LOGIC_VECTOR'
            else:
                name = 'STD_LOGIC'
                disableRange = True
        elif self.signed:
            name = "SIGNED"
        else:
            name = 'UNSIGNED'     
            
        c = self.constrain
        if disableRange or c is None or isinstance(c, Unconstrained):
            constr = ""
        elif isinstance(c, (int, float)):
            constr = "%d DOWNOT 0" % c
        else:        
            constr = "(%s)" % serializer.Value(c)     
        return name + constr
    
    def applySpecificator(self, const):
        assert(isinstance(self.constrain, Unconstrained))
        s = copy(self)
        s.constrain = const
        return s
    
    def bit_length(self):
        if isinstance(self.constrain, Unconstrained):
            try:
                return self.constrain.derivedWidth
            except AttributeError:
                return None
        elif isinstance(self.constrain, (int, float)):
            return int(self.constrain)
        else:
            w = self.constrain.staticEval()
            return abs(w.val[0].val - w.val[1].val) + 1 

    def valAsVhdl(self, val, serializer):
        w = self.bit_length()
        if self.signed is None:
            if self.forceVector or w > 1:
                return serializer.BitString(val.val, w, val.vldMask)
            else:
                return serializer.BitLiteral(val.val, val.vldMask)
        elif self.signed:
            return serializer.SignedBitString(val.val, w, val.vldMask)
        else:
            return serializer.UnsignedBitString(val.val, w, val.vldMask)
    
    @classmethod
    def getConvertor(cls):
        from hdl_toolkit.hdlObjects.types.bitsConversions import convertBits
        return convertBits
    
    @classmethod
    def getValueCls(cls):
        try:
            return cls._valCls
        except AttributeError:
            from hdl_toolkit.hdlObjects.types.bitsVal import BitsVal 
            cls._valCls = BitsVal
            return cls._valCls

    def __repr__(self):
        from hdl_toolkit.synthetisator.vhdlSerializer import VhdlSerializer
        c = self.constrain
        if isinstance(c, int):
            constr = "width:%d" % c
        elif isinstance(c, Unconstrained):
            try:
                constr = "derivedWidth:%d" % (c.derivedWidth)
            except AttributeError:
                constr = ""
        else:
            constr = VhdlSerializer.asHdl(self.constrain)
        
        return "<HdlType %s, %s>" % (
            self.__class__.__name__, constr)
