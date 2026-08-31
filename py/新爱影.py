import re
import sys
import json
import time
import base64
import threading

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def getName(self): return ""
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def destroy(self): pass
        def localProxy(self, params): return None

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry
    requests.packages.urllib3.disable_warnings()
except Exception:
    requests = None
P_TYPES  = "/api/vod/types"
P_HOME   = "/api/home/1"
P_FILTER = "/api/vod/filter?type="
P_DETAIL = "/api/vod/"
P_SEARCH = "/api/vod?wd="
P_PARSE  = "/api/vod/parse"

DEFAULT_BASE = "http://222.211.75.252:23433"
DEFAULT_PIC  = "http://222.211.75.252:23433"

# 排序关键词（按优先级从高到低排列，匹配到即赋予高优先级）
SORT_KEYWORDS = ["4K", "蓝光", "高清", "极速", "流畅", "秒播"]

# 屏蔽关键词（线路名称中包含任意一个即被过滤掉）
BLACK_KEYWORDS = ["失效", "测试", "备用", "废弃"]

class PbNode:
    __slots__ = ("a", "b", "c")
    def __init__(self, a=0, b=0, c=None):
        self.a = a; self.b = b; self.c = c

def _rv(buf, pos):
    val = 0; shift = 0
    while pos < len(buf):
        b = buf[pos]; pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80): return val, pos
        shift += 7
    return val, pos

def pb_decode(buf):
    if not buf: return []
    nodes = []; pos = 0
    while pos < len(buf):
        try: tag, pos = _rv(buf, pos)
        except: break
        wire = tag & 0x7; field = tag >> 3
        n = PbNode(a=field)
        if wire == 0:
            v, pos = _rv(buf, pos); n.b = v
        elif wire == 1:
            n.c = bytes(buf[pos:pos+8]); pos += 8
        elif wire == 2:
            ln, pos = _rv(buf, pos)
            n.c = bytes(buf[pos:pos+ln]); pos += ln
        elif wire == 5:
            n.c = bytes(buf[pos:pos+4]); pos += 4
        else: break
        nodes.append(n)
    return nodes

def fn(nodes, field):
    for n in nodes:
        if n.a == field: return n
    return PbNode()

def an(nodes, field):
    return [n for n in nodes if n.a == field]

def ss(c):
    if c is None: return ""
    return c.decode("utf-8", "replace") if isinstance(c, bytes) else str(c)

HTTP_RE = re.compile(r'(?i)https?://[^\x00-\x1F"\'<>\\]+')

def join_url(base, pic):
    if not pic: return ""
    if pic.startswith("http://") or pic.startswith("https://"): return pic
    if pic.startswith("//"): return "https:" + pic
    if base and not base.endswith("/"): base = base + "/"
    return (base or "") + pic

class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.base = DEFAULT_BASE
        self.pic  = DEFAULT_PIC
        self._http = None
        self._init_session()

    def _init_session(self):
        if requests is None: return
        s = requests.Session()
        if HTTPAdapter and Retry:
            r = Retry(total=2, backoff_factor=0.3,
                      status_forcelist=[500, 502, 503, 504])
            ad = HTTPAdapter(max_retries=r, pool_connections=4, pool_maxsize=8)
            s.mount("http://", ad); s.mount("https://", ad)
        self._http = s
    def getName(self): return "爱影视"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        if not url: return False
        u = url.lower()
        return ".m3u8" in u or ".mp4" in u or ".flv" in u

    def manualVideoCheck(self): return False

    def destroy(self):
        try:
            if self._http: self._http.close()
        except: pass
    def _request(self, path, payload=None, method="GET"):
        url = self.base + path
        if self._http is not None:
            if method == "POST":
                r = self._http.post(url, json=payload or {}, timeout=15, verify=False,
                    headers={"User-Agent": "Mozilla/5.0"})
            else:
                r = self._http.get(url, timeout=15, verify=False,
                    headers={"User-Agent": "Mozilla/5.0"})
            raw = r.content
        else:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            if method == "POST":
                req.data = json.dumps(payload or {}).encode("utf-8")
                req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
        top = pb_decode(raw)
        f3 = fn(top, 3)
        if f3.c:
            return f3.c
        return raw

    # ---- 映射 ----
    def _map_item(self, nodes):
        vid = str(fn(nodes, 1).b or "")
        if not vid: return None
        return {
            "vod_id":       vid,
            "vod_name":     ss(fn(nodes, 2).c),
            "vod_pic":      join_url(self.pic, ss(fn(nodes, 3).c)),
            "vod_actor":    ss(fn(nodes, 4).c),
            "vod_director": ss(fn(nodes, 5).c),
            "vod_score":    ss(fn(nodes, 6).c),
            "vod_remarks":  ss(fn(nodes, 7).c),
        }

    def _map_detail(self, nodes, vod_id):
        item = {
            "vod_id":       str(fn(nodes, 1).b or vod_id),
            "vod_name":     ss(fn(nodes, 2).c),
            "vod_pic":      join_url(self.pic, ss(fn(nodes, 3).c)),
            "vod_actor":    ss(fn(nodes, 4).c),
            "vod_director": ss(fn(nodes, 5).c),
            "vod_content":  ss(fn(nodes, 8).c),
            "vod_year":     ss(fn(nodes, 9).c),
            "vod_area":     ss(fn(nodes, 10).c),
            "vod_remarks":  ss(fn(nodes, 11).c),
        }
        if not item["vod_year"]:
            item["vod_year"] = ss(fn(nodes, 12).c)
        cat_list = []
        for cn in an(nodes, 13):
            c = ss(cn.c)
            if c: cat_list.append(c)
        if cat_list:
            item["vod_genre"] = "/".join(cat_list)
        elif not item.get("vod_genre"):
            item["vod_genre"] = ss(fn(nodes, 14).c)

        lines = [] 
        for line in an(nodes, 17):
            ln = pb_decode(line.c)
            if ss(fn(ln, 7).c) == "login": continue

            raw_lname = ss(fn(ln, 2).c) or ss(fn(ln, 3).c)
            if not raw_lname:
                raw_lname = "线路" + str(len(lines) + 1)

            name2 = ss(fn(ln, 2).c)
            name3 = ss(fn(ln, 3).c)
            name1 = ss(fn(ln, 1).c)
            name4 = ss(fn(ln, 4).c)

            def has_chinese(s):
                return any('\u4e00' <= ch <= '\u9fff' for ch in s)

            if name2 and name3:
                if has_chinese(name2) and not has_chinese(name3):
                    ch_name, tag = name2, name3
                elif has_chinese(name3) and not has_chinese(name2):
                    ch_name, tag = name3, name2
                else:
                    ch_name, tag = name2, name3
                if '(' in tag or '（' in tag:
                    display_name = ch_name + tag
                else:
                    display_name = ch_name + "(" + tag + ")"
            elif name2:
                display_name = name2
            elif name3:
                display_name = name3
            elif name1:
                display_name = name1
            elif name4:
                display_name = name4
            else:
                display_name = "线路" + str(len(lines) + 1)

            eps_parts = []
            for ep in an(ln, 12):
                epn = pb_decode(ep.c)
                ep_name = ss(fn(epn, 1).c) or ("第" + str(len(eps_parts)+1) + "集")
                ep_id = ss(fn(epn, 2).c)
                if not ep_id: continue
                play_obj = {
                    "url":         ep_id,
                    "from":        raw_lname,   
                    "parseIndex":  0,
                    "vod_id":      str(fn(nodes, 1).b or vod_id),
                    "episode_key": ep_id,
                }
                b = json.dumps(play_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                eps_parts.append(ep_name + "$z1." + base64.b64encode(b).decode("ascii").rstrip("="))
            if not eps_parts:
                continue
            lines.append({
                'display': display_name,
                'raw': raw_lname,
                'eps': "#".join(eps_parts)
            })

        filtered_lines = []
        for line in lines:
            blocked = False
            name_check = line['display'] + line['raw']
            for kw in BLACK_KEYWORDS:
                if kw in name_check:
                    blocked = True
                    break
            if not blocked:
                filtered_lines.append(line)

        def sort_key(line):
       
            name = line['display'] + line['raw']
            for idx, kw in enumerate(SORT_KEYWORDS):
                if kw in name:
                    return (idx, 0)  
            return (len(SORT_KEYWORDS), lines.index(line))

        filtered_lines.sort(key=sort_key)

        from_list = [line['display'] for line in filtered_lines]
        url_list = [line['eps'] for line in filtered_lines]

        item["vod_play_from"] = "$$$".join(from_list)
        item["vod_play_url"]  = "$$$".join(url_list)
        return item

    # ---- 首页 ----
    def homeContent(self, filter):
        out_classes, out_list = [], []
        try:
            raw = self._request(P_TYPES)
            if raw:
                top = pb_decode(raw)
                for n in an(top, 1):
                    sub = pb_decode(n.c)
                    tid = str(fn(sub, 1).b or "")
                    tname = ss(fn(sub, 2).c)
                    if tid and tname:
                        out_classes.append({"type_id": tid, "type_name": tname})
        except Exception as e:
            sys.stderr.write("[whale] homeContent types: %s\n" % e)

        try:
            raw = self._request(P_HOME)
            if raw:
                top = pb_decode(raw)
                seen = set()
                for banner in an(top, 4):
                    bn = pb_decode(banner.c)
                    for n in an(bn, 11):
                        sub = pb_decode(n.c)
                        item = self._map_item(sub)
                        if item and item["vod_id"] not in seen:
                            seen.add(item["vod_id"])
                            out_list.append(item)
        except Exception as e:
            sys.stderr.write("[whale] homeContent banner: %s\n" % e)
        return {"class": out_classes, "list": out_list}

    def homeVideoContent(self):
        return {"list": self.homeContent(False).get("list", [])}

    # ---- 分类 ----
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = str(pg or 1)
            path = P_FILTER + str(tid) + "&page=" + pg + "&pageSize=21"
            raw = self._request(path)
            if not raw:
                return {"list": [], "page": int(pg), "pagecount": 1, "limit": 21, "total": 0}
            top = pb_decode(raw)
            page = int(pg); pagecount = 1; total = 0; limit = 21
            meta = fn(top, 1)
            if meta.c:
                inner = pb_decode(meta.c)
                page  = fn(inner, 1).b or page
                limit = fn(inner, 2).b or 21
                total = fn(inner, 3).b or 0
                pagecount = max(1, -(-int(total) // int(limit))) if total else 1
            out_list = []
            for arr_node in an(top, 2):
                item = self._map_item(pb_decode(arr_node.c))
                if item: out_list.append(item)
            return {"list": out_list, "page": int(page), "pagecount": int(pagecount),
                    "limit": int(limit), "total": int(total)}
        except Exception as e:
            sys.stderr.write("[whale] categoryContent: %s\n" % e)
            return {"list": [], "page": 1, "pagecount": 1, "limit": 21, "total": 0}

    # ---- 详情 ----
    def detailContent(self, ids):
        try:
            if not ids: return {"list": []}
            vid = ids[0]
            raw = self._request(P_DETAIL + str(vid))
            if not raw: return {"list": []}
            top = pb_decode(raw)
            item = self._map_detail(top, vid)
            return {"list": [item] if item else []}
        except Exception as e:
            sys.stderr.write("[whale] detailContent: %s\n" % e)
            return {"list": []}

    # ---- 播放 ----
    def playerContent(self, flag, id, vipFlags=None):
        try:
            if not id: return {"parse": 0, "url": "", "header": {}}
            url_real = id; obj = {}
            if "$z1." in id:
                parts = id.split("$z1.", 1)
                b64 = parts[1]
                pad = (-len(b64)) % 4
                try:
                    obj = json.loads(base64.b64decode(b64 + ("=" * pad)))
                    url_real = obj.get("url") or url_real
                except: pass
            elif id.startswith("z1."):
                b64 = id[3:]
                pad = (-len(b64)) % 4
                try:
                    obj = json.loads(base64.b64decode(b64 + ("=" * pad)))
                    url_real = obj.get("url") or url_real
                except: pass

            # 直链直接返回
            if re.match(r'(?i)^https?://.*\.(m3u8|mp4|flv)(?:$|\?)', url_real):
                return {"parse": 0, "url": url_real, "header": {}}

            # POST /api/vod/parse 获取真实地址
            try: vid_int = int(obj.get("vod_id", 0) or 0)
            except: vid_int = 0
            payload = {
                "from":        obj.get("from")        or flag or "",
                "url":         url_real,
                "parseIndex":  obj.get("parseIndex")  or 0,
                "vod_id":      vid_int,
                "episode_key": obj.get("episode_key") or url_real,
            }
            raw = self._request(P_PARSE, payload=payload, method="POST")
            if not raw:
                return {"parse": 1, "url": url_real, "header": {}}
            top = pb_decode(raw)
            url_field = ss(fn(top, 2).c).strip()
            if not url_field or not re.match(r'(?i)^https?://', url_field):
                m = HTTP_RE.search(raw.decode("utf-8", "replace"))
                url_field = m.group(0) if m else ""
            if url_field:
                return {"parse": 0, "url": url_field, "header": {}}
            return {"parse": 1, "url": url_real, "header": {}}
        except Exception as e:
            sys.stderr.write("[whale] playerContent: %s\n" % e)
            return {"parse": 1, "url": id or "", "header": {}}

    # ---- 搜索 ----
    def searchContent(self, key, quick, pg="1"):
        try:
            from urllib.parse import quote as _q
            path = P_SEARCH + _q(key or "", safe="") + "&page=1&pageSize=21"
            raw = self._request(path)
            if not raw: return {"list": [], "page": 1, "pagecount": 1}
            top = pb_decode(raw)
            out_list = []
            for arr_node in an(top, 2):
                item = self._map_item(pb_decode(arr_node.c))
                if item: out_list.append(item)
            return {"list": out_list, "page": 1, "pagecount": 1}
        except Exception as e:
            sys.stderr.write("[whale] searchContent: %s\n" % e)
            return {"list": [], "page": 1}