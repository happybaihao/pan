# -*- coding: utf-8 -*-
"""Yangshipin live TV Spider for TVBox/Fengmi.

The old PHP implementations build a direct HLS URL with a legacy ``cKey``.
That request is now additionally bound to the official browser session, so
this Spider intentionally does not reproduce or bypass that protected player
flow.  It obtains the public channel directory and asks Fengmi/TVBox to load
the official channel page; Fengmi's WebView then discovers the official HLS
request and passes it to the player.

Only the public CCTV and satellite-TV channel records are exposed.
"""

import json
import re
import time
from urllib.parse import quote, unquote

try:
    import requests
except ImportError:  # Some Chaquopy builds expose only the stdlib.
    requests = None
    from urllib.request import Request, urlopen

try:
    from base.spider import Spider as BaseSpider
except Exception:  # Lets the module run in a normal desktop Python install.
    class BaseSpider(object):
        def __init__(self):
            pass


class Spider(BaseSpider):
    """CatVod-compatible public Yangshipin live-channel Spider."""

    NAME = "央视频直播"
    PAGE_URL = "https://www.yangshipin.cn/tv/home"
    CHANNEL_URL = "https://capi.yangshipin.cn/api/oms/pc/page/PG00000004"
    PAGE_SIZE = 24
    CACHE_SECONDS = 30 * 60
    WEB_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    API_HEADERS = {
        "User-Agent": WEB_USER_AGENT,
        "Accept": "application/octet-stream, */*",
        "Referer": "https://www.yangshipin.cn/",
        "yspappid": "519748109",
        "platform": "109",
        "app-platform": "pc",
        "app-version": "1.0.0",
    }
    TYPES = {
        "cctv": ("CCTV", "yangshi"),
        "satellite": ("卫视", "weishi"),
    }
    SATELLITE_ORDER = [
        "北京卫视", "东方卫视", "天津卫视", "重庆卫视", "黑龙江卫视",
        "辽宁卫视", "河北卫视", "山东卫视", "安徽卫视", "河南卫视",
        "湖北卫视", "湖南卫视", "江西卫视", "江苏卫视", "浙江卫视",
        "福建东南卫视", "广东卫视", "深圳卫视", "广西卫视", "贵州卫视",
        "四川卫视", "新疆卫视", "海南卫视", "吉林卫视", "山西卫视",
        "云南卫视", "内蒙古卫视", "陕西卫视", "甘肃卫视", "宁夏卫视",
        "青海卫视", "西藏卫视", "中国教育电视台1频道",
    ]
    # Complete last-resort directory captured from the public page metadata.
    # Normal operation still requests the current list first, so additions or
    # renamed channels are picked up without editing this file.
    FALLBACK_CHANNELS = [
        {"name": "CCTV1", "pid": "600001859", "stream": "2024078201", "type": "yangshi"},
        {"name": "CCTV10", "pid": "600001805", "stream": "2024078701", "type": "yangshi"},
        {"name": "CCTV11", "pid": "600001806", "stream": "2027248701", "type": "yangshi"},
        {"name": "CCTV12", "pid": "600001807", "stream": "2027248801", "type": "yangshi"},
        {"name": "CCTV13", "pid": "600001811", "stream": "2029797201", "type": "yangshi"},
        {"name": "CCTV14", "pid": "600001809", "stream": "2027248901", "type": "yangshi"},
        {"name": "CCTV15", "pid": "600001815", "stream": "2027249001", "type": "yangshi"},
        {"name": "CCTV16(4K）", "pid": "600099502", "stream": "2027249301", "type": "yangshi"},
        {"name": "CCTV16-HD", "pid": "600098637", "stream": "2027249101", "type": "yangshi"},
        {"name": "CCTV17", "pid": "600001810", "stream": "2027249401", "type": "yangshi"},
        {"name": "CCTV2", "pid": "600001800", "stream": "2024075401", "type": "yangshi"},
        {"name": "CCTV3", "pid": "600001801", "stream": "2024068501", "type": "yangshi"},
        {"name": "CCTV4", "pid": "600001814", "stream": "2029797101", "type": "yangshi"},
        {"name": "CCTV4K", "pid": "600002264", "stream": "2029810301", "type": "yangshi"},
        {"name": "CCTV5", "pid": "600001818", "stream": "2024078401", "type": "yangshi"},
        {"name": "CCTV5+", "pid": "600001817", "stream": "2024078001", "type": "yangshi"},
        {"name": "CCTV6", "pid": "600108442", "stream": "2013693901", "type": "yangshi"},
        {"name": "CCTV7", "pid": "600004092", "stream": "2024072001", "type": "yangshi"},
        {"name": "CCTV8", "pid": "600001803", "stream": "2029793001", "type": "yangshi"},
        {"name": "CCTV8K", "pid": "600156816", "stream": "2026774101", "type": "yangshi"},
        {"name": "CCTV9", "pid": "600004078", "stream": "2024078601", "type": "yangshi"},
        {"name": "CCTV世界地理频道", "pid": "600099637", "stream": "2026874403", "type": "yangshi"},
        {"name": "CCTV兵器科技频道", "pid": "600099649", "stream": "2026874603", "type": "yangshi"},
        {"name": "CCTV卫生健康频道", "pid": "600099651", "stream": "2025637003", "type": "yangshi"},
        {"name": "CCTV央视台球频道", "pid": "600099652", "stream": "2026875003", "type": "yangshi"},
        {"name": "CCTV央视文化精品频道", "pid": "600099653", "stream": "2026874903", "type": "yangshi"},
        {"name": "CCTV女性时尚频道", "pid": "600099650", "stream": "2026874803", "type": "yangshi"},
        {"name": "CCTV怀旧剧场频道", "pid": "600099620", "stream": "2026874303", "type": "yangshi"},
        {"name": "CCTV电视指南频道", "pid": "600099656", "stream": "2026875103", "type": "yangshi"},
        {"name": "CCTV第一剧场频道", "pid": "600099655", "stream": "2026874203", "type": "yangshi"},
        {"name": "CCTV风云剧场频道", "pid": "600099658", "stream": "2025637103", "type": "yangshi"},
        {"name": "CCTV风云足球频道", "pid": "600099636", "stream": "2026966203", "type": "yangshi"},
        {"name": "CCTV风云音乐频道", "pid": "600099660", "stream": "2026874503", "type": "yangshi"},
        {"name": "CCTV高尔夫·网球频道", "pid": "600099659", "stream": "2026874703", "type": "yangshi"},
        {"name": "CGTN", "pid": "600014550", "stream": "2024181701", "type": "yangshi"},
        {"name": "CGTN俄语频道", "pid": "600084758", "stream": "2024181901", "type": "yangshi"},
        {"name": "CGTN外语纪录频道", "pid": "600084781", "stream": "2024182301", "type": "yangshi"},
        {"name": "CGTN法语频道", "pid": "600084704", "stream": "2024181801", "type": "yangshi"},
        {"name": "CGTN西班牙语频道", "pid": "600084744", "stream": "2024182101", "type": "yangshi"},
        {"name": "CGTN阿拉伯语频道", "pid": "600084782", "stream": "2024182001", "type": "yangshi"},
        {"name": "东方卫视", "pid": "600002483", "stream": "2024054503", "type": "weishi"},
        {"name": "中国教育电视台1频道", "pid": "600171827", "stream": "2022823801", "type": "weishi"},
        {"name": "云南卫视", "pid": "600190402", "stream": "2025561303", "type": "weishi"},
        {"name": "内蒙古卫视", "pid": "600190401", "stream": "2025561203", "type": "weishi"},
        {"name": "北京卫视", "pid": "600002309", "stream": "2024052703", "type": "weishi"},
        {"name": "吉林卫视", "pid": "600190405", "stream": "2025561503", "type": "weishi"},
        {"name": "四川卫视", "pid": "600002516", "stream": "2024061403", "type": "weishi"},
        {"name": "天津卫视", "pid": "600152137", "stream": "2019927003", "type": "weishi"},
        {"name": "宁夏卫视", "pid": "600190737", "stream": "2025608503", "type": "weishi"},
        {"name": "安徽卫视", "pid": "600002532", "stream": "2024171403", "type": "weishi"},
        {"name": "山东卫视", "pid": "600002513", "stream": "2029787903", "type": "weishi"},
        {"name": "山西卫视", "pid": "600190407", "stream": "2025560803", "type": "weishi"},
        {"name": "广东卫视", "pid": "600002485", "stream": "2024060903", "type": "weishi"},
        {"name": "广西卫视", "pid": "600002509", "stream": "2024060703", "type": "weishi"},
        {"name": "新疆卫视", "pid": "600152138", "stream": "2019927403", "type": "weishi"},
        {"name": "江苏卫视", "pid": "600002521", "stream": "2024171103", "type": "weishi"},
        {"name": "江西卫视", "pid": "600002503", "stream": "2024061703", "type": "weishi"},
        {"name": "河北卫视", "pid": "600002493", "stream": "2024171503", "type": "weishi"},
        {"name": "河南卫视", "pid": "600002525", "stream": "2029797303", "type": "weishi"},
        {"name": "浙江卫视", "pid": "600002520", "stream": "2024054703", "type": "weishi"},
        {"name": "海南卫视", "pid": "600002506", "stream": "2024055603", "type": "weishi"},
        {"name": "深圳卫视", "pid": "600002481", "stream": "2024061303", "type": "weishi"},
        {"name": "湖北卫视", "pid": "600002508", "stream": "2024171203", "type": "weishi"},
        {"name": "湖南卫视", "pid": "600002475", "stream": "2024054803", "type": "weishi"},
        {"name": "甘肃卫视", "pid": "600190408", "stream": "2025561703", "type": "weishi"},
        {"name": "福建东南卫视", "pid": "600002484", "stream": "2024061503", "type": "weishi"},
        {"name": "西藏卫视", "pid": "600190403", "stream": "2025558003", "type": "weishi"},
        {"name": "贵州卫视", "pid": "600002490", "stream": "2024061603", "type": "weishi"},
        {"name": "辽宁卫视", "pid": "600002505", "stream": "2024171303", "type": "weishi"},
        {"name": "重庆卫视", "pid": "600002531", "stream": "2024061103", "type": "weishi"},
        {"name": "陕西卫视", "pid": "600190400", "stream": "2029795103", "type": "weishi"},
        {"name": "青海卫视", "pid": "600190406", "stream": "2025559103", "type": "weishi"},
        {"name": "黑龙江卫视", "pid": "600002498", "stream": "2029797003", "type": "weishi"},
    ]

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.session = requests.Session() if requests is not None else None
        if self.session is not None:
            self.session.headers.update(self.API_HEADERS)
        self._channels = []
        self._cache_until = 0

    def getName(self):
        return self.NAME

    def getDependence(self):
        return []

    def init(self, extend=""):
        # No external configuration is needed.  Keep the argument for the
        # CatVod Python Spider contract.
        return None

    def _log(self, message):
        try:
            self.log(message)
        except Exception:
            pass

    # ---- minimal protobuf reader ------------------------------------

    @staticmethod
    def _read_varint(data, offset):
        value = 0
        shift = 0
        while offset < len(data) and shift < 64:
            byte = data[offset]
            offset += 1
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value, offset
            shift += 7
        raise ValueError("invalid protobuf varint")

    @classmethod
    def _message(cls, data):
        """Return a generic protobuf field map without a bundled .proto file."""
        fields = {}
        offset = 0
        while offset < len(data):
            key, offset = cls._read_varint(data, offset)
            field, wire = key >> 3, key & 7
            if field <= 0:
                raise ValueError("invalid protobuf field")
            if wire == 0:
                value, offset = cls._read_varint(data, offset)
            elif wire == 1:
                if offset + 8 > len(data):
                    raise ValueError("truncated protobuf field")
                value = data[offset:offset + 8]
                offset += 8
            elif wire == 2:
                size, offset = cls._read_varint(data, offset)
                if size < 0 or offset + size > len(data):
                    raise ValueError("truncated protobuf field")
                value = data[offset:offset + size]
                offset += size
            elif wire == 5:
                if offset + 4 > len(data):
                    raise ValueError("truncated protobuf field")
                value = data[offset:offset + 4]
                offset += 4
            else:
                raise ValueError("unsupported protobuf wire type")
            fields.setdefault(field, []).append((wire, value))
        return fields

    @staticmethod
    def _field_texts(fields, field):
        result = []
        for wire, value in fields.get(field, []):
            if wire != 2:
                continue
            try:
                text = value.decode("utf-8").strip()
            except UnicodeDecodeError:
                continue
            if text:
                result.append(text)
        return result

    @classmethod
    def _walk_messages(cls, data, depth=0):
        if depth > 7 or not data:
            return
        try:
            fields = cls._message(data)
        except (TypeError, ValueError):
            return
        yield fields
        for values in fields.values():
            for wire, value in values:
                # The page response's top-level content container is roughly
                # 53 KB today.  Keep a ceiling to avoid recursing into an
                # unexpected huge blob, while allowing normal page payloads.
                if wire == 2 and 3 <= len(value) <= 2 * 1024 * 1024:
                    for nested in cls._walk_messages(value, depth + 1):
                        yield nested

    @classmethod
    def _paid_or_restricted(cls, fields):
        """Filter only explicit rights markers; integer flags are not stable."""
        text = " ".join(
            value.lower()
            for field in fields
            for value in cls._field_texts(fields, field)
        )
        return bool(re.search(r"(?:\\bvip\\b|\\bpaid\\b|\\bpay\\b|收费|付费|会员|restricted)", text))

    @classmethod
    def _decode_channels(cls, payload):
        channels = []
        seen = set()
        for fields in cls._walk_messages(payload):
            marker = (cls._field_texts(fields, 1) or [""])[0]
            name = (cls._field_texts(fields, 2) or [""])[0]
            pid = (cls._field_texts(fields, 4) or [""])[0]
            stream = (cls._field_texts(fields, 6) or [""])[0]
            channel_type = (cls._field_texts(fields, 11) or [""])[0]
            logos = cls._field_texts(fields, 5) + cls._field_texts(fields, 13)
            logo = next((item for item in logos if item.startswith("https://")), "")
            if marker != "tv-channel-list" or channel_type not in ("yangshi", "weishi"):
                continue
            if not name or not pid.isdigit() or pid in seen or cls._paid_or_restricted(fields):
                continue
            seen.add(pid)
            channels.append({
                "name": name,
                "pid": pid,
                "stream": stream,
                "type": channel_type,
                "logo": logo,
            })
        return cls._sort_channels(channels)

    @staticmethod
    def _sort_channels(channels):
        satellite_order = {name: index for index, name in enumerate(Spider.SATELLITE_ORDER)}

        def key(item):
            title = str(item.get("name") or "").strip()
            upper = title.upper()
            if item.get("type") == "yangshi":
                # Keep the main numbered CCTV channels in numeric order.
                # 4K/8K are variants, so place them after the regular set.
                special = {"CCTV4K": 104, "CCTV8K": 108}
                if upper in special:
                    return 0, special[upper], 0, upper
                match = re.fullmatch(r"CCTV(\d+)(.*)", upper)
                if match:
                    suffix = match.group(2)
                    suffix_rank = {"": 0, "+": 1, "-HD": 2}.get(suffix, 3)
                    return 0, int(match.group(1)), suffix_rank, upper
                if upper == "CGTN":
                    return 2, 0, 0, upper
                return 1, 0, 0, upper
            if item.get("type") == "weishi":
                return 3, satellite_order.get(title, len(satellite_order)), 0, title
            return 4, 0, 0, title

        return sorted(channels, key=key)

    def _get_channels(self):
        if self._channels and time.time() < self._cache_until:
            return self._channels
        try:
            # The public endpoint uses a timestamp query value to avoid a stale
            # CDN object.  It has no user/account data.
            url = "%s?%d" % (self.CHANNEL_URL, int(time.time() * 1000))
            if self.session is not None:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                payload = response.content
            else:
                request = Request(url, headers=dict(self.API_HEADERS))
                with urlopen(request, timeout=15) as response:
                    payload = response.read()
            channels = self._decode_channels(payload)
            if channels:
                self._channels = channels
                self._cache_until = time.time() + self.CACHE_SECONDS
                return channels
        except Exception as exc:
            self._log("yangshipin channel directory error: %s" % exc)
        self._channels = self._sort_channels(list(self.FALLBACK_CHANNELS))
        self._cache_until = time.time() + 60
        return self._channels

    # ---- TVBox/Fengmi response helpers ------------------------------

    @staticmethod
    def _number(value, default=1):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clean(value):
        return re.sub(r"\\s+", " ", str(value or "")).strip()

    def _video(self, channel):
        return {
            "vod_id": channel["pid"],
            "vod_name": channel["name"],
            "vod_pic": channel.get("logo", ""),
            "vod_remarks": "直播",
        }

    def _by_type(self, tid):
        return [
            item for item in self._get_channels()
            if item.get("type") == self.TYPES.get(str(tid), ("", ""))[1]
        ]

    def _by_pid(self, pid):
        return next((item for item in self._get_channels() if item.get("pid") == pid), None)

    # ---- TVBox/Fengmi data contract ---------------------------------

    def homeContent(self, filter=None):
        cctv = self._by_type("cctv")
        satellite = self._by_type("satellite")
        return {
            "class": [
                {"type_name": "CCTV", "type_id": "cctv"},
                {"type_name": "卫视", "type_id": "satellite"},
            ],
            "list": [self._video(item) for item in (cctv[:12] + satellite[:12])],
        }

    def homeVideoContent(self):
        return self.homeContent({}).get("list", [])

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        tid = str(tid or "")
        items = self._by_type(tid)
        page = self._number(pg)
        start = (page - 1) * self.PAGE_SIZE
        total = len(items)
        return {
            "list": [self._video(item) for item in items[start:start + self.PAGE_SIZE]],
            "page": page,
            "pagecount": max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE),
            "limit": self.PAGE_SIZE,
            "total": total,
        }

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        pid = self._clean(str(ids or "").split(",", 1)[0])
        channel = self._by_pid(pid)
        if not channel:
            return {"list": []}
        vod = self._video(channel)
        vod.update({
            "vod_content": "通过央视频官方页面播放。",
            "vod_play_from": "央视频",
            "vod_play_url": "官方直播$%s" % channel["pid"],
        })
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        keyword = self._clean(key).lower()
        page = self._number(pg)
        items = self._get_channels()
        if keyword:
            items = [item for item in items if keyword in item["name"].lower()]
        start = (page - 1) * self.PAGE_SIZE
        total = len(items)
        return {
            "list": [self._video(item) for item in items[start:start + self.PAGE_SIZE]],
            "page": page,
            "pagecount": max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE),
            "limit": self.PAGE_SIZE,
            "total": total,
        }

    def playerContent(self, flag, id, vipFlags=None):
        pid = unquote(str(id or "")).strip()
        if not pid.isdigit() or not self._by_pid(pid):
            return {"parse": 1, "url": "", "playUrl": "", "header": {}}
        return {
            "parse": 1,
            "url": "%s?pid=%s" % (self.PAGE_URL, quote(pid, safe="")),
            "playUrl": "",
            "header": {
                "User-Agent": self.WEB_USER_AGENT,
                "Referer": "https://www.yangshipin.cn/",
            },
        }

    def isVideoFormat(self, url):
        return ".m3u8" in str(url or "").lower()

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def destroy(self):
        try:
            if self.session is not None:
                self.session.close()
        except Exception:
            pass


if __name__ == "__main__":
    spider = Spider()
    print(json.dumps(spider.homeContent({}), ensure_ascii=False, indent=2))
