from hdl_toolkit.hdlObjects.specialValues import Time
from random import Random

def valueHasChanged(valA, valB):
    return valA.val is not valB.val or valA.vldMask != valB.vldMask

def agent_randomize(agent, timeQuantum=5 * 10 * Time.ns, seed=317):
    random = Random(seed)
    def randomEnProc(simulator):
        while True:
            agent.enable = random.random() < 0.5
            delay = int(random.random() * timeQuantum)  
            yield simulator.wait(delay)
    return randomEnProc