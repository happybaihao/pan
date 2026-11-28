#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import json
import base64
import threading
from urllib.parse import quote, urlparse

import requests
from base.spider import Spider

try:
    requests.packages.urllib3.disable_warnings(
        requests.packages.urllib3.exceptions.InsecureRequestWarning
    )
except Exception:
    pass

DEFAULT_HOST = "https://www.xn--74qz10cqsltibh40akss.com"
DEFAULT_IMG = "https://img.1234cdn.com/img"
UA = ("Mozilla/5.0 (Linux; Android 16; Pixel 9 Pro Build/BP1A.250305.019) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.7743.101 Mobile Safari/537.36")

BLOCK_PAN = ("123",)
BLOCK_PAN_DOMAIN = ("123pan", "123684", "123865", "123912")
PAGE_SIZE = 48


class Spider(Spider):
    def getName(self):
        return "观影"

    def init(self, extend=""):
        self.host = DEFAULT_HOST
        self.img = DEFAULT_IMG
        self.user = ""
        self.pwd = ""
        self.cookie = ""
        self.classes = {"mv": "电影", "tv": "剧集", "ac": "动漫"}
        self._lock = threading.RLock()
        self._verified = False
        self._login_ok = False
        self._login_tried = False
        self._login_msg = ""

        ext = self._ext(extend)
        inner = ext.get("ext")
        if isinstance(inner, dict):
            merged = dict(ext)
            merged.update(inner)
            ext = merged
        host = str(ext.get("host") or ext.get("url") or "").strip().rstrip("/")
        if host:
            if not host.lower().startswith("http"):
                host = "https://" + host
            self.host = host
        self.img = str(ext.get("img") or ext.get("image") or DEFAULT_IMG).rstrip("/")
        self.user = str(ext.get("username") or ext.get("user") or "")
        self.pwd = str(ext.get("password") or ext.get("pwd") or "")
        self.cookie = str(ext.get("cookie") or "")

        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/",
            "X-Requested-With": "XMLHttpRequest",
        })
        self._set_cookie(self.cookie)

    @staticmethod
    def _ext(endpoint=""):
        if isinstance(endpoint, dict):
            return dict(endpoint)
        s = str(endpoint or "").strip()
        if not s:
            return {}
        if s[0] in "{[":
            for cand in (s, s.replace("'", '"')):
                try:
                    d = json.loads(cand)
                    if isinstance(d, dict):
                        return d
                except Exception:
                    continue
        if "=" in s and "{" not in s:
            out = {}
            for part in re.split(r"[&;]", s):
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k.strip():
                        out[k.strip()] = v.strip()
            known = {"host", "url", "img", "image", "username", "user",
                     "password", "pwd", "cookie", "ext"}
            if out and (set(out) & known):
                return out
        return {"cookie": s}

    def _set_cookie(self, cookie):
        cookie = str(cookie or "").strip()
        if not cookie:
            return
        self.cookie = cookie
        self.session.headers["Cookie"] = cookie
        dom = urlparse(self.host).hostname or ""
        for part in cookie.split(";"):
            if "=" not in part:
                continue
            k, v = part.strip().split("=", 1)
            try:
                self.session.cookies.set(k, v, domain=dom, path="/")
            except Exception:
                pass

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def _pow(self):
        cid = ""
        try:
            page = self.session.get(self.host + "/", timeout=15).text or ""
            m = re.search(r'powChallengeId\s*[=:]\s*"([0-9A-Za-z_-]+)"', page)
            if m:
                cid = m.group(1)
        except Exception:
            pass
        try:
            hdr = {"X-Pow-Id": cid} if cid else {}
            d = self.session.get(self.host + "/res/pow", headers=hdr, timeout=20).json()
            n = int(str(d["N"]), 16)
            x = int(str(d["x"]), 16)
            t = int(d.get("t") or 0)
            y = pow(x, 1 << t, n)
            body = {"y": format(y, "x")}
            cid2 = d.get("challenge_id") or cid
            if cid2:
                body["id"] = cid2
            r = self.session.post(self.host + "/res/pow", data=body, timeout=30).json()
            return bool(r.get("success"))
        except Exception:
            return False

    def _login(self):
        with self._lock:
            if self._login_ok:
                return True
            if self._login_tried:
                return False
            if not (self.user and self.pwd):
                self._login_msg = "ext 未配置 username/password，且 cookie 已失效"
                self._login_tried = True
                return False
            self._login_tried = True
            try:
                r = self.session.post(
                    self.host + "/user/login",
                    data={
                        "code": "",
                        "siteid": "1",
                        "dosubmit": "1",
                        "cookietime": "10506240",
                        "username": self.user,
                        "password": self.pwd,
                    },
                    headers={"Referer": self.host + "/user/login",
                             "Accept": "application/json, text/javascript, */*; q=0.01"},
                    timeout=20,
                )
                j = r.json()
            except Exception:
                self._login_msg = "登录请求失败（返回非 JSON，可能被验证拦截）"
                if self._pow():
                    self._verified = True
                return False
            if j.get("code") == 200 or j.get("success") is True:
                self._login_ok = True
                self._verified = True
                self._login_msg = ""
                ck = "; ".join("%s=%s" % (c.name, c.value) for c in self.session.cookies)
                if ck:
                    self.cookie = ck
                return True
            self._login_msg = str(j.get("msg") or "登录失败")
            if j.get("captcha"):
                self._login_msg += "（站点要求图形验证码，请改用 cookie 方式登录）"
            return False

    @staticmethod
    def _is_pow(txt):
        if not txt:
            return False
        if "powSolve" in txt:
            return True
        s = txt.replace(" ", "")
        return '"refresh":1' in s or '"code":419' in s

    @staticmethod
    def _is_nologin(txt):
        return bool(txt) and "未登录" in txt and "nologin" in txt

    def _req(self, u, ref="", retry=2):
        url = u if str(u).startswith("http") else self.host + u
        hdr = {"Referer": ref or self.host + "/"}
        for _ in range(retry + 1):
            try:
                r = self.session.get(url, headers=hdr, timeout=20)
            except Exception:
                return ""
            txt = r.text or ""
            if self._is_pow(txt):
                if self._pow():
                    self._verified = True
                    continue
                return ""
            if self._is_nologin(txt):
                if self._login():
                    continue
                return ""
            return txt
        return ""

    def _json_get(self, u, ref=""):
        try:
            return json.loads(self._req(u, ref))
        except Exception:
            return {}

    def _b64e(self, o):
        s = o if isinstance(o, str) else json.dumps(o, ensure_ascii=False, separators=(",", ":"))
        return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")

    def _b64d(self, s):
        try:
            raw = base64.urlsafe_b64decode((str(s) + "=" * (-len(str(s)) % 4)).encode()).decode()
        except Exception:
            return s
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def _obj(self, h, k):
        if not h:
            return None
        m = re.search(r"_obj\.%s\s*=\s*" % re.escape(k), h)
        if not m:
            m = re.search(r'_obj\["%s"\]\s*=\s*' % re.escape(k), h)
        if not m:
            return None
        i = m.end()
        while i < len(h) and h[i].isspace():
            i += 1
        if i >= len(h):
            return None
        c = h[i]
        if c in "\"'":
            j = h.find(c, i + 1)
            return h[i + 1:j] if j > 0 else None
        if c not in "[{":
            j = h.find(";", i)
            return h[i:j if j > 0 else len(h)].strip().strip("\"'")
        q = c
        end = "}" if q == "{" else "]"
        deep, ins, esc, out = 0, False, False, []
        for ch in h[i:]:
            out.append(ch)
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                ins = not ins
                continue
            if ins:
                continue
            if ch == q:
                deep += 1
            elif ch == end:
                deep -= 1
                if deep == 0:
                    break
        s = "".join(out).replace("\\/", "/").replace("\\'", "'")
        for cand in (s, re.sub(r",\s*([}\]])", r"\1", s)):
            try:
                return json.loads(cand)
            except Exception:
                continue
        return None

    def _pic(self, d, i):
        return "%s/%s/%s/256.webp" % (self.img, d, i) if d and i else ""

    def _phdr(self):
        return {"User-Agent": UA, "Referer": self.host + "/"}

    def _vod(self, name, i, d, remarks="", extra=None):
        d = str(d or "mv")
        i = str(i or "")
        title = name if isinstance(name, str) else (name or "")
        item = {"title": str(title or "未知"), "id": i, "dir": d, "remarks": str(remarks or "")}
        if isinstance(extra, dict):
            for k in ("year", "area", "score", "type", "ename", "lang"):
                v = extra.get(k)
                if v not in (None, ""):
                    item[k] = v
        return {
            "vod_id": self._b64e(item),
            "vod_name": item["title"],
            "vod_pic": self._pic(d, i),
            "vod_remarks": item["remarks"],
        }

    def _ep(self, title, url):
        t = re.sub(r"[\r\n\t]+", " ", str(title)).replace("#", "＃").replace("$", "￥").strip()
        return t + "$" + self._b64e(str(url))

    def _join(self, v):
        if isinstance(v, (list, tuple)):
            return " / ".join(str(x) for x in v if x)
        return str(v or "")

    def _list_from_inlist(self, x):
        if not x:
            return []
        if isinstance(x, list):
            out = []
            for block in x:
                out += self._list_from_inlist(block)
            return out
        if not isinstance(x, dict):
            return []
        ts = x.get("t") or x.get("title") or []
        ids = x.get("i") or x.get("id") or []
        gs = x.get("g") or x.get("status") or []
        qs = x.get("q") or []
        ty = str(x.get("ty") or x.get("dir") or "mv")
        years = x.get("a") or []
        arr = []
        for n, name in enumerate(ts):
            if isinstance(name, dict):
                v = name
                arr.append(self._vod(v.get("title") or v.get("name"), v.get("id"),
                                     v.get("dir") or ty, v.get("status") or v.get("year"), v))
                continue
            i = ids[n] if n < len(ids) else ""
            r = gs[n] if n < len(gs) else ""
            q = ""
            if n < len(qs):
                q = " ".join(str(t) for t in qs[n]) if isinstance(qs[n], (list, tuple)) else str(qs[n])
            extra = None
            if n < len(years) and isinstance(years[n], (list, tuple)) and years[n]:
                extra = {"year": years[n][0]}
            arr.append(self._vod(name, i, ty, ("%s %s" % (r, q)).strip(), extra))
        return arr

    def _list_from_search(self, x):
        if not x or not isinstance(x, dict):
            return []
        l = x.get("l") or x
        if not isinstance(l, dict):
            return []
        titles = l.get("title") or l.get("t") or []
        ids = l.get("i") or l.get("id") or []
        ds = l.get("d") or l.get("dir") or []
        years = l.get("year") or []
        arr = []
        for n in range(len(titles)):
            arr.append(self._vod(
                titles[n],
                ids[n] if n < len(ids) else "",
                ds[n] if n < len(ds) else "mv",
                str(years[n]) if n < len(years) else "",
            ))
        return arr

    def _from_change(self, tid, page=1):
        try:
            page = max(1, int(page))
        except Exception:
            page = 1
        return self._list_from_inlist(self._json_get("/res/change/%s/%d" % (tid, page),
                                                     self.host + "/" + str(tid)))

    def _suggest_search(self, key):
        d = self._json_get("/res/search_suggest?q=" + quote(key))
        if not isinstance(d, list):
            return []
        out, seen = [], set()
        for v in d:
            if not isinstance(v, dict):
                continue
            dr = str(v.get("dir") or "mv")
            k = dr + str(v.get("id"))
            if k in seen:
                continue
            seen.add(k)
            out.append(self._vod(v.get("title"), v.get("id"), dr, v.get("year"), v))
        return out

    def _suggest_items(self, tid=""):
        kws = {"mv": ["2025", "电影", "最新电影", "人生"],
               "tv": ["剧集", "2025", "黑袍", "庆余年"],
               "ac": ["动漫", "星辰变", "斗罗", "瑞克"],
               "": ["2025", "星辰变", "黑袍", "人生"]}.get(str(tid), [str(tid)])
        arr, seen = [], set()
        for kw in kws:
            d = self._json_get("/res/search_suggest?q=" + quote(kw))
            if not isinstance(d, list):
                continue
            for v in d:
                if not isinstance(v, dict):
                    continue
                dr = str(v.get("dir") or "mv")
                if tid and dr != str(tid):
                    continue
                key = dr + str(v.get("id") or "")
                if key in seen:
                    continue
                seen.add(key)
                arr.append(self._vod(v.get("title"), v.get("id"), dr, v.get("year"), v))
            if len(arr) >= 24:
                break
        return arr

    def _home_items(self):
        h = self._req("/")
        items = self._list_from_inlist(self._obj(h, "inlist"))
        if len(items) >= 6:
            return items[:24]
        bucket = [self._from_change(t, 1) for t in ("mv", "tv", "ac")]
        merged, seen = [], set()
        for v in items:
            if v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                merged.append(v)
        for n in range(8):
            for b in bucket:
                if n < len(b) and b[n]["vod_id"] not in seen:
                    seen.add(b[n]["vod_id"])
                    merged.append(b[n])
        return merged[:24]

    def homeContent(self, filter):
        return {
            "class": [{"type_id": k, "type_name": v} for k, v in self.classes.items()],
            "list": self._home_items(),
            "filters": {},
        }

    def homeVideoContent(self):
        return {"list": self._home_items()}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "")
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        res = {"page": page, "pagecount": 1, "limit": 30, "total": 0, "list": []}
        if tid not in self.classes:
            return res

        url = "/" + tid if page == 1 else "/%s?page=%d" % (tid, page)
        h = self._req(url)
        items = self._list_from_inlist(self._obj(h, "inlist"))

        pages = 0
        p = self._obj(h, "page")
        if isinstance(p, dict):
            try:
                pages = int(p.get("pages") or 0)
            except Exception:
                pages = 0

        if pages and page > pages:
            res["pagecount"] = pages
            res["total"] = pages * PAGE_SIZE
            return res

        if not items:
            items = self._from_change(tid, page)
        if not items and page == 1:
            items = self._suggest_items(tid)

        res["pagecount"] = pages or 100
        res["limit"] = len(items) or 30
        res["total"] = res["pagecount"] * PAGE_SIZE
        res["list"] = items
        return res

    def searchContent(self, key, quick, pg="1"):
        key = str(key or "").strip()
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        res = {"page": page, "pagecount": 1, "limit": 30, "total": 0, "list": []}
        if not key:
            return res
        url = "/search?q=" + quote(key) + (("&page=%d" % page) if page > 1 else "")
        h = self._req(url)
        items = self._list_from_search(self._obj(h, "search"))
        p = self._obj(h, "page")
        if isinstance(p, dict):
            try:
                res["pagecount"] = int(p.get("pages") or 0) or 1
            except Exception:
                res["pagecount"] = 1
        if not items:
            items = self._suggest_search(key)
        res["list"] = items
        res["total"] = len(items) if page <= 1 else res["pagecount"] * 25
        return res

    def _sources(self, down):
        pf, pu = [], []
        used = {}

        def uniq(name):
            name = str(name or "网盘").strip() or "网盘"
            n = used.get(name, 0) + 1
            used[name] = n
            return name if n == 1 else "%s %d" % (name, n)

        pan = down.get("panlist") or {}
        if isinstance(pan, dict) and pan.get("id"):
            groups = {}
            tnames = pan.get("tname") or []
            urls = pan.get("url") or []
            types = pan.get("type") or []
            names = pan.get("name") or []
            pwds = pan.get("p") or []
            for i, u in enumerate(urls):
                if not u:
                    continue
                u = str(u)
                tp = types[i] if i < len(types) else 0
                name = "网盘"
                try:
                    if 0 <= int(tp) < len(tnames):
                        name = str(tnames[int(tp)])
                except Exception:
                    pass
                if any(b in name for b in BLOCK_PAN):
                    continue
                if any(b in u.lower() for b in BLOCK_PAN_DOMAIN):
                    continue
                title = str(names[i]) if i < len(names) and names[i] else "网盘链接"
                pwd = str(pwds[i]) if i < len(pwds) and pwds[i] else ""
                if pwd and "pwd=" not in u:
                    u += ("&" if "?" in u else "?") + "pwd=" + pwd
                groups.setdefault(name, []).append(self._ep(title, u))
            for k, v in groups.items():
                pf.append(uniq(k))
                pu.append("#".join(v))
        return pf, pu

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        item = self._b64d(ids[0])
        if not isinstance(item, dict):
            return {"list": []}
        dr = str(item.get("dir") or "mv")
        vid = str(item.get("id") or "")
        if not vid:
            return {"list": []}

        detail_url = "/%s/%s" % (dr, vid)
        h = self._req(detail_url)
        d = self._obj(h, "d")
        if not isinstance(d, dict):
            d = {}
        down = self._json_get("/res/downurl/%s/%s" % (dr, vid), self.host + detail_url)
        if not isinstance(down, dict):
            down = {}

        pf, pu = self._sources(down)
        one = {
            "vod_id": ids[0],
            "vod_name": d.get("title") or item.get("title") or "",
            "vod_pic": self._pic(dr, vid),
            "vod_year": str(d.get("year") or item.get("year") or ""),
            "vod_area": self._join(d.get("diqu")),
            "vod_actor": self._join(d.get("zhuyan")),
            "vod_director": self._join(d.get("daoyan")),
            "vod_content": re.sub(r"<[^>]+>", "", str(d.get("summary") or "")),
            "vod_remarks": re.sub(r"<[^>]+>", "", str(d.get("status") or "")),
            "vod_play_from": "$$$".join(pf),
            "vod_play_url": "$$$".join(pu),
        }
        return {"list": [one]}

    def playerContent(self, flag, id, vipFlags):
        if not id or id == "noop":
            return {"parse": 0, "jx": 0, "url": ""}
        u = self._b64d(id)
        if isinstance(u, dict):
            u = u.get("url") or ""
        u = u if isinstance(u, str) else str(u or "")
        if not u:
            return {"parse": 0, "jx": 0, "url": ""}
        if u.startswith("push://"):
            return {"parse": 0, "jx": 0, "url": u}
        if u.startswith("http"):
            return {"parse": 0, "jx": 0, "url": "push://" + u, "header": self._phdr()}
        return {"parse": 0, "jx": 0, "url": u}