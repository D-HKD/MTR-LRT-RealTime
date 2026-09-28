from workers import WorkerEntrypoint, Response, fetch
from urllib.parse import urlparse, parse_qs, urlencode

# 車站列表
LR_STATIONS = [
    {"name": "輕鐵｜天水圍站", "type": "lr", "id": 1027},
    {"name": "輕鐵｜天榮站", "type": "lr", "id": 1017},
    {"name": "輕鐵｜豐年路站", "type": "lr", "id": 1044},
    {"name": "輕鐵｜元朗站", "type": "lr", "id": 1045},
]
TML_STATIONS = [
    {"name": "屯馬綫｜屯門站", "type": "tml", "code": "TUM"},
    {"name": "屯馬綫｜天水圍站", "type": "tml", "code": "TIS"},
    {"name": "屯馬綫｜朗屏站", "type": "tml", "code": "LOP"},
    {"name": "屯馬綫｜元朗站", "type": "tml", "code": "YUL"},
]
ALL_STATIONS = LR_STATIONS + TML_STATIONS

async def fetch_get_json(base_url, params=None):
    """GET + Query參數，加上UA Header"""
    if params:
        query = urlencode(params)
        url = f"{base_url}?{query}"
    else:
        url = base_url
    resp = await fetch(url, {
        "headers": {
            "User-Agent": "MTR-ETA-CloudflareWorker/1.0"
        }
    })
    return await resp.json()

async def get_lr_data(station_id):
    try:
        payload = {"station_id": station_id, "with_special": 0}
        j = await fetch_get_json("https://rt.data.gov.hk/v1/transport/mtr/lrt/getSchedule", payload)
    except Exception:
        return [], "連線失敗"
    if j.get("status") != 1:
        return [], "API返回錯誤"
    trains = []
    for plat in j["platform_list"]:
        for route in plat["route_list"]:
            trains.append({
                "plat": plat["platform_id"],
                "route": route["route_no"],
                "dest": route["dest_ch"],
                "time": route["time"],
                "length": route["train_length"],
                "direction": route["dest_ch"]
            })
    return trains, j["system_time"]

async def get_tml_data(sta_code):
    try:
        payload = {"line": "TML", "sta": sta_code, "lang": "zh"}
        j = await fetch_get_json("https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php", payload)
    except Exception:
        return [], "連線失敗"
    key = f"TML-{sta_code}"
    if key not in j.get("data", {}):
        return [], j.get("sys_time", "")
    data = j["data"][key]
    trains = []
    for direction, dir_name in [("UP", "往屯門"), ("DOWN", "往烏溪沙")]:
        for t in data.get(direction, []):
            trains.append({
                "dir": dir_name,
                "plat": t["plat"],
                "dest": t["dest"],
                "time": t["ttnt"],
                "direction": dir_name
            })
    return trains, data["sys_time"]

HTML_TPL = '''
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTR 實時到站｜自用版</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;}
body{background:#f4f5f7;color:#222;padding:16px;max-width:640px;margin:0 auto;}
.mtr-header{background:#003663;color:white;padding:16px;border-radius:12px 12px 0 0;display:flex;align-items:center;gap:12px;}
.mtr-logo{height:36px;}
h1{font-size:22px;font-weight:600;}
.select-container{background:#fff;padding:16px;border-radius:0 0 12px 12px;margin-bottom:16px;box-shadow:0 2px 8px #00000012;display:grid;gap:12px;}
select{width:100%;padding:14px;font-size:18px;border:1px solid #d0d7e3;border-radius:8px;background:#fff;}
.train-card{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 2px 8px #00000010;}
.line-tag{display:inline-block;padding:4px 10px;border-radius:6px;color:white;font-weight:bold;font-size:14px;margin-bottom:8px;}
.tag-lr{background:#ff7f24;}
.tag-tml{background:#b6232a;}
.update-time{color:#666;font-size:14px;margin-bottom:12px;}
.train-item{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid #eee;font-size:17px;}
.train-item:last-child{border-bottom:none;}
.urgent{color:#d12229;font-weight:bold;}
.info-left{flex:1;}
.info-right{font-weight:bold;text-align:right;}
.lr-circle{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:999px;background:#ff7f24;color:white;font-weight:bold;margin-right:6px;font-size:14px;}
.soon-badge{display:inline-block;background:#d12229;color:#fff;padding:2px 6px;border-radius:4px;font-size:12px;margin-left:6px;}
</style>
<meta http-equiv="refresh" content="10">
</head>
<body>
    <div class="mtr-header">
        <img class="mtr-logo" src="https://upload.wikimedia.org/wikipedia/zh/thumb/8/87/MTR_Corporation_logo.svg/1200px-MTR_Corporation_logo.svg.png" alt="MTR Logo">
        <h1>實時到站資訊</h1>
    </div>
    <div class="select-container">
        <form method="GET">
            <select name="station" onchange="this.form.submit()">
                {{station_options}}
            </select>
            <select name="filter_dir" onchange="this.form.submit()">
                <option value="all" {{sel_all}}>全部方向</option>
                <option value="往屯門" {{sel_tuenmun}}>往屯門</option>
                <option value="往烏溪沙" {{sel_wukisha}}>往烏溪沙</option>
                <option value="往元朗" {{sel_yuenlong}}>往元朗</option>
                <option value="往天水圍" {{sel_tinshuiwai}}>往天水圍</option>
            </select>
        </form>
    </div>
{{train_content}}
</body>
</html>
'''

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        parsed_url = urlparse(request.url)
        params = parse_qs(parsed_url.query)
        sel_idx = int(params.get("station", ["0"])[0])
        filter_dir = params.get("filter_dir", ["all"])[0]
        station = ALL_STATIONS[sel_idx]
        train_list = []
        sys_time = ""
        station_type = station["type"]

        if station["type"] == "lr":
            trains, sys_time = await get_lr_data(station["id"])
            for t in trains:
                try:
                    mins = int(t["time"])
                except:
                    mins = 99
                train_list.append({
                    "type": "lr",
                    "plat": t["plat"],
                    "route": t["route"],
                    "dest": t["dest"],
                    "time": t["time"],
                    "min": mins,
                    "length": t["length"],
                    "direction": t["direction"]
                })
        else:
            trains, sys_time = await get_tml_data(station["code"])
            for t in trains:
                try:
                    mins = int(t["time"])
                except:
                    mins = 99
                train_list.append({
                    "type": "tml",
                    "dir": t["dir"],
                    "plat": t["plat"],
                    "dest": t["dest"],
                    "time": t["time"],
                    "min": mins,
                    "direction": t["direction"]
                })

        # 組合車站下拉選項
        station_options = ""
        for idx, s in enumerate(ALL_STATIONS):
            selected = "selected" if int(sel_idx) == idx else ""
            station_options += f'<option value="{idx}" {selected}>{s["name"]}</option>'

        # 方向下拉 selected
        sel_all = "selected" if filter_dir == "all" else ""
        sel_tuenmun = "selected" if filter_dir == "往屯門" else ""
        sel_wukisha = "selected" if filter_dir == "往烏溪沙" else ""
        sel_yuenlong = "selected" if filter_dir == "往元朗" else ""
        sel_tinshuiwai = "selected" if filter_dir == "往天水圍" else ""

        # 組合列車HTML
        train_content = ""
        if train_list:
            train_content += f'<div class="train-card"><span class="line-tag {"tag-lr" if station_type=="lr" else "tag-tml"}">{station["name"]}</span><div class="update-time">更新時間：{sys_time}</div>'
            for t in train_list:
                if not (filter_dir == "all" or filter_dir in t["direction"]):
                    continue
                urgent = "urgent" if t["min"] <= 5 else ""
                soon_badge = '<span class="soon-badge">即將到站</span>' if t["min"] <=5 else ""
                if t["type"] == "lr":
                    left = f'<span class="lr-circle">{t["route"]}</span>月台{t["plat"]}｜往{t["dest"]}（{t["length"]}卡）{soon_badge}'
                else:
                    left = f'屯馬綫｜{t["dir"]}｜月台{t["plat"]}｜{t["dest"]}{soon_badge}'
                right = f'{t["time"]} 分鐘'
                train_content += f'<div class="train-item {urgent}"><div class="info-left">{left}</div><div class="info-right">{right}</div></div>'
            train_content += "</div>"
        else:
            train_content = '<div class="train-card"><div class="update-time">暫時未能取得列車資料，請稍後再試</div></div>'

        html_out = HTML_TPL
        html_out = html_out.replace("{{station_options}}", station_options)
        html_out = html_out.replace("{{sel_all}}", sel_all)
        html_out = html_out.replace("{{sel_tuenmun}}", sel_tuenmun)
        html_out = html_out.replace("{{sel_wukisha}}", sel_wukisha)
        html_out = html_out.replace("{{sel_yuenlong}}", sel_yuenlong)
        html_out = html_out.replace("{{sel_tinshuiwai}}", sel_tinshuiwai)
        html_out = html_out.replace("{{train_content}}", train_content)

        return Response(html_out, headers={"content-type": "text/html;charset=utf-8"})
