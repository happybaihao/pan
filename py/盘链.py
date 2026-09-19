# -*- coding: utf-8 -*-
import sys, requests, base64, json, time, re, threading, datetime
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append('..')
from base.spider import Spider as BaseSpider

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.site = "https://pinglian.lol"
        self.ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0.0.0 Safari/537.36")

        # ======== 已为你预置账号、密码和CK，无需再填 ========
        self.username = ""
        self.password = ""
        self.cookie = ("")
        # ====================================================

        self._logged_in = False
        self._login_lock = threading.Lock()
        self._today_checkin_status = None  # None=未知，True=已签，False=未签

        self.channels = {
            "0": "全部", "movie": "电影", "drama": "电视剧",
            "variety": "综艺", "anime": "动漫",
        }
        self.pan_order = ["quark", "uc", "baidu", "xunlei", "123",
                          "tianyi", "115", "aliyun", "guangya", "mobile"]
        self.pan_names = {
            "quark": "夸克", "uc": "UC", "baidu": "百度", "xunlei": "迅雷",
            "123": "123盘", "tianyi": "天翼", "115": "115", "aliyun": "阿里",
            "guangya": "光鸭", "mobile": "移动", "others": "其他",
        }

        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": self.ua,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    # ================================================================== #
    # 基础信息 & 初始化
    # ================================================================== #
    def getName(self):
        return "盘链"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def init(self, extend=""):
        if extend:
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict):
                    self.username = cfg.get("username", self.username)
                    self.password = cfg.get("password", self.password)
                    self.cookie = cfg.get("cookie", self.cookie)
            except Exception:
                pass

        if self.cookie:
            self.session.headers.update({"Cookie": self.cookie})
            if not self._check_cookie_valid():
                print("[盘链] Cookie失效，尝试使用账号密码重新登录...")
                self._logged_in = False
                if self.username and self.password:
                    self._login()
            else:
                self._logged_in = True
                print("[盘链] Cookie有效")
        elif self.username and self.password:
            self._login()

        # 登录成功后自动执行签到
        if self._logged_in:
            self._daily_checkin()

        return self

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    # ================================================================== #
    # 自动签到模块
    # ================================================================== #
    def _parse_checkin_status(self, data):
        """从任务接口响应中递归解析今日签到状态，返回 True/False/None"""
        status_keys = ["checked_in", "signed", "today_checked", "is_signed",
                       "checkin_status", "status", "signed_today"]

        def _search(obj, depth=0):
            if depth > 3:
                return None
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key.lower() in status_keys:
                        if isinstance(value, bool):
                            return value
                        if isinstance(value, int):
                            return bool(value)
                        if isinstance(value, str):
                            v_low = value.lower()
                            if v_low in ("true", "1", "yes", "signed", "checked", "已完成", "已签到"):
                                return True
                            if v_low in ("false", "0", "no", "unsigned", "unchecked", "未完成", "未签到"):
                                return False
                    result = _search(value, depth + 1)
                    if result is not None:
                        return result
            elif isinstance(obj, list):
                for item in obj:
                    result = _search(item, depth + 1)
                    if result is not None:
                        return result
            return None

        return _search(data)

    def _daily_checkin(self):
        """先查询任务状态，未签到则自动签到（防重复机制）"""
        if self._today_checkin_status is not None:
            if self._today_checkin_status:
                print("[盘链] 今日已签到，跳过。")
            return

        # 1) 查询任务状态
        try:
            resp = self.session.get(
                self.site + "/api/tasks",
                headers={"Referer": self.site + "/tasks", "Origin": self.site},
                timeout=10,
            )
            tasks_data = resp.json()
            checked = self._parse_checkin_status(tasks_data)
            if checked is True:
                print("[盘链] 查询到今日已签到，跳过。")
                self._today_checkin_status = True
                return
            elif checked is False:
                print("[盘链] 查询到今日未签到，准备自动签到...")
            else:
                print("[盘链] 无法解析签到状态，尝试直接签到...")
        except Exception as e:
            print(f"[盘链] 查询任务状态异常: {e}，尝试直接签到...")

        # 2) 执行签到
        try:
            resp = self.session.post(
                self.site + "/api/tasks/checkin",
                json={},
                headers={
                    "Content-Type": "application/json",
                    "Referer": self.site + "/tasks",
                    "Origin": self.site,
                    "Accept": "*/*",
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("success"):
                msg = data.get("message") or data.get("msg") or "签到成功"
                print(f"[盘链] 签到成功: {msg}")
                self._today_checkin_status = True
            else:
                msg = data.get("message") or data.get("msg") or ""
                if re.search(r"已签到|已经签到|重复|今天已", msg, re.I):
                    print(f"[盘链] 今日已签到（{msg}），跳过。")
                    self._today_checkin_status = True
                else:
                    print(f"[盘链] 签到失败: {msg}")
                    self._today_checkin_status = False
        except Exception as e:
            print(f"[盘链] 签到异常: {e}")
            self._today_checkin_status = False

    # ================================================================== #
    # 编码 / 转义工具
    # ================================================================== #
    def _b64e(self, obj):
        text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")

    def _b64d(self, s):
        try:
            padded = str(s) + "=" * (-len(str(s)) % 4)
            text = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            try:
                return json.loads(text)
            except Exception:
                return text
        except Exception:
            return s

    def _safe(self, t):
        return str(t or "").replace("#", "＃").replace("$", "￥")

    # ================================================================== #
    # 登录相关
    # ================================================================== #
    def _check_cookie_valid(self):
        try:
            r = self.session.get(
                self.site + "/api/videos",
                params={"page": 1, "page_size": 1},
                timeout=10,
            )
            data = r.json()
            return r.status_code == 200 and data.get("success") is not False
        except Exception:
            return False

    def _login(self):
        with self._login_lock:
            if self._logged_in:
                return True
            try:
                print(f"[盘链] 正在登录账号: {self.username}")
                r = self.session.post(
                    self.site + "/api/auth/login",
                    data={"username": self.username, "password": self.password, "remember": "1"},
                    headers={
                        "Referer": self.site + "/login",
                        "Origin": self.site,
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    },
                    timeout=15,
                )
                d = r.json()
                if d.get("success"):
                    self._logged_in = True
                    new_cookie = self.session.cookies.get_dict()
                    if new_cookie:
                        cookie_str = "; ".join([f"{k}={v}" for k, v in new_cookie.items()])
                        self.session.headers.update({"Cookie": cookie_str})
                    print("[盘链] 登录成功")
                    return True
                else:
                    print(f"[盘链] 登录失败: {d.get('message', '未知错误')}")
            except Exception as e:
                print(f"[盘链] 登录异常: {e}")
            return False

    def _ensure_login(self):
        if self._logged_in:
            return True
        if self.username and self.password:
            return self._login()
        return False

    def _need_login(self, payload):
        if not isinstance(payload, dict):
            return False
        if payload.get("success") is False:
            msg = str(payload.get("message", "") or payload.get("msg", ""))
            if re.search(r"登录|登陆|未授权|无权限|签到|unauthor|non-?login", msg, re.I):
                return True
        code = payload.get("code")
        if code in (-1, 401, 403):
            return True
        return False

    def _unwrap(self, payload):
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            return payload["data"]
        return payload

    # ================================================================== #
    # 请求封装
    # ================================================================== #
    def _req_json(self, path, params=None, referer=None, retry_login=True):
        self._ensure_login()
        if referer is None:
            referer = self.site + "/videos"
        headers = {"Referer": referer, "Origin": self.site}
        try:
            r = self.session.get(self.site + path, params=params or {}, headers=headers, timeout=15)
            d = r.json()
            if retry_login and self._need_login(d):
                print(f"[盘链] 接口提示需要登录: {path}")
                self._logged_in = False
                if "Cookie" in self.session.headers:
                    del self.session.headers["Cookie"]
                if self._ensure_login():
                    return self._req_json(path, params, referer, False)
            return d
        except Exception as e:
            print(f"[盘链] GET请求异常 {path}: {e}")
            return {}

    def _req_json_post(self, path, body=None, referer=None, retry_login=True):
        self._ensure_login()
        if referer is None:
            referer = self.site + "/videos"
        headers = {"Referer": referer, "Origin": self.site, "Content-Type": "application/json"}
        try:
            r = self.session.post(self.site + path, json=body or {}, headers=headers, timeout=15)
            d = r.json()
            if retry_login and self._need_login(d):
                self._logged_in = False
                if "Cookie" in self.session.headers:
                    del self.session.headers["Cookie"]
                if self._ensure_login():
                    return self._req_json_post(path, body, referer, False)
            return d
        except Exception as e:
            print(f"[盘链] POST请求异常 {path}: {e}")
            return {}

    # ================================================================== #
    # 数据规范化 & 抓取
    # ================================================================== #
    def _normalize_video(self, x):
        x = x or {}
        return {
            "vod_id": str(x.get("id", "") or ""),
            "vod_name": str(x.get("title", "") or ""),
            "vod_pic": str(x.get("cover", "") or ""),
            "vod_remarks": str(x.get("remarks", "") or ""),
            "vod_score": str(x.get("score", "") or ""),
            "vod_year": str(x.get("year", "") or ""),
            "vod_area": str(x.get("area", "") or ""),
            "vod_lang": str(x.get("lang", "") or ""),
            "vod_actor": str(x.get("actor", "") or ""),
            "vod_director": str(x.get("director", "") or ""),
            "vod_content": str(x.get("intro", "") or ""),
            "type_name": str(x.get("type_name", "") or ""),
            "play_from": str(x.get("play_from", "") or ""),
            "play_url": str(x.get("play_url", "") or ""),
        }

    def _fetch_videos(self, page=1, type_id="", keyword="", year="", area="", lang=""):
        params = {"page": str(page or 1), "page_size": "30", "sort": "year_desc"}
        if keyword:
            params["search"] = keyword
        if type_id and type_id != "0":
            if type_id in ("movie", "drama", "variety", "anime"):
                params["group"] = type_id
            else:
                params["type"] = type_id
        if year:
            params["year"] = str(year)
        if area:
            params["area"] = str(area)
        if lang:
            params["lang"] = str(lang)

        payload = self._req_json("/api/videos", params)
        data = self._unwrap(payload) or {}
        lst = data.get("list") or []
        total = int(data.get("total") or 0)
        page_size = int(data.get("page_size") or 30)
        return {
            "list": [self._normalize_video(x) for x in lst],
            "page": int(data.get("page") or page or 1),
            "pagecount": max(1, (total + page_size - 1) // page_size) if total else 1,
            "total": total,
        }

    def _fetch_detail(self, video_id):
        path = "/api/videos/" + quote(str(video_id), safe="")
        payload = self._req_json(path)
        data = self._unwrap(payload) or {}
        return {
            "video": self._normalize_video(data.get("video") or {}),
            "links": data.get("links") or [],
        }

    # ================================================================== #
    # 网盘链接解析：ticket → link-open → 真实网盘 URL
    # ================================================================== #
    def _resolve_pan_link(self, link_id):
        """把 link_id 换成真实网盘 URL（形如 https://pan.quark.cn/s/xxx?pwd=yyy）"""
        try:
            try:
                link_id_int = int(link_id)
            except (ValueError, TypeError):
                link_id_int = link_id

            ticket_resp = self._req_json_post("/api/videos/link-ticket", {"link_id": link_id_int})
            ticket_data = self._unwrap(ticket_resp) or {}
            ticket = ticket_data.get("ticket")
            if not ticket:
                msg = ""
                if isinstance(ticket_resp, dict):
                    msg = ticket_resp.get("message") or ticket_resp.get("msg") or ""
                print(f"[盘链] link_id={link_id} 获取ticket失败: {msg or ticket_resp}")
                return ""

            data_resp = self._req_json(
                "/api/videos/link-open/" + quote(str(link_id), safe=""),
                {"t": ticket},
            )
            data = self._unwrap(data_resp) or {}
            url = str(data.get("url") or "")
            if not url:
                msg = ""
                if isinstance(data_resp, dict):
                    msg = data_resp.get("message") or data_resp.get("msg") or ""
                print(f"[盘链] link_id={link_id} 获取URL失败: {msg or data_resp}")
                return ""

            print(f"[盘链] link_id={link_id} -> {url}")
            return url
        except Exception as e:
            print(f"[盘链] 解析异常 link_id={link_id}: {e}")
        return ""

    def _fetch_online_play_url(self, vod_id):
        """抓取页面里的在线播放地址（m3u8 等）"""
        try:
            r = self.session.get(
                self.site + "/pages/video.php?id=" + quote(str(vod_id), safe=""),
                headers={"Referer": self.site + "/videos"},
                timeout=15,
            )
            html = r.text
            m = re.search(r'vodPlayUrl\s*:\s*"((?:[^"\\]|\\.)*)"', html)
            if not m:
                m = re.search(r'(https?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)', html)
            if not m:
                return ""
            decoded = m.group(1)
            decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda g: chr(int(g.group(1), 16)), decoded)
            decoded = decoded.replace("\\/", "/").replace('\\"', '"').replace("\\\\", "\\")
            if not re.search(r"\$https?://", decoded) and ".m3u8" not in decoded:
                return ""
            return decoded
        except Exception:
            return ""

    # ================================================================== #
    # 首页 / 分类 / 搜索
    # ================================================================== #
    def homeContent(self, filter):
        classes = [{"type_name": name, "type_id": tid} for tid, name in self.channels.items()]
        filters = {}
        year_opts = [{"n": "全部", "v": ""}]
        area_opts = [{"n": "全部", "v": ""}]
        lang_opts = [{"n": "全部", "v": ""}]
        try:
            data = self._unwrap(self._req_json("/api/videos/filters")) or {}
            for v in (data.get("years") or []):
                year_opts.append({"n": str(v), "v": str(v)})
            for v in (data.get("areas") or []):
                area_opts.append({"n": str(v), "v": str(v)})
            for v in (data.get("langs") or []):
                lang_opts.append({"n": str(v), "v": str(v)})
        except Exception:
            pass
        for tid in self.channels:
            filters[tid] = [
                {"key": "year", "name": "年份", "init": "", "value": year_opts},
                {"key": "area", "name": "地区", "init": "", "value": area_opts},
                {"key": "lang", "name": "语言", "init": "", "value": lang_opts},
            ]
        return {"class": classes, "list": [], "filters": filters}

    def homeVideoContent(self):
        try:
            r = self._fetch_videos(page=1, type_id="0")
        except Exception:
            r = {"list": []}
        return {
            "list": [
                {
                    "vod_id": x["vod_id"],
                    "vod_name": x["vod_name"],
                    "vod_pic": x["vod_pic"],
                    "vod_remarks": x["vod_remarks"] or x.get("type_name", ""),
                }
                for x in r["list"][:12]
            ]
        }

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if str(pg).isdigit() else 1
        except Exception:
            page = 1
        ext = extend or {}
        try:
            r = self._fetch_videos(
                page=page, type_id=str(tid),
                year=str(ext.get("year", "") or ""),
                area=str(ext.get("area", "") or ""),
                lang=str(ext.get("lang", "") or ""),
            )
            return {
                "list": [
                    {
                        "vod_id": x["vod_id"],
                        "vod_name": x["vod_name"],
                        "vod_pic": x["vod_pic"],
                        "vod_remarks": x["vod_remarks"] or x.get("type_name", ""),
                    }
                    for x in r["list"]
                ],
                "page": r["page"],
                "pagecount": r["pagecount"],
                "limit": 30,
                "total": r["total"],
            }
        except Exception:
            return {"list": [], "page": page, "pagecount": 0, "limit": 30, "total": 0}

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if str(pg).isdigit() else 1
        except Exception:
            page = 1
        if not key:
            return {"list": [], "page": page, "pagecount": 0, "limit": 30, "total": 0}
        try:
            r = self._fetch_videos(page=page, keyword=key)
            return {
                "list": [
                    {
                        "vod_id": x["vod_id"],
                        "vod_name": x["vod_name"],
                        "vod_pic": x["vod_pic"],
                        "vod_remarks": x["vod_remarks"] or x.get("type_name", ""),
                    }
                    for x in r["list"]
                ],
                "page": r["page"],
                "pagecount": r["pagecount"],
                "limit": 30,
                "total": r["total"],
            }
        except Exception:
            return {"list": [], "page": page, "pagecount": 0, "limit": 30, "total": 0}

    # ================================================================== #
    # 详情页：并发预解析网盘链接
    # ================================================================== #
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) and ids else (ids if isinstance(ids, str) else "")
        if not vid:
            return {"list": []}

        try:
            detail = self._fetch_detail(vid)
        except Exception:
            return {"list": []}

        video = detail.get("video") or {}
        links = detail.get("links") or []

        play_froms = []
        play_urls = []

        # 1) 在线播放线路
        online = self._fetch_online_play_url(vid)
        if online:
            play_froms.append("⚡️在线播放")
            play_urls.append(online)

        # 2) 网盘线路（并发预解析）
        if links:
            groups = {}
            for link in links:
                key = str(link.get("pan_type") or "others")
                groups.setdefault(key, []).append(link)

            ordered = [k for k in self.pan_order if k in groups] + \
                      [k for k in groups if k not in self.pan_order]
            flat = [(k, link) for k in ordered for link in groups[k]]

            def _resolve_one(item):
                key, link = item
                lid = str(link.get("id") or "")
                if not lid:
                    return key, link, ""
                return key, link, self._resolve_pan_link(lid)

            resolved = []
            if flat:
                try:
                    with ThreadPoolExecutor(max_workers=5) as ex:
                        futures = [ex.submit(_resolve_one, it) for it in flat]
                        for fut in as_completed(futures):
                            try:
                                resolved.append(fut.result())
                            except Exception as e:
                                print(f"[盘链] 并发解析单项异常: {e}")
                except Exception as e:
                    print(f"[盘链] 并发解析异常: {e}")
                    resolved = [_resolve_one(it) for it in flat]

            platform_eps = {}
            for key, link, url in resolved:
                if not url:
                    continue
                title = self._safe(str(link.get("title") or (self.pan_names.get(key, key) + "资源")))
                pwd = str(link.get("password") or "")
                if pwd:
                    title += "（提取码:" + pwd + "）"
                encoded = self._b64e(url)
                platform_eps.setdefault(key, []).append(title + "$" + encoded)

            for key in ordered:
                eps = platform_eps.get(key) or []
                if eps:
                    play_froms.append(self.pan_names.get(key, key))
                    play_urls.append("#".join(eps))

        if not play_froms:
            play_froms = ["提示"]
            play_urls = ["未找到可用资源，请检查账号登录状态或积分$noop"]

        return {
            "list": [{
                "vod_id": vid,
                "vod_name": video.get("vod_name", ""),
                "vod_pic": video.get("vod_pic", ""),
                "vod_year": video.get("vod_year", ""),
                "vod_area": video.get("vod_area", ""),
                "vod_actor": video.get("vod_actor", ""),
                "vod_director": video.get("vod_director", ""),
                "vod_content": video.get("vod_content", ""),
                "vod_remarks": video.get("vod_remarks", ""),
                "vod_play_from": "$$$".join(play_froms),
                "vod_play_url": "$$$".join(play_urls),
            }]
        }

    # ================================================================== #
    # 播放：交给 APP 用本地网盘 CK 处理 push://
    # ================================================================== #
    def _resolve_go_url(self, url):
        try:
            r = self.session.get(url, timeout=12, allow_redirects=True)
            m = re.search(
                r"https?://(?:pan\.quark\.cn|drive\.uc\.cn|pan\.baidu\.com|"
                r"www\.aliyundrive\.com|www\.alipan\.com|alipan\.com|"
                r"cloud\.189\.cn|www\.123pan\.com|123pan\.com|"
                r"pan\.xunlei\.com|115\.com)[^\s\"'<>]+",
                r.text,
            )
            if m:
                return m.group(0).replace("&amp;", "&")
        except Exception:
            pass
        return url

    def _wrap_pan_url(self, url):
        if not url or not isinstance(url, str):
            return {"parse": 0, "jx": 0, "url": "", "msg": "获取播放地址失败"}

        if url.startswith(("magnet:", "ed2k:", "thunder:")):
            return {"parse": 0, "jx": 0, "url": url}

        if url.startswith("push://"):
            return {
                "parse": 0, "jx": 0, "url": url,
                "header": {"User-Agent": self.ua, "Referer": self.site + "/"},
            }

        if url.startswith("http"):
            if ".m3u8" in url or ".mp4" in url:
                return {
                    "parse": 0, "jx": 0, "url": url,
                    "header": {"User-Agent": self.ua, "Referer": self.site + "/"},
                }
            return {
                "parse": 0, "jx": 0,
                "url": "push://" + url,
                "header": {"User-Agent": self.ua, "Referer": self.site + "/"},
            }

        return {"parse": 0, "jx": 0, "url": ""}

    def playerContent(self, flag, id, vipFlags):
        if not id or id == "noop":
            return {"parse": 0, "jx": 0, "url": "", "msg": "无效的播放地址"}

        s = str(id)

        if s.startswith(("magnet:", "ed2k:", "thunder:")):
            return {"parse": 0, "jx": 0, "url": s}

        if s.startswith("http://") or s.startswith("https://"):
            if "api/go.php" in s:
                resolved = self._resolve_go_url(s)
                if resolved and resolved != s:
                    return self._wrap_pan_url(resolved)
            return self._wrap_pan_url(s)

        if s.startswith("push://"):
            return {
                "parse": 0, "jx": 0, "url": s,
                "header": {"User-Agent": self.ua, "Referer": self.site + "/"},
            }

        raw = self._b64d(s)

        if isinstance(raw, str):
            if raw.startswith("plid://"):
                m = re.match(r"^plid://([^/]+)/(.+)$", raw)
                if m:
                    url = self._resolve_pan_link(m.group(2))
                    if url:
                        return self._wrap_pan_url(url)
                return {"parse": 0, "jx": 0, "url": "", "msg": "网盘链接解析失败"}

            if raw.startswith("push://"):
                return {
                    "parse": 0, "jx": 0, "url": raw,
                    "header": {"User-Agent": self.ua, "Referer": self.site + "/"},
                }

            if raw.startswith("http://") or raw.startswith("https://"):
                return self._wrap_pan_url(raw)

            if raw.startswith(("magnet:", "ed2k:", "thunder:")):
                return {"parse": 0, "jx": 0, "url": raw}

        return {"parse": 0, "jx": 0, "url": "", "msg": "无法识别的播放格式"}