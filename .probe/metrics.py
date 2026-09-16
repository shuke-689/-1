import ctypes, ctypes.wintypes as wt
u=ctypes.windll.user32
u.SetProcessDPIAware()
print("Screen: %dx%d  virtual: %dx%d" % (u.GetSystemMetrics(0), u.GetSystemMetrics(1), u.GetSystemMetrics(78), u.GetSystemMetrics(79)))
print("Monitors: %d" % u.GetSystemMetrics(80))
import ctypes.wintypes
class R(ctypes.Structure): _fields_=[("l",ctypes.c_long),("t",ctypes.c_long),("r",ctypes.c_long),("b",ctypes.c_long)]
mons=[]
def cb(h,dc,rc,data):
    r=ctypes.cast(rc,ctypes.POINTER(R)).contents
    mons.append((r.l,r.t,r.r,r.b))
    return 1
CB=ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(R), ctypes.c_double)
u.EnumDisplayMonitors(0,0,CB(cb),0)
for i,m in enumerate(mons): print("  monitor%d: %s  size=%dx%d" % (i,m,m[2]-m[0],m[3]-m[1]))
