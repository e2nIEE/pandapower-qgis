import pandapower as pp
import pandapower.networks as nw


# net = nw.mv_oberrhein()
#
# pp.runpp(net, algorithm='nr', v_debug=True)
#
# kwargs = {
#     'algorithm': 'nr',
#     'max_iteration': 300,
#     'v_debug': True
# }
#
# #pp.runpp(net, **kwargs)
#
# pp.to_json(net, r"C:\Users\slee\Documents\pp_old\test_runpp.json")



net = pp.from_json(r"C:\Users\slee\Documents\pp_old\mv_oberrhein_wgs - Kopie.json")

print("===== wgs version direct after loading =====")
print(f"res_bus exists?: {hasattr(net, 'res_bus') and not net.res_bus.empty}")
if hasattr(net, 'res_bus') and not net.res_bus.empty:
    print(f"va_degree before runpp: {net.res_bus['va_degree'].iloc[0]:.3f}도")

print("WGS va_degree before runpp:")
print(net.res_bus['va_degree'].head(10))


print("\n===== run runpp =====")
pp.runpp(net)
print(f"va_degree after run runpp without parameter: {net.res_bus['va_degree'].iloc[0]:.3f}도")
kwargs = {
    'algorithm': 'nr',
    'max_iteration': 300,
    'v_debug': True
}
pp.runpp(net, **kwargs)
print(f"va_degree after run runpp with parameter: {net.res_bus['va_degree'].iloc[0]:.3f}도")

print("WGS va_degree after runpp:")
print(net.res_bus['va_degree'].head(10))

print("WGS version ext_grid:")
print(net.ext_grid[['bus', 'vm_pu', 'va_degree', 'in_service']])



net2 = nw.mv_oberrhein()

print("===== status of net from library after loading =====")
print(f"res_bus exists?: {hasattr(net2, 'res_bus') and not net2.res_bus.empty}")
if hasattr(net2, 'res_bus') and not net2.res_bus.empty:
    print(f"va_degree before runpp: {net2.res_bus['va_degree'].iloc[0]:.3f}도")

print("Library version va_degree before runpp:")
print(net2.res_bus['va_degree'].head(10))


print("\n===== run runpp =====")
pp.runpp(net2)
print(f"va_degree after runpp without parameter: {net2.res_bus['va_degree'].iloc[0]:.3f}도")
kwargs = {
    'algorithm': 'nr',
    'max_iteration': 300,
    'v_debug': True
}
pp.runpp(net2, **kwargs)
print(f"va_degree after runpp with parameter: {net2.res_bus['va_degree'].iloc[0]:.3f}도")

print("Library version va_degree after runpp:")
print(net2.res_bus['va_degree'].head(10))

print("Library version ext_grid:")
print(net2.ext_grid[['bus', 'vm_pu', 'va_degree', 'in_service']])

