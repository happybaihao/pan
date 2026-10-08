# coding: utf-8
"""Python port of the BaoBaoBaShi Yeguo ForwardWidget 1.0.5."""

import base64
import hashlib
import inspect
import json
import math
import re
import time
from collections import OrderedDict
from urllib.parse import urlencode, urlsplit

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base.spider import Spider


SOURCE_URL = "https://fwd.uou.qzz.io/widgets/Yeguo_TuT.js"
SOURCE_VERSION = "1.0.5"
SOURCE_AUTHOR = "宝宝巴士"
VERSION = "1.0.0"


class Spider(Spider):
    backend_parse = False
    category_mode = False
    API_KEY = b"2acf7e91e9864673"
    API_IV = b"1c29882d3ddfcfd6"
    MEDIA_KEY = b"f5d965df75336270"
    MEDIA_IV = b"97b60394abc2fbe1"
    UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    PAGE_SIZE = 24
    CATEGORIES = (
        ("home", "首页推荐", {}),
        ("explore", "发现", {}),
        ("rank", "排行榜", {}),
        ("dushi", "都市", {"background": 40}),
        ("xiandai", "现代", {"background": 39}),
        ("xiaoyuan", "校园", {"background": 47}),
        ("gudai", "古代", {"background": 41}),
        ("xiangcun", "乡村", {"background": 42}),
        ("zhichang", "职场", {"background": 44}),
        ("chongsheng", "重生", {"setting": 26}),
        ("chuanyue", "穿越", {"setting": 27}),
        ("xitong", "系统", {"setting": 28}),
        ("nixi", "逆袭", {"setting": 53}),
        ("mogai", "魔改", {"setting": 56}),
    )

    def getName(self):
        return "野果短剧"

    @staticmethod
    def _config(value):
        if isinstance(value, str):
            value = json.loads(value) if value.strip() else {}
        if not isinstance(value, dict):
            return {}
        config = dict(value)
        data = config.get("data")
        if isinstance(data, str):
            data = json.loads(data) if data.strip() else {}
        if isinstance(data, dict):
            config.update(data)
        return config

    def init(self, extend=""):
        config = self._config(extend)
        self._inherit_site_key()
        self.apiBase = str(config.get("apiBase") or "https://www.yeguodj.com/api.php").rstrip("/")
        self.coverProxy = str(config.get("coverProxy") or "").rstrip("/")
        self.coverToken = str(config.get("coverToken") or "")
        self.timeout = float(config.get("timeout") or 20)
        old_session = getattr(self, "_session", None)
        if old_session is not None:
            old_session.close()
        self._session = requests.Session()
        self._details = OrderedDict()
        self._images = OrderedDict()
        self._image_cache = OrderedDict()

    def _inherit_site_key(self):
        if getattr(self, "siteKey", ""):
            return
        # Atvp creates the inner Spider without copying its runtime routing key.
        frame = inspect.currentframe()
        try:
            frame = frame.f_back
            for unused in range(8):
                if frame is None:
                    break
                owner = frame.f_locals.get("self")
                if owner is not None and owner is not self:
                    owns_inner = any(
                        getattr(owner, name, None) is self
                        for name in ("_inner", "inner", "spider")
                    )
                    key = getattr(owner, "siteKey", "")
                    if owns_inner and key:
                        self.siteKey = key
                        return
                frame = frame.f_back
        finally:
            del frame

    def _headers(self):
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": self.UA,
            "Referer": "https://yeguodj.com/",
            "Origin": "https://yeguodj.com",
        }

    @staticmethod
    def _text(value):
        return str(value if value is not None else "").strip()

    @staticmethod
    def _number(value):
        text = str(value)
        return int(text) if re.fullmatch(r"-?\d+", text) else value

    @staticmethod
    def _page(value):
        try:
            return max(1, int(value))
        except (ValueError, TypeError):
            return 1

    @staticmethod
    def _label(value):
        return str(value).replace("$", "＄").replace("#", "＃")

    @staticmethod
    def _unwrap(value):
        inner = value.get("data", value) if isinstance(value, dict) else value
        if isinstance(inner, dict) and isinstance(inner.get("data"), (dict, list)):
            return inner["data"]
        return inner

    def _decode_api(self, value):
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError("野果 API 响应格式异常")
        data = value.get("data")
        if isinstance(data, str) and len(data) > 20:
            cipher = base64.b64decode(data.replace("-", "+").replace("_", "/") + "=" * (-len(data) % 4))
            plain = unpad(AES.new(self.API_KEY, AES.MODE_CBC, self.API_IV).decrypt(cipher), 16)
            value = dict(value)
            value["data"] = json.loads(plain.decode("utf-8"))
        if str(value.get("code", "200")) not in ("0", "1", "200"):
            raise ValueError("野果 API 返回错误状态")
        return value

    def _api(self, path, body=None):
        url = self.apiBase + path
        payload = body or {}
        try:
            response = self._session.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            response = self._session.get(url, params=payload, headers=self._headers(), timeout=self.timeout)
            response.raise_for_status()
        return self._decode_api(response.json())

    def homeContent(self, filter):
        result = {"class": [{"type_id": key, "type_name": title} for key, title, unused in self.CATEGORIES]}
        if filter:
            filters = []
            for dimension, title in (("background", "背景"), ("setting", "设定")):
                values = [{"n": "全部", "v": ""}]
                values.extend(
                    {"n": name, "v": str(body[dimension])}
                    for unused, name, body in self.CATEGORIES if dimension in body
                )
                filters.append({"key": dimension, "name": title, "value": values})
            result["filters"] = {"explore": filters}
        return result

    def homeVideoContent(self):
        return {"list": self.categoryContent("home", "1", False, {})["list"]}

    def _cover(self, url):
        url = self._text(url)
        if not url or url.startswith("data:image/"):
            return url
        if url.startswith("//"):
            url = "https:" + url
        if urlsplit(url).scheme not in ("http", "https"):
            return ""
        if self.coverProxy:
            query = {"url": url}
            if self.coverToken:
                query["token"] = self.coverToken
            return self.coverProxy + "/?" + urlencode(query)
        key = self._text(getattr(self, "siteKey", ""))
        if not key:
            raise ValueError("封面代理缺少运行时 siteKey")
        token = hashlib.sha256(url.encode("utf-8")).hexdigest()
        self._images[token] = url
        self._images.move_to_end(token)
        if len(self._images) > 512:
            self._images.popitem(last=False)
        base = self.getProxyUrl()
        separator = "&" if "?" in base else "?"
        return base + separator + urlencode({"siteKey": key, "img": token})

    def _card(self, item):
        if not isinstance(item, dict):
            return None
        video_id = self._text(item.get("video_id", item.get("id")))
        if not video_id:
            return None
        count = item.get("episode_count") or item.get("episodes") or item.get("total_serial") or ""
        remark = self._text(item.get("update_status") or item.get("serialize_status_text"))
        if not remark and count:
            remark = "更新至%s集" % count
        return {
            "vod_id": "yeguo:" + video_id,
            "vod_name": self._text(item.get("title") or item.get("video_title") or item.get("name")) or video_id,
            "vod_pic": self._cover(item.get("cover") or item.get("cover_img") or item.get("pic")),
            "vod_remarks": remark,
        }

    def _cards(self, rows, deduplicate=False):
        cards, seen = [], set()
        for row in rows:
            card = self._card(row)
            if card and (not deduplicate or card["vod_id"] not in seen):
                cards.append(card)
                seen.add(card["vod_id"])
        return cards

    def _list_result(self, payload, page, home=False):
        inner = self._unwrap(payload)
        if not isinstance(inner, (dict, list)):
            raise ValueError("野果列表响应格式异常")
        rows = inner if isinstance(inner, list) else (inner.get("list") or inner.get("top_list") or [])
        if home:
            rows = list(inner.get("top_list") or [])
            for module in (inner.get("modules") or {}).get("list", []):
                if isinstance(module.get("list"), list):
                    rows.extend(module["list"])
                elif module.get("video_id"):
                    rows.append(module)
        cards = self._cards(rows, deduplicate=home)
        total = None
        if isinstance(inner, dict):
            for key in ("total", "total_count", "count"):
                if isinstance(inner.get(key), (int, str)) and str(inner[key]).isdigit():
                    total = int(inner[key])
                    break
        if total is None:
            has_next = bool(cards) if home else len(rows) >= self.PAGE_SIZE
            pagecount = page + int(has_next)
            total = (page - 1) * self.PAGE_SIZE + len(rows) + int(has_next)
        else:
            pagecount = max(1, int(math.ceil(float(total) / self.PAGE_SIZE)))
        return {"list": cards, "page": page, "pagecount": pagecount, "limit": self.PAGE_SIZE, "total": total}

    def categoryContent(self, tid, pg, filter, extend):
        page = self._page(pg)
        category = next((item for item in self.CATEGORIES if item[0] == str(tid)), None)
        if category is None:
            raise ValueError("未知野果分类")
        if tid == "home" and page == 1:
            return self._list_result(self._api("/api/home/homePage", {}), page, home=True)
        body = {"page": page, "limit": self.PAGE_SIZE}
        body.update(category[2])
        if tid == "explore":
            config = self._config(extend)
            for key in ("background", "setting"):
                if self._text(config.get(key)):
                    body[key] = self._number(config[key])
        path = "/api/theater/videoRank" if tid == "rank" else "/api/theater/exploreList"
        return self._list_result(self._api(path, body), page)

    def searchContent(self, key, quick, pg="1"):
        page = self._page(pg)
        keyword = self._text(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": 1, "limit": self.PAGE_SIZE, "total": 0}
        payload = self._api("/api/search/result", {"keyword": keyword, "page": page})
        return self._list_result(payload, page)

    def _parse_id(self, value):
        text = self._text(value)
        if text.startswith("atvp_detail:"):
            text = text[len("atvp_detail:"):]
        for prefix in ("yeguodj:", "yeguo:"):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        parts = (text.split(":") + ["", ""])[:3]
        if not parts[0]:
            raise ValueError("缺少野果剧集 ID")
        return parts

    def _detail(self, video_id):
        cached = self._details.get(video_id)
        if cached and time.time() - cached[0] < 180:
            return cached[1]
        info = self._unwrap(self._api("/api/playlet/detail", {"video_id": self._number(video_id)}))
        if not isinstance(info, dict):
            raise ValueError("野果详情响应格式异常")
        if info.get("video_id") is None and isinstance(info.get("data"), dict):
            info = info["data"]
        self._details[video_id] = (time.time(), info)
        if len(self._details) > 64:
            self._details.popitem(last=False)
        return info

    def detailContent(self, ids):
        video_id, unused, unused_id = self._parse_id(ids[0] if isinstance(ids, list) else ids)
        info = self._detail(video_id)
        episodes = info.get("episodes") if isinstance(info.get("episodes"), list) else []
        entries = []
        for index, episode in enumerate(episodes):
            number = episode.get("sort") or episode.get("episode") or index + 1
            episode_id = self._text(episode.get("id") or episode.get("episode_id"))
            target = "yeguo:%s:%s%s" % (video_id, number, ":" + episode_id if episode_id else "")
            label = self._label(self._text(episode.get("title")) or "第%s集" % number)
            entries.append(label + "$" + target)
        if not entries:
            entries = ["第1集$yeguo:%s:1" % video_id]
        return {"list": [{
            "vod_id": "yeguo:" + video_id,
            "vod_name": self._text(info.get("title")) or video_id,
            "vod_pic": self._cover(info.get("cover") or info.get("cover_img")),
            "vod_content": self._text(info.get("description") or info.get("intro")),
            "vod_play_from": "野果",
            "vod_play_url": "#".join(entries),
        }]}

    def playerContent(self, flag, id, vipFlags):
        result = {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": self._headers()}
        try:
            video_id, number, episode_id = self._parse_id(id)
            number = number or "1"
            if not episode_id:
                episodes = self._detail(video_id).get("episodes") or []
                selected = next((
                    episode for index, episode in enumerate(episodes)
                    if number in (str(episode.get("sort")), str(episode.get("episode")), str(index + 1))
                ), episodes[0] if episodes else {})
                episode_id = self._text(selected.get("id") or selected.get("episode_id"))
            body = {"video_id": self._number(video_id)}
            body["episode_id" if episode_id else "ep"] = self._number(episode_id or number)
            info = self._unwrap(self._api("/api/playlet/play", body))
            if not isinstance(info, dict):
                raise ValueError("野果播放响应格式异常")
            if info.get("video_url") is None and isinstance(info.get("data"), dict):
                info = info["data"]
            url = self._text(info.get("video_url") or info.get("video_url_h265"))
            if not url:
                for episode in info.get("episodeAll") or []:
                    if (episode_id and str(episode.get("id")) == episode_id) or str(episode.get("sort") or episode.get("index")) == number:
                        url = self._text(episode.get("video_url"))
                        break
            if not url:
                raise ValueError("无播放地址，可能需要 App 或金币解锁")
            result["url"] = url
        except (ValueError, KeyError, TypeError, requests.RequestException):
            result.update({"msg": "野果播放解析失败，接口不可用或当前分集需要解锁", "error": "playback_unavailable"})
        return result

    @staticmethod
    def _image_mime(data):
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        return ""

    def _decode_cover(self, data):
        if self._image_mime(data):
            return data
        if data.startswith(b"data:image/"):
            data = base64.b64decode(data.split(b",", 1)[1], validate=True)
            if self._image_mime(data):
                return data
        try:
            compact = b"".join(data.split())
            decoded = base64.b64decode(compact, validate=True)
            if decoded:
                data = decoded
        except (ValueError, base64.binascii.Error):
            pass
        if self._image_mime(data):
            return data
        plain = unpad(AES.new(self.MEDIA_KEY, AES.MODE_CBC, self.MEDIA_IV).decrypt(data), 16)
        if not self._image_mime(plain):
            raise ValueError("封面解密结果不是图片")
        return plain

    def localProxy(self, param):
        token = self._text(param.get("img"))
        url = self._images.get(token)
        if not url:
            return [404, "text/plain; charset=utf-8", "封面不存在或已过期"]
        cached = self._image_cache.get(token)
        if cached and time.time() - cached[0] < 300:
            return [200, cached[1], cached[2]]
        try:
            headers = self._headers()
            headers["Accept"] = "image/*,*/*;q=0.8"
            response = self._session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            data = self._decode_cover(response.content)
            mime = self._image_mime(data)
            self._image_cache[token] = (time.time(), mime, data)
            if len(self._image_cache) > 64:
                self._image_cache.popitem(last=False)
            return [200, mime, data]
        except (ValueError, requests.RequestException):
            return [502, "text/plain; charset=utf-8", "野果封面获取或解密失败"]

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|mkv|flv|webm)(?:[?#]|$)", str(url), re.I))

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return []

    def destroy(self):
        session = getattr(self, "_session", None)
        if session is not None:
            session.close()
