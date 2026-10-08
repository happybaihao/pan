# coding: utf-8
"""Python port of the BaoBaoBaShi JingGuo ForwardWidget 1.1.0."""

import json
import math
import re
import time
import uuid
from collections import OrderedDict
from urllib.parse import quote

import requests
from base.spider import Spider


SOURCE_URL = "https://fwd.uou.qzz.io/widgets/JingGuo_TuT.js"
SOURCE_VERSION = "1.1.0"
SOURCE_AUTHOR = "宝宝巴士"
VERSION = "1.0.0"


class Spider(Spider):
    backend_parse = False
    category_mode = False
    UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    PAGE_SIZE = 24
    CATEGORIES = (
        ("heat", "热度", {"sort": "heat"}),
        ("latest", "最新", {"sort": "latest"}),
        ("landing", "首页推荐", {}),
        ("nav_all", "全部", {"navigationId": 2}),
        ("nav_original", "原创精品", {"navigationId": 7}),
        ("nav_single", "单体作品", {"navigationId": 3}),
        ("nav_anime", "动漫改编", {"navigationId": 6}),
        ("nav_movie", "影视改编", {"navigationId": 5}),
        ("len_multi", "多集", {"length": "multi"}),
        ("len_single", "单集", {"length": "single"}),
        ("tag_mogai", "魔改", {"_tagFilter": "魔改"}),
        ("tag_dushi", "都市", {"_tagFilter": "都市"}),
        ("tag_zhichang", "职场", {"_tagFilter": "职场"}),
        ("tag_qihuan", "奇幻", {"_tagFilter": "奇幻"}),
        ("tag_guzhuang", "古装", {"_tagFilter": "古装"}),
        ("tag_dongman", "动漫", {"_tagFilter": "动漫"}),
    )

    def getName(self):
        return "禁果短剧"

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
        self.apiBase = str(config.get("apiBase") or "https://jinguoduanju.app").rstrip("/")
        self.timeout = float(config.get("timeout") or 20)
        old_session = getattr(self, "_session", None)
        if old_session is not None:
            old_session.close()
        self._session = requests.Session()
        self._token = ""
        self._device_id = uuid.uuid4().hex
        self._cache = OrderedDict()

    def _headers(self, authenticated=False):
        headers = {
            "Accept": "application/json",
            "User-Agent": self.UA,
            "Referer": self.apiBase + "/",
            "Origin": self.apiBase,
        }
        if authenticated:
            headers["Authorization"] = "Bearer " + self._token
        return headers

    def _ensure_token(self):
        if self._token:
            return
        body = {"deviceId": "h5:" + self._device_id, "channelCode": "", "attributionToken": ""}
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        response = self._session.post(
            self.apiBase + "/api/v1/auth/device", json=body, headers=headers, timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        self._token = str(data.get("token") or "").strip()
        if not self._token:
            raise ValueError("禁果设备登录失败")

    def _api(self, path, query=None):
        for attempt in range(2):
            self._ensure_token()
            response = self._session.get(
                self.apiBase + "/api/v1" + path,
                params=query or {}, headers=self._headers(True), timeout=self.timeout,
            )
            if response.status_code == 401:
                self._token = ""
                if attempt == 0:
                    continue
                raise ValueError("禁果设备登录已失效")
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and str(data.get("status")) == "401":
                self._token = ""
                if attempt == 0:
                    continue
                raise ValueError("禁果设备登录已失效")
            if isinstance(data, dict) and data.get("status") and str(data["status"]) not in ("200", "0"):
                raise ValueError("禁果 API 返回错误状态")
            return data
        raise ValueError("禁果设备登录已失效")

    def _cached_api(self, path, query=None, ttl=300):
        key = (path, json.dumps(query or {}, sort_keys=True, ensure_ascii=True))
        cached = self._cache.get(key)
        if cached and time.time() - cached[0] < ttl:
            return cached[1]
        data = self._api(path, query)
        self._cache[key] = (time.time(), data)
        self._cache.move_to_end(key)
        if len(self._cache) > 64:
            self._cache.popitem(last=False)
        return data

    @staticmethod
    def _text(value):
        return str(value if value is not None else "").strip()

    @staticmethod
    def _page(value):
        try:
            return max(1, int(value))
        except (ValueError, TypeError):
            return 1

    @staticmethod
    def _label(value):
        return str(value).replace("$", "＄").replace("#", "＃")

    def _abs_url(self, value):
        url = self._text(value)
        if not url or re.match(r"^https?://", url, re.I):
            return url
        if url.startswith("//"):
            return "https:" + url
        return self.apiBase + ("" if url.startswith("/") else "/") + url

    def _card(self, item):
        if not isinstance(item, dict) or item.get("id") is None:
            return None
        video_id = self._text(item["id"])
        if not video_id:
            return None
        count = item.get("episodeCount")
        remark = "全%s集" % count if count else ""
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        if tags:
            remark += (" · " if remark else "") + " · ".join(str(tag) for tag in tags)
        return {
            "vod_id": "jgdj:" + video_id,
            "vod_name": self._text(item.get("title")) or video_id,
            "vod_pic": self._abs_url(item.get("coverUrl") or item.get("cover")),
            "vod_remarks": remark,
        }

    def _page_result(self, rows, page):
        total = len(rows)
        sliced = rows[(page - 1) * self.PAGE_SIZE:page * self.PAGE_SIZE]
        cards = [card for card in (self._card(row) for row in sliced) if card]
        return {
            "list": cards, "page": page, "pagecount": max(1, int(math.ceil(float(total) / self.PAGE_SIZE))),
            "limit": self.PAGE_SIZE, "total": total,
        }

    def homeContent(self, filter):
        result = {"class": [{"type_id": key, "type_name": title} for key, title, unused in self.CATEGORIES]}
        if filter:
            result["filters"] = {"nav_all": [
                {"key": "sort", "name": "排序", "value": [{"n": "最新", "v": "latest"}, {"n": "热度", "v": "heat"}]},
                {"key": "length", "name": "集数", "value": [{"n": "全部", "v": ""}, {"n": "多集", "v": "multi"}, {"n": "单集", "v": "single"}]},
                {"key": "_tagFilter", "name": "标签", "value": [{"n": "全部", "v": ""}] + [
                    {"n": title, "v": body["_tagFilter"]}
                    for unused, title, body in self.CATEGORIES if "_tagFilter" in body
                ]},
            ]}
        return result

    def homeVideoContent(self):
        return {"list": self.categoryContent("landing", "1", False, {})["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        page = self._page(pg)
        category = next((item for item in self.CATEGORIES if item[0] == str(tid)), None)
        if category is None:
            raise ValueError("未知禁果分类")
        if tid == "landing":
            data = self._cached_api("/landing")
            rows = data.get("dramas") or []
        else:
            query = {"sort": "latest"}
            query.update(category[2])
            config = self._config(extend)
            if tid == "nav_all":
                for name in ("sort", "length", "_tagFilter"):
                    if self._text(config.get(name)):
                        query[name] = config[name]
            tag_filter = query.pop("_tagFilter", "")
            rows = self._cached_api("/dramas", query)
            if not isinstance(rows, list):
                raise ValueError("禁果列表响应格式异常")
            if tag_filter:
                rows = [row for row in rows if isinstance(row.get("tags"), list) and tag_filter in row["tags"]]
        return self._page_result(rows, page)

    def searchContent(self, key, quick, pg="1"):
        page = self._page(pg)
        keyword = self._text(key)
        if not keyword:
            return self._page_result([], page)
        rows = self._cached_api("/dramas", {"sort": "latest", "q": keyword})
        if not isinstance(rows, list):
            raise ValueError("禁果搜索响应格式异常")
        return self._page_result(rows, page)

    def _parse_id(self, value):
        text = self._text(value)
        if text.startswith("atvp_detail:"):
            text = text[len("atvp_detail:"):]
        for prefix in ("jinguo:", "jgdj:"):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        parts = (text.split(":") + ["", ""])[:3]
        if not parts[0]:
            raise ValueError("缺少禁果剧集 ID")
        return parts

    def _detail(self, video_id):
        data = self._cached_api("/dramas/" + quote(video_id, safe=""), ttl=180)
        if not isinstance(data, dict):
            raise ValueError("禁果详情响应格式异常")
        return data

    def detailContent(self, ids):
        video_id, unused, unused_id = self._parse_id(ids[0] if isinstance(ids, list) else ids)
        data = self._detail(video_id)
        drama = data.get("drama") or {}
        episodes = data.get("episodes") or []
        entries = []
        for index, episode in enumerate(episodes):
            number = episode.get("number") or index + 1
            episode_id = self._text(episode.get("id"))
            target = "jgdj:%s:%s:%s" % (video_id, number, episode_id)
            label = self._label(self._text(episode.get("title")) or "第%s集" % number)
            entries.append(label + "$" + target)
        if not entries:
            entries = ["第1集$jgdj:%s:1" % video_id]
        tags = drama.get("tags") if isinstance(drama.get("tags"), list) else []
        return {"list": [{
            "vod_id": "jgdj:" + video_id,
            "vod_name": self._text(drama.get("title")) or video_id,
            "vod_pic": self._abs_url(drama.get("coverUrl")),
            "vod_content": self._text(data.get("description")) or " · ".join(str(tag) for tag in tags),
            "vod_play_from": "禁果",
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
                    episode for episode in episodes
                    if number in (str(episode.get("number")), str(episode.get("id")))
                ), episodes[0] if episodes else {})
                episode_id = self._text(selected.get("id"))
            if not episode_id:
                raise ValueError("缺少禁果分集 ID")
            play = self._api("/episodes/" + quote(episode_id, safe="") + "/play")
            if not isinstance(play, dict):
                raise ValueError("禁果播放响应格式异常")
            url = self._text(play.get("videoUrl"))
            if not url:
                raise ValueError("无播放地址，当前分集可能需要解锁")
            result["url"] = url
        except (ValueError, KeyError, TypeError, requests.RequestException):
            result.update({"msg": "禁果播放解析失败，接口不可用或当前分集需要解锁", "error": "playback_unavailable"})
        return result

    def localProxy(self, param):
        return [404, "text/plain; charset=utf-8", "禁果不需要本地代理"]

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
