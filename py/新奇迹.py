#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import base64
import random
import time
import re
import urllib.request
import urllib.parse
import ssl
import os
import hashlib
try:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5 as _PKCS1
    from Crypto.Cipher import AES as _PAES
except ImportError:
    raise ImportError("需要 pycryptodome 库")
_UA = "okhttp/3.10.0"
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE
LOG_PATH = "/storage/emulated/0/TVBOX/pg/debug.txt"
def _log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass
def _http(url, data=None, headers=None, timeout=20):
    hdrs = {"User-Agent": _UA, "app-platform": "android"}
    if headers:
        hdrs.update(headers)
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    else:
        req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        return r.read().decode("utf-8", "replace")
def _hex(n):
    return "".join(random.choice("0123456789abcdef") for _ in range(n))
def _cbc_dec(key, iv, data):
    out = _PAES.new(key, _PAES.MODE_CBC, iv).decrypt(data)
    pad = out[-1]
    return out[:-pad] if 1 <= pad <= 16 else out
def _cbc_enc(key, iv, data):
    pad = 16 - len(data) % 16
    return _PAES.new(key, _PAES.MODE_CBC, iv).encrypt(data + bytes([pad]) * pad)
class _Client:
    def __init__(self, cfg):
        self.cfg = cfg
        self._session = None
        self._sid = None
        self._k = None
        self._iv = None
        self._ns = None
        self.expire = 0
        self._host = None
    def _ensure_session(self):
        if self._session is not None and time.time() < self.expire:
            return
        h = self.cfg.get("host", "").strip()
        if not h:
            raise Exception("ext 中必须提供 host")
        if h.endswith(('.txt', '.json')):
            try:
                _log(f"动态获取 host: {h}")
                content = _http(h, timeout=6).strip()
                if content.startswith(('http://', 'https://')):
                    h = content
                    _log(f"纯文本动态 host: {h}")
                else:
                    data = json.loads(content)
                    dom = data.get("domain") or data.get("host") or ""
                    if dom.startswith(('http://', 'https://')):
                        h = dom
                        _log(f"JSON动态 host: {h}")
                    else:
                        raise Exception("无法解析动态 host")
            except Exception as e:
                raise Exception(f"动态获取失败: {e}")
        else:
            _log(f"静态 host: {h}")
        self._host = h
        ns = self.cfg.get("nsKey", "").strip()
        if not ns:
            raise Exception("ext 中缺少 key")
        sk = _hex(128)
        pub_resp = _http(h + "/api.php/qijiappapi.index/getPublicKey")
        pub = json.loads(pub_resp)
        pk = pub["data"]["public_key"].replace("\\/", "/")
        k = RSA.import_key(pk)
        enc = base64.b64encode(_PKCS1.new(k).encrypt(sk.encode())).decode()
        r = _http(h + "/api.php/qijiappapi.index/handshake", {
            "encrypted_key": enc,
            "device_id": self.cfg.get("device_id", "a1b2c3d4e5f67890"),
            "timestamp": int(time.time())
        })
        j = json.loads(r)
        if j.get("code") != 1:
            raise Exception("handshake fail: " + str(j.get("msg")))
        self._sid = j["data"]["session_id"]
        self._k = bytes.fromhex(sk[:32])
        self._iv = bytes.fromhex(sk[32:64])
        self._ns = ns.encode()
        self.expire = time.time() + 12 * 3600
        self._session = True
        _log("会话建立成功")
    def call(self, ep, params=None):
        self._ensure_session()
        url = self._host + f"/api.php/qijiappapi.index/{ep}"
        r = _http(url, params or {}, {"app-session-id": self._sid})
        j = json.loads(r)
        if j.get("code") != 1:
            _log(f"{ep} 返回错误: {j.get('msg')}")
            return None
        d = j.get("data")
        if isinstance(d, str) and len(d) > 8:
            try:
                decrypted = _cbc_dec(self._k, self._iv, base64.b64decode(d))
                decoded = decrypted.decode("utf-8", "replace")
                return json.loads(decoded)
            except Exception as e:
                _log(f"{ep} 解密失败: {e}")
                return None
        return d
    def ns_enc(self, plain):
        return base64.b64encode(_cbc_enc(self._ns, self._ns, plain.encode())).decode()
    def _direct_parse(self, parse_api, ep_url):
        full = parse_api + ep_url if parse_api else ep_url
        try:
            req = urllib.request.Request(full, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=15, context=_SSL) as r:
                body = r.read().decode("utf-8", "replace")
            return json.loads(body)
        except Exception as e:
            _log(f"直调解析失败: {e}")
            return {}
    def vod_parse(self, parse_key, ptype, ep_url):
        r = self.call("vodParse", {
            "url": self.ns_enc(ep_url),
            "parse_api": parse_key,
            "token": "",
            "player_parse_type": ptype,
            "base_api": parse_key + ep_url
        })
        if isinstance(r, dict):
            inner = r.get("json")
            if isinstance(inner, str):
                try:
                    return json.loads(inner)
                except Exception:
                    return r
        if not r and parse_key:
            return self._direct_parse(parse_key, ep_url)
        return r or {}
class Spider:
    def __init__(self):
        _log("Spider 初始化")
        self.ext_config = {}
        self._cli = None
        self._init_cache = None
        self._detail_cache = {}
        self._play_cache = {}
        self._types = {}
        self._filters = {}
        self._search_cache = {}
        self._home_list = []
        self.cate_block = []
        self.order_keywords = []
        self.block_keywords = []
        self.meili_key = None
        self.meili_index = "mac_vod_myy"
        self.meili_host = None
        self._meili_failed = False
    @staticmethod
    def getDependence():
        return []
    def init(self, ext=""):
        _log(f"init 被调用, ext={ext}")
        if isinstance(ext, dict):
            self.ext_config = ext.copy()
        else:
            try:
                s = (ext or "").strip()
                if s:
                    if s.startswith("http"):
                        j = json.loads(_http(s, timeout=8))
                        self.ext_config = j
                    else:
                        j = json.loads(s)
                        self.ext_config = j
            except Exception as e:
                _log(f"init 解析 ext 失败: {e}")
                self.ext_config = {}
        if "key" not in self.ext_config or not self.ext_config["key"]:
            _log("错误：ext 中缺少 key")
            return
        if "host" not in self.ext_config or not self.ext_config["host"]:
            _log("错误：ext 中缺少 host")
            return
        global _UA
        if "ua" in self.ext_config and self.ext_config["ua"]:
            _UA = self.ext_config["ua"]
        if "meili_index" in self.ext_config:
            self.meili_index = self.ext_config["meili_index"]
        if "meili_host" in self.ext_config:
            self.meili_host = self.ext_config["meili_host"]
        if "cate_block" in self.ext_config:
            c = self.ext_config["cate_block"].strip()
            if c:
                self.cate_block = [x.strip() for x in c.split(",") if x.strip()]
        from_str = self.ext_config.get("from", "").strip()
        if from_str:
            if '@' in from_str:
                sort_part, block_part = from_str.split('@', 1)
                self.order_keywords = [x.strip() for x in sort_part.split(",") if x.strip()]
                self.block_keywords = [x.strip() for x in block_part.split(",") if x.strip()]
            else:
                self.order_keywords = [x.strip() for x in from_str.split(",") if x.strip()]
        if "device_id" not in self.ext_config or not self.ext_config["device_id"]:
            self.ext_config["device_id"] = hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
        self._warmup()
    def _client(self):
        if self._cli is None:
            cfg = {
                "host": self.ext_config.get("host", ""),
                "nsKey": self.ext_config.get("key", ""),
                "device_id": self.ext_config.get("device_id", ""),
            }
            self._cli = _Client(cfg)
        return self._cli
    def _warmup(self):
        _log("开始预热")
        try:
            c = self._client()
            init = c.call("initV4", {
                "device_id": self.ext_config.get("device_id", ""),
                "app_version": self.ext_config.get("app_version", "1.0.1")
            })
            if not init:
                _log("initV4 返回空")
                return
            self._init_cache = (init, time.time())
            cfg = init.get("config", {})
            self.meili_key = cfg.get("meili_master_key") or ""
            _log(f"meili_key: {self.meili_key[:4] if self.meili_key else 'None'}...")
            type_list = init.get("type_list", [])
            for t in type_list:
                tid = t.get("type_id")
                if tid in (0, None):
                    continue
                cate_name = t.get("type_name", str(tid))
                if any(kw in cate_name for kw in self.cate_block):
                    _log(f"分类 {cate_name} 被屏蔽")
                    continue
                self._types[tid] = cate_name
                fs = []
                try:
                    ext = json.loads(t.get("type_extend") or "{}")
                    for key, label in (("class", "类型"), ("area", "地区"), ("year", "年份"), ("lang", "语言")):
                        raw = str(ext.get(key) or "").strip()
                        if not raw:
                            continue
                        opts = [x for x in raw.split(",") if x.strip()]
                        opts = [{"n": (o[:6] + "…") if len(o) > 8 else o, "v": o} for o in opts]
                        fs.append({"key": key, "name": label,
                                   "value": [{"n": "全部", "v": ""}] + opts})
                except Exception:
                    pass
                if fs:
                    self._filters[tid] = fs
            self._home_list = []
            for item in init.get("banner_list", []) + init.get("recommend_list", []):
                self._home_list.append({
                    "vod_id": str(item.get("vod_id", "")),
                    "vod_name": item.get("vod_name", ""),
                    "vod_pic": (item.get("vod_pic") or "").replace("\\/", "/"),
                    "vod_remarks": item.get("vod_remarks", ""),
                })
        except Exception as e:
            _log(f"预热异常: {e}")
            import traceback
            _log(traceback.format_exc())
        if not self._types:
            self._types = {1: "电影", 2: "电视剧", 3: "动漫", 4: "综艺",
                           22: "短剧", 6: "纪录片", 21: "体育", 23: "直播"}
    def homeContent(self, filter1=1):
        classes = [{"type_id": k, "type_name": v} for k, v in self._types.items()]
        out = {"class": classes}
        if self._filters:
            out["filters"] = {str(k): v for k, v in self._filters.items()}
        out["list"] = self._home_list[:20]
        return out
    def homeVideoContent(self):
        if not self._home_list:
            self._warmup()
        return {"list": self._home_list[:20]}
    def categoryContent(self, tid, pg=1, filter1=1, ext=None):
        if isinstance(ext, str):
            try:
                ext = json.loads(ext) if ext.strip() else {}
            except Exception:
                ext = {}
        ext = ext or {}
        try:
            page = int(pg)
        except:
            page = 1
        try:
            tid = int(tid)
        except:
            pass
        c = self._client()
        r = c.call("typeFilterVodList", {
            "type_id": tid,
            "page": page,
            "area": ext.get("area", ""),
            "year": ext.get("year", ""),
            "lang": ext.get("lang", ""),
            "class": ext.get("class", ""),
            "sort": ext.get("sort", "")
        })
        vods = []
        for v in (r or {}).get("recommend_list", []):
            vods.append({
                "vod_id": str(v.get("vod_id", "")),
                "vod_name": v.get("vod_name", ""),
                "vod_pic": (v.get("vod_pic") or "").replace("\\/", "/"),
                "vod_remarks": v.get("vod_remarks", ""),
            })
        more = len(vods) >= 20
        return {"list": vods, "page": page,
                "pagecount": page + 1 if more else page,
                "limit": "20", "total": (page + 30) if more else page * 20}
    
    # ---------- 新 detailContent（双线路名，参考新qiji） ----------
    def detailContent(self, ids):
        vid = str(ids[0])
        if vid in self._detail_cache:
            return self._detail_cache[vid]
        try:
            c = self._client()
            r = c.call("vodDetail3", {"vod_id": int(vid)})
        except Exception as e:
            _log(f"detailContent 异常: {e}")
            return {"list": []}
        if not r:
            return {"list": []}
        vod = r.get("vod", {})

        play_infos = []
        for p in r.get("vod_play_list", []):
            pi = p.get("player_info", {})
            urls = p.get("urls", [])
            if isinstance(urls, str):
                urls = self._parse_urls(urls)
            if not urls:
                continue

            # 从第一个剧集获取 from 字段（线路标识）
            from_val = urls[0].get("from", "")
            show_base = pi.get("show") or from_val
            display_name = f"{show_base}({from_val})" if from_val else show_base

            parse_api = pi.get("parse", "")
            parse_type = pi.get("player_parse_type", "1")

            play_infos.append({
                "from": display_name,
                "player_info": pi,
                "parse_api": parse_api,
                "parse_type": parse_type,
                "urls": urls,
            })

        # 过滤
        if self.block_keywords:
            play_infos = [info for info in play_infos
                          if not any(kw in info["from"] for kw in self.block_keywords)]

        # 排序
        if self.order_keywords:
            def order_score(info):
                name = info["from"]
                for idx, kw in enumerate(self.order_keywords):
                    if kw in name:
                        return idx
                return len(self.order_keywords)
            play_infos.sort(key=order_score)

        display_mode = self.ext_config.get("line", {}).get("display", "single")
        play_froms = []
        play_urls = []
        for info in play_infos:
            from_name = info["from"]
            parse_api = info["parse_api"]
            parse_type = info["parse_type"]

            if display_mode == "double":
                suffix = " [解析]" if parse_api else " [直连]"
                final_name = from_name + suffix
            else:
                final_name = from_name

            eps = []
            for e in info["urls"]:
                name = str(e.get("name", ""))
                u = e.get("url", "")
                if u.startswith("http") and not parse_api:
                    tok = "D|" + u
                else:
                    tok = "P|" + base64.b64encode(json.dumps(
                        {"p": parse_api, "t": parse_type, "u": u}, ensure_ascii=False).encode()).decode()
                eps.append(name + "$" + tok)

            play_froms.append(final_name)
            play_urls.append("#".join(eps))

        v = {
            "vod_id": vid,
            "vod_name": vod.get("vod_name", ""),
            "vod_pic": (vod.get("vod_pic") or "").replace("\\/", "/"),
            "type_name": (vod.get("vod_class") or "").split(",")[0],
            "vod_year": vod.get("vod_year", ""),
            "vod_area": vod.get("vod_area", ""),
            "vod_actor": vod.get("vod_actor", ""),
            "vod_director": vod.get("vod_director", ""),
            "vod_content": (vod.get("vod_blurb") or "").replace("\\n", "\n"),
            "vod_remarks": vod.get("vod_remarks", ""),
            "vod_play_from": "$$$".join(play_froms),
            "vod_play_url": "$$$".join(play_urls),
        }
        ret = {"list": [v]}
        self._detail_cache[vid] = ret
        if len(self._detail_cache) > 80:
            self._detail_cache.pop(next(iter(self._detail_cache)))
        return ret

    @staticmethod
    def _parse_urls(s):
        s = s.strip()
        try:
            return json.loads(s)
        except Exception:
            pass
        try:
            return eval(s)
        except Exception:
            pairs = re.findall(r"'name'\s*:\s*'([^']*)'.*?'url'\s*:\s*'([^']*)'", s, re.S)
            return [{"name": n, "url": u} for n, u in pairs]
    def playerContent(self, flag, id, vipFlags=None):
        ck = str(id)
        if ck in self._play_cache:
            hit = self._play_cache[ck]
            if time.time() - hit[0] < 1800:
                return hit[1]
            self._play_cache.pop(ck, None)
        tok = str(id)
        try:
            kind, payload = tok.split("|", 1)
        except ValueError:
            return {"url": tok, "header": {"User-Agent": _UA}}
        if kind == "D":
            out = {"url": payload, "header": {"User-Agent": _UA}}
        else:
            try:
                info = json.loads(base64.b64decode(payload))
            except Exception:
                return {"url": "", "msg": "参数错误"}
            try:
                c = self._client()
                r = c.vod_parse(info.get("p", ""), info.get("t", "1"), info.get("u", ""))
                real = (r or {}).get("url") or ""
                real = real.replace("\\/", "/")
            except Exception as e:
                _log(f"播放解析异常: {e}")
                real = ""
            if not real:
                return {"url": "", "msg": "解析失败，请换线路"}
            out = {"url": real, "header": {"User-Agent": _UA}}
        if len(self._play_cache) > 150:
            self._play_cache.pop(next(iter(self._play_cache)))
        self._play_cache[ck] = (time.time(), out)
        return out

    def _fetch_meili_key(self):
        if hasattr(self, '_meili_failed') and self._meili_failed:
            return ""
        try:
            app_ver = self.ext_config.get("app_version", "6.0.4")
            init = self._client().call("initV4", {
                "device_id": self.ext_config.get("device_id", ""),
                "app_version": app_ver
            })
            mk = (init or {}).get("config", {}).get("meili_master_key") or ""
            if not mk:
                _log("initV4未获取meili_key，尝试initV119")
                init = self._client().call("initV119", {
                    "device_id": self.ext_config.get("device_id", ""),
                    "app_version": app_ver
                })
                mk = (init or {}).get("config", {}).get("meili_master_key") or ""
            if mk:
                self.meili_key = mk
                _log(f"成功获取 meili_key: {mk[:4]}...")
                return mk
            _log("initV4 / initV119 均未返回 meili_master_key")
            self._meili_failed = True
        except Exception as e:
            _log(f"获取 meili_key 异常: {e}")
            self._meili_failed = True
        return ""

    def _search_via_api(self, key, page):
        out = []
        seen = set()
        try:
            cli = self._client()
            dev_id = cli.cfg.get("device_id", "")
            app_ver = self.ext_config.get("app_version", "6.0.4")
            key_l = key.lower()

            def _add(v):
                vid = str(v.get("vod_id", ""))
                if not vid or vid in seen:
                    return
                seen.add(vid)
                out.append({
                    "vod_id": vid,
                    "vod_name": v.get("vod_name", ""),
                    "vod_pic": (v.get("vod_pic") or "").replace("\\/", "/"),
                    "vod_remarks": v.get("vod_remarks", ""),
                })

            for p in range(1, 3):
                if len(out) >= 25:
                    break
                params = {
                    "device_id": dev_id,
                    "app_version": app_ver,
                    "keyword": key,
                    "page": p,
                    "limit": 20,
                    "type_id": 0,
                }
                r = cli.call("searchList", params)
                if not r:
                    break
                sl = r.get("search_list", [])
                if not sl:
                    break
                for v in sl:
                    if key_l in (v.get("vod_name") or "").lower():
                        _add(v)
            _log(f"API searchList 搜索 '{key}' 返回 {len(out)} 条")
        except Exception as e:
            _log(f"API searchList 异常: {e}")
        return out

    def _search_fallback(self, key):
        out = []
        key_l = key.lower()
        for tid in list(self._types.keys())[:2]:
            try:
                c = self._client()
                r = c.call("typeFilterVodList", {
                    "type_id": tid,
                    "page": 1,
                    "area": "",
                    "year": "",
                    "lang": "",
                    "class": "",
                    "sort": ""
                })
                if not r:
                    continue
                for v in r.get("recommend_list", []):
                    if key_l in (v.get("vod_name") or "").lower():
                        out.append({
                            "vod_id": str(v.get("vod_id", "")),
                            "vod_name": v.get("vod_name", ""),
                            "vod_pic": (v.get("vod_pic") or "").replace("\\/", "/"),
                            "vod_remarks": v.get("vod_remarks", ""),
                        })
            except Exception as e:
                _log(f"fallback 分类 {tid} 搜索异常: {e}")
                continue
            if len(out) >= 20:
                break
        return out

    def _search(self, key, pg=None):
        key = str(key or "").strip()
        if not key:
            return {"list": []}
        try:
            page = int(pg) if pg not in (None, "", 0, "0") else 1
        except:
            page = 1
        ck = key + "|" + str(page)
        now = time.time()
        for k in list(self._search_cache):
            if now - self._search_cache[k][0] > 300:
                self._search_cache.pop(k, None)
        if ck in self._search_cache:
            return self._search_cache[ck][1]

        out = []
        # ---- 1. MeiliSearch ----
        try:
            cli = self._client()
            host = self.meili_host
            if not host:
                base = cli._host
                if "://" in base:
                    proto, rest = base.split("://", 1)
                    host = proto + "://" + rest.split(":")[0] + ":7700"
                else:
                    host = "http://" + base.split(":")[0] + ":7700"
            if not host.startswith("http"):
                host = "http://" + host
            mk = self.meili_key
            if not mk:
                mk = self._fetch_meili_key()
            _log(f"搜索索引: {self.meili_index}, 主机: {host}, meili_key: {mk[:4] if mk else 'None'}")
            if mk:
                limit, offset = 20, (page - 1) * 20
                body = json.dumps({"q": key, "limit": limit, "offset": offset}).encode()
                req = urllib.request.Request(
                    f"{host}/indexes/{self.meili_index}/search",
                    data=body, method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + mk,
                        "User-Agent": _UA
                    }
                )
                with urllib.request.urlopen(req, timeout=12, context=_SSL) as r:
                    res = json.loads(r.read().decode())
                for h in res.get("hits", []):
                    out.append({
                        "vod_id": str(h.get("vod_id", "")),
                        "vod_name": h.get("vod_name", ""),
                        "vod_pic": (h.get("vod_pic") or "").replace("\\/", "/"),
                        "vod_remarks": h.get("vod_remarks", ""),
                    })
                _log(f"MeiliSearch 返回 {len(out)} 条")
        except Exception as e:
            _log(f"MeiliSearch 异常: {e}")

        # ---- 2. searchList ----
        if not out:
            _log("MeiliSearch 无结果，尝试 searchList API")
            out = self._search_via_api(key, page)

        # ---- 3. 兜底分类（仅前2个） ----
        if not out:
            _log("searchList 无结果，尝试分类兜底（仅前2个分类）")
            out = self._search_fallback(key)

        ret = {"list": out[:25], "page": page,
               "pagecount": page + 1 if len(out) >= 20 else page}
        self._search_cache[ck] = (time.time(), ret)
        return ret

    def searchContent(self, key, quick=None, pg=None):
        return self._search(key, pg)
    def searchContentPage(self, key, quick=None, pg=None):
        return self._search(key, pg)

# ================= TVBox 模块级入口 =================
_SP = None
_SP_T = 0.0
def _ensure():
    global _SP, _SP_T
    if _SP is None or time.time() - _SP_T > 8 * 3600:
        _log("创建 Spider 实例")
        _SP = Spider()
        _SP_T = time.time()
    return _SP
def init(ext=""):
    return _ensure().init(ext)
def homeContent(filter1=1):
    return _ensure().homeContent(filter1)
def homeVideoContent():
    return _ensure().homeVideoContent()
def categoryContent(tid, pg=1, filter1=1, ext=None):
    return _ensure().categoryContent(tid, pg, filter1, ext)
def detailContent(ids):
    return _ensure().detailContent(ids)
def playerContent(flag, id, vipFlags=None):
    return _ensure().playerContent(flag, id, vipFlags)
def searchContent(key, quick=0, pg=None):
    return _ensure().searchContent(key, quick, pg)
def searchContentPage(key, quick=0, pg=None):
    return _ensure().searchContentPage(key, quick, pg)