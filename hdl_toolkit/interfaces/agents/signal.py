from hdl_toolkit.hdlObjects.specialValues import Time
from hdl_toolkit.simulator.agentBase import AgentBase
from hdl_toolkit.simulator.shortcuts import onRisingEdge


class SignalAgent(AgentBase):
    """
    Agent for signal interface, it can use clock and reset interface for synchronization
    or can be synchronized by delay
    
    @attention: clock synchronization has higher priority 
    """
    def __init__(self, intf, clk=None, rstn=None, delay=10 * Time.ns):
        self.delay = delay
        self.initDelay = 0
        self.clk = clk
        self.rstn = rstn
        self.intf = intf
        self.data = []
        
        self.initPending = True 
        
        if clk is not None:
            self.monitor = onRisingEdge(self.clk, self.monitor)
            self.driver = onRisingEdge(self.clk, self.driver)
            
    
    def doRead(self, s):
        return s.read(self.intf)
        
    def doWrite(self, s, data):
        s.w(data, self.intf)    
        
    def driver(self, s):
        if self.initPending and self.initDelay:
            yield s.wait(self.initDelay)
            self.initPending = False
        
        
        if self.clk is None:
            # if clock is specified this function is periodicaly called every
            # clk tick
            while True:
                if self.data:
                    self.doWrite(s, self.data.pop(0))
                yield s.wait(self.delay)
        else:
            # if clock is specified this function is periodicaly called every
            # clk tick
            if self.data:
                self.doWrite(s, self.data.pop(0))
    
    
    def monitor(self, s):
        if self.clk is None:
            if self.initPending and self.initDelay:
                yield s.wait(self.initDelay)
                self.initPending = False
            # if there is no clk, we have to manage periodic call by our selfs
            while True:
                yield s.updateComplete
                d = self.doRead(s)
                self.data.append(d)
                yield s.wait(self.delay)
        else:
            # if clock is specified this function is periodicaly called every
            # clk tick
            yield s.updateComplete
            d = self.doRead(s)
            self.data.append(d)

