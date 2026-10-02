#!/usr/bin/python
# -*- coding: utf-8 -*-
import json
import re
import time
import base64
import hashlib
import hmac
import os
import urllib.parse
import requests

try:
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass

from base.spider import Spider

DEF = {
    "host": "",
    "ua": "okhttp/4.12.0",
    "app_version": "1.0.1",
    "device_id": "samsung.Samsung",
    "sign_device": "samsung.Samsung",
    "timeout": 15,
    "page_size": 20,
    "name": "同壳影视",
}



def _canonical_query(q):
    if not q:
        return ""
    pairs = []
    for kv in q.split("&"):
        if not kv:
            continue
        if "=" in kv:
            k, v = kv.split("=", 1)
        else:
            k, v = kv, ""
        pairs.append((k, v))
    pairs.sort(key=lambda x: x[0])
    return "&".join("%s=%s" % (k, v) for k, v in pairs)


def _norm_dev(d):
    d = (d or "").strip()
    if not d:
        return d
    parts = d.split(".")
    return ".".join(parts[:2]) if len(parts) > 2 else d


class _Session:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session_id = None
        self.key = None
        self.offset = 0
        self.expires = 0
        self._sess = requests.session()
        self._sess.verify = False

    def _raw(self, method, path, body=None, headers=None):
        url = self.cfg["host"] + path
        hd = {"User-Agent": self.cfg["ua"], "X-Device-Risk": "0", "Accept": "application/json"}
        if headers:
            hd.update(headers)
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode()
            hd["Content-Type"] = "application/json; charset=utf-8"
        try:
            r = self._sess.request(method, url, data=data, headers=hd, timeout=self.cfg["timeout"])
            return r.content
        except Exception:
            return None

    def handshake(self):
        try:
            cr = json.loads(self._raw("GET", "/api/v1/security/challenge") or b"{}")
            cr = cr.get("data") or cr
            if not cr.get("challenge"):
                return False
            body = {"platform": "android", "version": self.cfg["app_version"], "device_id": self.cfg["sign_device"]}
            raw = self._raw("POST", "/api/v1/security/init", body)
            if not raw:
                return False
            init = json.loads(raw)
            init = init.get("data") or init
            if not init.get("session_id") or not init.get("sign_key"):
                return False
            self.session_id = init["session_id"]
            self.key = init["sign_key"].encode()
            self.offset = int(init.get("server_time") or 0) - int(time.time())
            self.expires = time.time() + int(init.get("expires_in") or 600) - 30
            return True
        except Exception:
            return False

    def sign_headers(self, method, path, body_bytes=None):
        if not self.session_id or time.time() > self.expires:
            if not self.handshake():
                return {}
        ts = str(int(time.time() + self.offset))
        nonce = os.urandom(16).hex()
        bs = hashlib.sha256(b"").hexdigest() if body_bytes is None else hashlib.sha256(body_bytes).hexdigest()
        s = "\n".join([
            method.upper(),
            path.split("?")[0],
            _canonical_query(path.split("?")[1] if "?" in path else ""),
            bs, ts, nonce, self.cfg["sign_device"], self.session_id, self.cfg["app_version"],
        ])
        sg = hmac.new(self.key, s.encode(), hashlib.sha256).hexdigest()
        return {
            "X-Session-Id": self.session_id,
            "X-Timestamp": ts,
            "X-Nonce": nonce,
            "X-Sign": sg,
            "X-Body-Sha256": bs,
            "X-App-Version": self.cfg["app_version"],
            "X-Device-Id": self.cfg["sign_device"],
        }

    def get_json(self, path):
        hd = self.sign_headers("GET", path)
        raw = self._raw("GET", path, headers=hd) if hd else self._raw("GET", path)
        try:
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def post_json(self, path, body):
        bb = json.dumps(body, separators=(",", ":")).encode()
        hd = self.sign_headers("POST", path, bb)
        if not hd:
            return None
        raw = self._raw("POST", path, body, headers=hd)
        try:
            return json.loads(raw) if raw else None
        except Exception:
            return None


def _fix_url(u, host):
    if not u:
        return ""
    u = str(u).strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return host + u
    return u


def _safe(v):
    return v if v is not None else ""


def _extract_tk(pid):
    m = re.search(r"(?:^|\$)(tk:[A-Za-z0-9_\-\.]+)", str(pid))
    if m:
        return m.group(1)
    if str(pid).startswith("tk:"):
        return str(pid)
    return None


def _jwt_payload(ticket):
    part = ticket.split(".")[0]
    pad = part + "=" * (-len(part) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(pad))
    except Exception:
        return None


class Spider(Spider):
    def __init__(self):
        self.cfg = dict(DEF)
        self.S = _Session(self.cfg)

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            s = extend.strip()
            try:
                cfg = json.loads(s) if s.startswith("{") else {"host": s}
            except Exception:
                cfg = {"host": s}
        if not isinstance(cfg, dict):
            cfg = {}
        for k in ("host", "ua", "app_version", "device_id", "sign_device", "name"):
            if cfg.get(k):
                self.cfg[k] = str(cfg[k])
        for k in ("timeout", "page_size"):
            if cfg.get(k):
                try:
                    self.cfg[k] = int(cfg[k])
                except Exception:
                    pass
        self.cfg["sign_device"] = _norm_dev(self.cfg["sign_device"] or self.cfg["device_id"])
        self.cfg["host"] = self.cfg["host"].rstrip("/")
        self.name = self.cfg["name"]
        self.host = self.cfg["host"]
        self.S = _Session(self.cfg)
    def destroy(self):
        pass

    def getName(self):
        return self.cfg.get("name", DEF["name"])

    def getVersion(self):
        return "1.1.0"

    def isVideoFormat(self, url):
        return bool(re.match(r"(?i).*\.(mp4|m3u8|flv|mkv|avi|ts|mov|mpd|m4a|wmv)(\?.*)?$", str(url)))

    def manualSniffer(self, needGoto):
        return False

    def homeContent(self, filter=False):
        classes = []
        filters = {}
        data = self.S.get_json("/api/v1/category/filters?type_id=1")
        if data:
            d = data.get("data") or {}
            for c in d.get("categories", []):
                classes.append({
                    "type_id": str(c.get("type_id")),
                    "type_name": _safe(c.get("type_name")),
                })
            if str(filter).lower() == "true":
                f_item = []
                years = ["全部"] + [str(y) for y in (d.get("years") or []) if str(y) != "全部"]
                f_item.append({
                    "key": "year", "name": "年份",
                    "value": [{"n": str(v), "v": "" if str(v) == "全部" else str(v)} for v in years],
                })
                f_item.append({
                    "key": "area", "name": "地区",
                    "value": [{"n": str(v), "v": "" if str(v) == "全部" else str(v)} for v in (d.get("areas") or [])],
                })
                f_item.append({
                    "key": "class", "name": "类型",
                    "value": [{"n": str(v), "v": "" if str(v) == "全部" else str(v)} for v in (d.get("classes") or [])],
                })
                f_item.append({
                    "key": "lang", "name": "语言",
                    "value": [{"n": str(v), "v": "" if str(v) == "全部" else str(v)} for v in (d.get("langs") or [])],
                })
                f_item.append({
                    "key": "sort", "name": "排序",
                    "value": [{"n": s.get("label", ""), "v": s.get("value", "")} for s in (d.get("sorts") or [])],
                })
                for c in classes:
                    filters[c["type_id"]] = f_item
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return self.categoryContent("1", 1, "", {})

    def categoryContent(self, tid, pg, filter, extend):
        params = ["type_id=%s" % tid, "page=%s" % pg]
        if extend:
            for k in ("sort", "year", "area", "class", "lang"):
                val = extend.get(k)
                if val:
                    params.append("%s=%s" % (k, urllib.parse.quote(str(val))))
        data = self.S.get_json("/api/v1/category/videos?" + "&".join(params))
        videos = []
        pagecount, total = 1, 0
        if data:
            d = data.get("data") or {}
            pg_info = d.get("pagination") or {}
            pagecount = int(pg_info.get("total_pages") or 1)
            total = int(pg_info.get("total") or 0)
            seen = set()
            for v in (d.get("videos") or d.get("hits") or []):
                vid = str(v.get("vod_id", ""))
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                videos.append(self._list_item(v))
        print("[%s] 分类 %s 第%s页 匹配到 %s 个视频" % (self.name, tid, pg, len(videos)))
        return {
            "list": videos,
            "page": int(pg) if str(pg).isdigit() else 1,
            "pagecount": max(pagecount, 1),
            "limit": self.cfg["page_size"],
            "total": total,
        }

    def searchContent(self, key, quick=False, pg="1"):
        data = self.S.get_json("/api/v1/search?wd=%s&page=%s" % (
            urllib.parse.quote(str(key)), pg))
        videos = []
        pagecount, total = 1, 0
        if data:
            d = data.get("data") or {}
            pagecount = int(d.get("total_pages") or (d.get("pagination") or {}).get("total_pages") or 1)
            total = int(d.get("total") or (d.get("pagination") or {}).get("total") or 0)
            seen = set()
            for h in (d.get("hits") or d.get("videos") or []):
                vid = str(h.get("vod_id", ""))
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                videos.append(self._list_item(h))
        print("[%s] 搜索 '%s' 第%s页 匹配到 %s 个结果" % (self.name, key, pg, len(videos)))
        return {
            "list": videos,
            "page": int(pg) if str(pg).isdigit() else 1,
            "pagecount": max(pagecount, 1),
            "limit": self.cfg["page_size"],
            "total": total,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        data = self.S.get_json("/api/v1/video/detail?id=%s" % ids[0])
        if not data:
            return {"list": []}
        info = (data.get("data") or {}).get("vod_info") or {}
        if not info.get("vod_id"):
            return {"list": []}
        vod = {
            "vod_id": str(info.get("vod_id", "")),
            "vod_name": _safe(info.get("vod_name")),
            "vod_sub": _safe(info.get("vod_sub")),
            "vod_pic": _fix_url(_safe(info.get("vod_pic")), self.cfg["host"]),
            "vod_actor": _safe(info.get("vod_actor")),
            "vod_director": _safe(info.get("vod_director")),
            "vod_area": _safe(info.get("vod_area")),
            "vod_lang": _safe(info.get("vod_lang")),
            "vod_year": str(info.get("vod_year") or ""),
            "vod_remarks": _safe(info.get("vod_remarks")),
            "vod_class": _safe(info.get("vod_class")),
            "vod_score": _safe(info.get("vod_score")),
            "vod_content": _safe(info.get("vod_content")) or _safe(info.get("vod_blurb")),
            "vod_pubdate": _safe(info.get("vod_pubdate")),
            "type_name": _safe(info.get("type_name")),
        }
        players = info.get("vod_url_with_player") or []
        play_from, play_url, seen_from = [], [], set()
        for p in players:
            name = p.get("name") or p.get("code") or ""
            url = p.get("url") or ""
            if not name or not url:
                continue
            if name in seen_from:
                continue
            seen_from.add(name)
            play_from.append(name)
            play_url.append(url.strip("#"))
        if play_from:
            vod["vod_play_from"] = "$$$".join(play_from)
            vod["vod_play_url"] = "$$$".join(play_url)
        else:
            vod["vod_play_from"] = "提示"
            vod["vod_play_url"] = "提示$该分类暂不支持在线播放，请查看剧情简介或切换其他源"
        print("[%s] 详情 %s 提取到 %s 个播放源" % (self.name, ids[0], len(play_from)))
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        tok = _extract_tk(id)
        if not tok:
            if self.isVideoFormat(id):
                return {"parse": 0, "playUrl": "", "url": str(id), "header": {"User-Agent": self.cfg["ua"]}}
            return {"parse": 0, "playUrl": "", "url": str(id), "header": {}}
        r = self.S.post_json("/api/v1/vod/ticket", {"token": tok})
        if not r or r.get("code") != 1:
            return {"parse": 0, "playUrl": "", "url": str(id), "header": {}}
        ticket = (r.get("data") or {}).get("ticket") or ""
        payload = _jwt_payload(ticket)
        if not payload:
            return {"parse": 0, "playUrl": "", "url": str(id), "header": {}}
        d = payload.get("data") or {}
        enc_url = d.get("url") or ""
        parse_api = d.get("parse_api") or ""
        if not enc_url:
            return {"parse": 0, "playUrl": "", "url": str(id), "header": {}}
        if not parse_api and enc_url.startswith("http"):
            return {"parse": 0, "playUrl": "", "url": enc_url, "header": {"User-Agent": self.cfg["ua"]}}
        if not parse_api:
            return {"parse": 0, "playUrl": "", "url": str(id), "header": {}}
        full = parse_api + urllib.parse.quote(enc_url, safe="")
        j = None
        try:
            if full.startswith("http"):
                r2 = self.S._sess.get(full, headers={"User-Agent": self.cfg["ua"]}, timeout=self.cfg["timeout"], verify=False)
                j = r2.json()
            else:
                p = full if full.startswith("/") else "/" + full
                j = self.S.get_json(p)
        except Exception:
            j = None
        if isinstance(j, dict) and j.get("url") and str(j.get("code")) in ("200", "1"):
            play = j["url"]
            print("[%s] 播放解析: %s -> %s" % (self.name, str(tok)[:24], play[:70]))
            return {"parse": 0, "playUrl": "", "url": play, "header": {"User-Agent": self.cfg["ua"]}}
        return {"parse": 0, "playUrl": "", "url": str(id), "header": {}}

    def _list_item(self, v):
        return {
            "vod_id": str(v.get("vod_id", "")),
            "vod_name": _safe(v.get("vod_name")),
            "vod_pic": _fix_url(_safe(v.get("vod_pic")), self.cfg["host"]),
            "vod_remarks": _safe(v.get("vod_remarks")),
            "vod_score": _safe(v.get("vod_score")),
            "vod_actor": _safe(v.get("vod_actor")),
            "vod_area": _safe(v.get("vod_area")),
            "vod_year": str(v.get("vod_year") or ""),
            "type_name": _safe(v.get("type_name")),
        }


_sp = None


def _g():
    global _sp
    if _sp is None:
        _sp = Spider()
        _sp.init("")
    return _sp


def init(extend=""):
    global _sp
    _sp = Spider()
    _sp.init(extend)


def homeContent(filter=False):
    return _g().homeContent(filter)


def homeVideoContent():
    return _g().homeVideoContent()


def categoryContent(tid, pg, filter, extend):
    return _g().categoryContent(tid, pg, filter, extend)


def detailContent(ids):
    return _g().detailContent(ids)


def searchContent(key, quick=False, pg="1"):
    return _g().searchContent(key, quick, pg)


def playerContent(flag, id, vipFlags):
    return _g().playerContent(flag, id, vipFlags)


def getName():
    return _g().getName()
