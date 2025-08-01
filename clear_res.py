import pandapower as pp
import pandapower.networks as nw

net = nw.mv_oberrhein()

# clear all 'res_' table
try:
    pp.clear_result_tables(net)
    print("✅ Results are successfully reset.")
    # save file as new file
    pp.to_json(net, r"C:\Users\slee\Documents\pp_old\mv_oberrhein_wgs_clear_res.json")
    print(r"File path: C:\Users\slee\Documents\pp_old\mv_oberrhein_wgs_clear_res.json")
except AttributeError:
    print("❌ Problem with clear_result_tables methode.")

# Check res tables
if net is None:
    print("Network is None.")

res_keys = [key for key in net.keys() if key.startswith('res_')]

if res_keys:
    # Check size of each tables
    for key in res_keys:
        try:
            size = len(net[key])
            print(f"  - {key}: {size} rows")
        except:
            print(f"  - {key}: Size check is not available.")
else:
    print(f"No result tables are detected.")