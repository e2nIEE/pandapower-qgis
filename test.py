import pandapower as pp
import pandapower.networks as nw


net = nw.mv_oberrhein()

pp.runpp(net, algorithm='nr', v_debug=True)

kwargs = {
    'algorithm': 'nr',
    'max_iteration': 300,
    'v_debug': True
}

#pp.runpp(net, **kwargs)

pp.to_json(net, r"C:\Users\slee\Documents\pp_old\test_runpp.json")