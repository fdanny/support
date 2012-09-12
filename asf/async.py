import copy
import functools
from asf_context import ASFError

try:
    from ..lib import gevent
except ImportError:
    pass #other imports are gevent-relative, so if gevent on system will work ok
import gevent.pool
import gevent.socket
import gevent.threadpool

CPU_THREAD = None # Lazily initialize -- mhashemi 6/11/2012
CPU_THREAD_ENABLED = True

def cpu_bound(f):
    '''
    decorator to mark a function as cpu-heavy; will be executed in a separate
    thread to avoid blocking any socket communication
    '''
    @functools.wraps(f)
    def g(*a, **kw):
        if not CPU_THREAD_ENABLED:
            return f(*a, **kw)
        global CPU_THREAD
        if CPU_THREAD is None:
            CPU_THREAD = gevent.threadpool.ThreadPool(1)
        return CPU_THREAD.apply(f, a, kw)
    g.no_defer = f
    return g

def close_threadpool():
    global CPU_THREAD
    if CPU_THREAD:
        CPU_THREAD.join()
        CPU_THREAD.kill()
        CPU_THREAD = None
    return

def join(asf_reqs, raise_exc=True, timeout=None):
    greenlets = [gevent.Greenlet.spawn(req) for req in asf_reqs]
    try:
        gevent.joinall(greenlets, raise_error=raise_exc, timeout=timeout)
    except gevent.socket.error as e:
        raise ASFError(e)
    return [gr.value if gr.successful() else gr.exception for gr in greenlets]

#TODO: use this again
class ASFTimeoutError(ASFError):
    def __init__(self, request=None, timeout=None):
        try:
            self.ip = request.ip
            self.port = request.port
            self.service_name = request.service
            self.op_name = request.operation
        except AttributeError as ae:
            pass
        if timeout:
            self.timeout = timeout

    def __str__(self):
        ret = "ASFTimeoutError"
        try:
            ret += " encountered while to trying execute "+self.op_name \
                   +" on "+self.service_name+" ("+str(self.ip)+':'      \
                   +str(self.port)+")"
        except AttributeError:
            pass
        try:
            ret += " after "+str(self.timeout)+" seconds"
        except AttributeError:
            pass
        ret += "\n\n"+super(ASFTimeoutError, self).__str__()
        return ret

### What follows is code related to map() contributed from MoneyAdmin's asf_util
class Node(object):
    def __init__(self, ip, port, **kw):
        self.ip   = ip
        self.port = port
        
        # in case you want to add name/location/id/other metadata
        for k,v in kw.items():
            setattr(self, k, v)

# call it asf_map to avoid name collision with builtin map?
# return callable to avoid collision with kwargs?
def map_factory(op, node_list, raise_exc=True, timeout=None):
    """
    map_factory() enables easier concurrent calling across multiple servers,
    provided a node_list, which is an iterable of Node objects.
    """
    def asf_map(*a, **kw):
        return join([op_ip_port(op, node.ip, node.port).async(*a, **kw)
                        for node in node_list], raise_exc=False, timeout=timeout)
    return asf_map

def op_ip_port(op, ip, port):
    serv = copy.copy(op.service)
    serv.meta = copy.copy(serv.meta)
    serv.meta.ip = ip
    serv.meta.port = port
    op = copy.copy(op)
    op.service = serv
    return op
