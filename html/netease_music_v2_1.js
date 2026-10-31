// 影音TV 音乐库 v2.1.0 · netease直连 · 分类修正版 | SPDX-License-Identifier: GPL-3.0-only
const MH_BUILD_PLATFORM="netease";
function createKuwo(req) {
// T4 / catvod 格式，对应 py 版同名脚本

let token = '';
let bangCache = null;
let songCache = Object.create(null);
let songCacheOrder = [];

// ==================== 公共方法 ====================

function newToken() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let s = '';
    for (let i = 0; i < 10; i++) {
        s += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return s;
}

function headers() {
    if (!token) token = newToken();
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'http://www.kuwo.cn/',
        'csrf': token,
        'Cookie': 'kw_token=' + token
    };
}

// 不同宿主 req 返回结构不一致，统一取出 JSON
async function getJson(url, timeout) {
    try {
        const resp = await req(url, {
            method: 'get',
            headers: headers(),
            timeout: timeout || 10000
        });
        if (!resp) return {};
        let body = resp.content;
        if (body === undefined) body = resp.data;
        if (body === undefined) body = resp.body;
        if (body === undefined) body = resp;
        if (typeof body === 'string') {
            try {
                return JSON.parse(body);
            } catch (e) {
                return {};
            }
        }
        return body || {};
    } catch (e) {
        return {};
    }
}

function pad(n, len) {
    let s = String(n);
    while (s.length < len) s = '0' + s;
    return s;
}

function cleanText(value) {
    return String(value || '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/<[^>]+>/g, '').trim();
}

// 同 HTML：相对专辑路径补全，升级 500px；不拿歌手头像冒充歌曲封面。
function coverUrl(value) {
    if (Array.isArray(value)) value = value[0];
    let url = String(value || '').trim();
    if (!url) return '';
    if (url.indexOf('//') === 0) url = 'https:' + url;
    else if (!/^https?:\/\//i.test(url)) {
        if (/^[a-z][a-z\d+.-]*:/i.test(url)) return '';
        url = 'https://img1.kuwo.cn/star/albumcover/' + url.replace(/^\/+/, '');
    }
    return url.replace(/^http:/i, 'https:')
        .replace(/_(120|150|300)(\.(?:jpe?g|png|webp))(?=\?|$)/i, '_500$2')
        .replace(/\/albumcover\/(120|150|300)\//i, '/albumcover/500/');
}

function rememberSong(song) {
    if (!song || !/^\d+$/.test(String(song.rid))) return song;
    const rid = String(song.rid);
    let saved = songCache[rid];
    if (!saved) {
        saved = { rid: rid, name: '', artist: '', album: '', pic: '', lrc: '' };
        songCache[rid] = saved; songCacheOrder.push(rid);
        if (songCacheOrder.length > 384) delete songCache[songCacheOrder.shift()];
    }
    for (const key of ['name', 'artist', 'album', 'pic', 'lrc']) if (song[key]) saved[key] = song[key];
    return saved;
}

function lrcFrom(data) {
    const root = (data && data.data) || data || {};
    const raw = root.lrclist || root.lyricList || root.lrcList || [];
    if (Array.isArray(raw) && raw.length) {
        const lines = [];
        for (const item of raw) {
            const seconds = parseFloat(item.time);
            const text = cleanText(item.lineLyric || item.text || item.lyric);
            if (isFinite(seconds) && seconds >= 0 && text) lines.push({ time: seconds, text: text });
        }
        lines.sort((a, b) => a.time - b.time);
        return lines.map(item => '[' + formatTime(item.time) + ']' + item.text).join('\n');
    }
    for (const key of ['lrc', 'lyric', 'lyrics']) {
        const value = root[key];
        if (typeof value === 'string' && /\[\d+:\d+/.test(value)) return value;
        if (value && typeof value.lyric === 'string') return value.lyric;
    }
    return '';
}

async function trackMetadata(rid) {
    let song = songCache[rid] || { rid: rid };
    const results = await Promise.all([
        song.name && song.artist && song.pic ? Promise.resolve({}) :
            getJson('http://wapi.kuwo.cn/api/www/music/musicInfo?mid=' + rid, 3000),
        song.lrc ? Promise.resolve({}) :
            getJson('https://kuwo.cn/openapi/v1/www/lyric/getlyric?musicId=' + rid, 3000)
    ]);
    const info = results[0].data || {};
    const normal = normSongs([Object.assign({}, info, { rid: rid })]);
    if (normal.length) song = normal[0];
    song = rememberSong(Object.assign({}, song, { lrc: lrcFrom(results[1]) }));
    if (!song.name || !song.pic || !song.lrc) {
        const fallback = await getJson('https://m.kuwo.cn/newh5/singles/songinfoandlrc?musicId=' + rid + '&httpsStatus=1', 3000);
        const data = fallback.data || {};
        const songinfo = data.songinfo || {};
        song = rememberSong({ rid: rid, name: cleanText(songinfo.songName || songinfo.name),
            artist: cleanText(songinfo.artist || songinfo.singer), album: cleanText(songinfo.album),
            pic: coverUrl(songinfo.pic || songinfo.albumpic || songinfo.picture), lrc: lrcFrom(fallback) });
    }
    if (!song.pic) {
        // pic.web returns the image URL as TEXT, not image bytes. Resolve it first.
        try {
            const resp = await req('https://artistpicserver.kuwo.cn/pic.web?type=rid_pic&pictype=url&size=500&rid=' + rid,
                { method: 'get', headers: headers(), timeout: 2000 });
            const body = typeof resp === 'string' ? resp : resp && (resp.content || resp.data || resp.body);
            if (typeof body === 'string' && /^https?:\/\/\S+$/i.test(body.trim())) song = rememberSong({ rid: rid, pic: coverUrl(body.trim()) });
        } catch (e) {}
    }
    return Object.assign({}, song);
}

// 兼容 data 为数组 / data.data / data.list 几种结构
function pickList(data) {
    const d = data.data;
    if (Array.isArray(d)) return d;
    if (d && typeof d === 'object') {
        const keys = ['data', 'list', 'musicList', 'artistList'];
        for (const k of keys) {
            if (Array.isArray(d[k])) return d[k];
        }
    }
    return [];
}

// 统一歌曲结构，rid 必须是纯数字，否则是目录节点之类的假条目
function normSongs(rawList) {
    const out = [];
    if (!Array.isArray(rawList)) return out;
    for (const m of rawList) {
        if (!m || typeof m !== 'object') continue;
        let rid = m.rid || m.id || m.musicrid || m.MUSICRID || m.musicId || '';
        rid = String(rid).replace('MUSIC_', '').trim();
        const name = cleanText(m.name || m.songName || m.songname || m.SONGNAME);
        const artist = cleanText(m.artist || m.singer || m.ARTIST);
        if (name && /^\d+$/.test(rid)) {
            out.push(rememberSong({ name: name, rid: rid, artist: artist,
                album: cleanText(m.album || m.albumName || m.ALBUM),
                pic: coverUrl(m.albumpic || m.web_albumpic_short || m.hts_albumpic || m.pic || m.picture) }));
        }
    }
    return out;
}

function songsToPlayUrl(songs) {
    const arr = [];
    for (const s of songs) {
        const name = String(s.name || '').replace(/[$#]/g, '').trim();
        const artist = String(s.artist || '').replace(/[$#]/g, '').trim();
        if (!name || !s.rid) continue;
        arr.push(artist ? `${name} - ${artist}$${s.rid}` : `${name}$${s.rid}`);
    }
    return arr;
}

// ==================== init / 首页 ====================

async function init(cfg) {
    token = newToken();
    bangCache = null;
    songCache = Object.create(null); songCacheOrder = [];
}

async function home(filter) {
    const classes = [
        { type_name: '推荐歌单', type_id: 'playlist' },
        { type_name: '排行榜', type_id: 'bang' },
        { type_name: '华语男', type_id: '1' },
        { type_name: '华语女', type_id: '2' },
        { type_name: '华语组合', type_id: '3' },
        { type_name: '日韩男', type_id: '4' },
        { type_name: '日韩女', type_id: '5' },
        { type_name: '日韩组合', type_id: '6' },
        { type_name: '欧美男', type_id: '7' },
        { type_name: '欧美女', type_id: '8' },
        { type_name: '欧美组合', type_id: '9' },
        { type_name: '其他', type_id: '0' }
    ];

    let tagValues = [
        { n: '最热', v: 'hot' },
        { n: '最新', v: 'new' }
    ];
    try {
        tagValues = tagValues.concat(await getPlaylistTags());
    } catch (e) {}

    return JSON.stringify({
        class: classes,
        filters: {
            playlist: [{ key: 'tag', name: '分类', value: tagValues }]
        }
    });
}

async function getPlaylistTags() {
    const data = await getJson('http://wapi.kuwo.cn/api/www/playlist/getTagList');
    const tags = [];
    const seen = ['推荐', '推荐歌单', '最热', '最新'];
    let groups = data.data || [];
    if (!Array.isArray(groups) && groups && typeof groups === 'object') {
        groups = groups.data || [];
    }
    for (const group of groups) {
        const items = (group && group.data) || [];
        for (const t of items) {
            const tid = t.id;
            const name = t.name;
            if (tid && name && seen.indexOf(name) === -1) {
                seen.push(name);
                tags.push({ n: name, v: String(tid) });
            }
        }
    }
    return tags.slice(0, 40);
}

// 首页推荐留空，避免与「推荐歌单」分类内容重复
async function homeVod() {
    return JSON.stringify({ list: [] });
}

// ==================== 分类 ====================

async function category(tid, pg, filter, extend) {
    if (!pg) pg = 1;
    if (tid === 'playlist') return await playlistCategory(pg, extend || {});
    if (tid === 'bang') return await bangCategory();
    return await artistCategory(tid, pg);
}

async function playlistCategory(pg, extend) {
    const tag = extend.tag || 'hot';
    let url;
    if (tag === 'hot' || tag === 'new') {
        url = 'http://wapi.kuwo.cn/api/www/classify/playlist/getRcmPlayList' +
              `?pn=${pg}&rn=30&order=${tag}`;
    } else {
        url = 'http://wapi.kuwo.cn/api/www/classify/playlist/getTagPlayList' +
              `?id=${tag}&pn=${pg}&rn=30`;
    }

    const videos = [];
    try {
        const data = await getJson(url);
        for (const item of pickList(data)) {
            const pid = item.id;
            if (!pid) continue;
            const cnt = item.listencnt || item.playCnt || '';
            videos.push({
                vod_id: 'pl_' + pid,
                vod_name: item.name || '',
                vod_pic: item.img || item.pic || '',
                vod_remarks: cnt ? '播放 : ' + cnt : (item.total || '') + '首'
            });
        }
    } catch (e) {}

    return JSON.stringify({
        list: videos, page: pg, pagecount: 9999, limit: 30, total: 999999
    });
}

async function bangCategory() {
    const videos = [];
    const cache = {};
    try {
        const data = await getJson('http://wapi.kuwo.cn/api/www/bang/bang/bangMenu');
        let groups = data.data || [];
        if (!Array.isArray(groups) && groups && typeof groups === 'object') {
            groups = groups.data || [];
        }
        for (const group of groups) {
            const gname = (group && group.name) || '';
            const items = (group && (group.list || group.data)) || [];
            for (const b of items) {
                const sid = String(b.sourceid || '');
                if (!sid) continue;
                cache[sid] = [b.name || '', b.pic || '', b.intro || ''];
                videos.push({
                    vod_id: 'bang_' + sid,
                    vod_name: b.name || '',
                    vod_pic: b.pic || b.img || '',
                    vod_remarks: gname
                });
            }
        }
        bangCache = cache;
    } catch (e) {}

    return JSON.stringify({
        list: videos, page: 1, pagecount: 1,
        limit: videos.length || 100, total: videos.length || 100
    });
}

async function artistCategory(tid, pg) {
    const url = 'http://wapi.kuwo.cn/api/www/artist/artistInfo' +
                `?category=${tid}&prefix=&pn=${pg}&rn=30`;
    const videos = [];
    try {
        const data = await getJson(url);
        const list = (data.data && data.data.artistList) || [];
        for (const item of list) {
            videos.push({
                vod_id: String(item.id || ''),
                vod_name: item.name || '',
                vod_pic: item.pic300 || item.pic || item.pic120 || '',
                vod_remarks: ''
            });
        }
    } catch (e) {}

    return JSON.stringify({
        list: videos, page: pg, pagecount: 9999, limit: 90, total: 999999
    });
}

// ==================== 详情 ====================

async function detail(id) {
    let vid = Array.isArray(id) ? id[0] : id;
    vid = String(vid);
    try {
        if (vid.indexOf('pl_') === 0) return await playlistDetail(vid.substring(3));
        if (vid.indexOf('bang_') === 0) return await bangDetail(vid.substring(5));
        if (vid.indexOf('song_') === 0) return await songDetail(vid.substring(5));
        return await artistDetail(vid);
    } catch (e) {
        return JSON.stringify({
            list: [{
                vod_id: vid,
                vod_name: '加载失败',
                vod_content: '加载失败: ' + e,
                vod_remarks: '加载失败',
                vod_actor: '未知',
                vod_play_from: '酷我音乐',
                vod_play_url: ''
            }]
        });
    }
}

async function playlistDetail(pid) {
    let name = '', pic = '', info = '', note = '';
    let songs = [];

    // rn 过大会被接口拒掉，固定 30 分页
    for (let pn = 1; pn <= 10; pn++) {
        const url = 'http://wapi.kuwo.cn/api/www/playlist/playListInfo' +
                    `?pid=${pid}&pn=${pn}&rn=30`;
        const data = await getJson(url);
        const d = data.data || {};
        if (pn === 1) {
            note = `code=${data.code} msg=${String(data.msg || '').substring(0, 20)}`;
            name = d.name || '';
            pic = d.img || d.pic || '';
            info = String(d.info || '').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim();
        }
        const pageSongs = normSongs(d.musicList);
        if (!pageSongs.length) break;
        songs = songs.concat(pageSongs);
        if (pageSongs.length < 30 || songs.length >= 300) break;
    }

    const playArr = songsToPlayUrl(songs.slice(0, 300));
    return JSON.stringify({
        list: [{
            vod_id: 'pl_' + pid,
            vod_name: name,
            vod_pic: pic,
            vod_content: playArr.length ? (info || '暂无歌单简介') : '未获取到歌曲：' + note,
            vod_remarks: `歌曲 :   ${playArr.length}首`,
            vod_actor: '',
            vod_play_from: '酷我音乐',
            vod_play_url: playArr.join('#')
        }]
    });
}

async function bangPage(sid, pn, rn) {
    const url = 'http://wapi.kuwo.cn/api/www/bang/bang/musicList' +
                `?bangId=${sid}&pn=${pn}&rn=${rn}`;
    const data = await getJson(url, 8000);
    const d = data.data || {};
    return {
        code: data.code,
        msg: String(data.msg || ''),
        img: d.img || '',
        songs: normSongs(d.musicList)
    };
}

async function bangDetail(raw) {
    const sid = raw.split('~')[0];
    const meta = await bangInfo(sid);
    let name = meta[0], pic = meta[1];
    const intro = meta[2];

    let songs = [];
    let note = '';
    let rn = 0;

    // rn 过大会被接口拒掉，自适应挑一个能用的
    for (const tryRn of [30, 20, 10]) {
        const r = await bangPage(sid, 1, tryRn);
        note = `rn=${tryRn} code=${r.code} msg=${r.msg.substring(0, 20)} 歌曲=${r.songs.length}`;
        if (r.code === 200 && r.songs.length) {
            rn = tryRn;
            pic = r.img || pic;
            songs = r.songs;
            break;
        }
    }

    if (rn) {
        for (let pn = 2; pn < 12; pn++) {
            if (songs.length >= 300) break;
            const r = await bangPage(sid, pn, rn);
            if (r.code !== 200 || !r.songs.length) break;
            songs = songs.concat(r.songs);
            if (r.songs.length < rn) break;
        }
    }

    const playArr = songsToPlayUrl(songs.slice(0, 300));
    return JSON.stringify({
        list: [{
            vod_id: 'bang_' + sid,
            vod_name: name || '酷我榜单',
            vod_pic: pic,
            vod_content: playArr.length ? (intro || '酷我排行榜') : '未获取到歌曲：' + note,
            vod_remarks: `歌曲 :   ${playArr.length}首`,
            vod_actor: '排行榜',
            vod_play_from: '酷我音乐',
            vod_play_url: playArr.join('#')
        }]
    });
}

// 榜单歌曲接口返回里没有 name 字段，标题要从 bangMenu 取
async function bangInfo(sid) {
    if (!bangCache) {
        const cache = {};
        try {
            const data = await getJson('http://wapi.kuwo.cn/api/www/bang/bang/bangMenu');
            let groups = data.data || [];
            if (!Array.isArray(groups) && groups && typeof groups === 'object') {
                groups = groups.data || [];
            }
            for (const group of groups) {
                const items = (group && (group.list || group.data)) || [];
                for (const b of items) {
                    const key = String(b.sourceid || '');
                    if (key) cache[key] = [b.name || '', b.pic || '', b.intro || ''];
                }
            }
        } catch (e) {}
        bangCache = cache;
    }
    return bangCache[String(sid)] || ['', '', ''];
}

async function songDetail(rid) {
    const song = await trackMetadata(String(rid));
    const name = song.name, artist = song.artist, album = song.album, pic = song.pic;

    // 拿不到信息也要能播，rid 才是播放必需的
    const title = name || ('单曲 ' + rid);
    const label = (artist ? `${title} - ${artist}` : title).replace(/[$#]/g, '');

    return JSON.stringify({
        list: [{
            vod_id: 'song_' + rid,
            vod_name: title,
            vod_pic: pic,
            vod_content: album ? '专辑：' + album : '酷我单曲',
            vod_remarks: artist,
            vod_actor: artist,
            vod_play_from: '酷我音乐',
            vod_play_url: `${label}$${rid}`
        }]
    });
}

async function artistDetail(rid) {
    const data = await getJson(`http://wapi.kuwo.cn/api/www/artist/artist?artistid=${rid}`);
    const d = data.data || {};
    const artistName = d.name || '';

    const allSongs = await getArtistSongs(rid, artistName);

    const artistInfo = String(d.info || '')
        .replace(/<[^>]+>/g, '')
        .replace(/&nbsp;/g, ' ')
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n')
        .trim();

    const playArr = [];
    for (const song of allSongs.slice(0, 300)) {
        const name = String(song.name || '').replace(/[$#]/g, '').trim();
        const album = String(song.album || '').replace(/[$#]/g, '').trim();
        playArr.push(album ? `${name} - ${album}$${song.rid}` : `${name}$${song.rid}`);
    }

    return JSON.stringify({
        list: [{
            vod_id: rid,
            vod_name: artistName,
            vod_pic: d.pic300 || d.pic || '',
            vod_content: artistInfo || '暂无歌手简介',
            vod_remarks: `歌曲 :   ${playArr.length}首`,
            vod_actor: artistName,
            vod_play_from: '酷我音乐',
            vod_play_url: playArr.join('#')
        }]
    });
}

async function getArtistSongs(rid, artistName) {
    const songs = [];
    for (let page = 1; page <= 10; page++) {
        const url = 'http://wapi.kuwo.cn/api/www/artist/artistMusic' +
                    `?artistid=${rid}&pn=${page}&rn=30`;
        const data = await getJson(url);
        if (data.code !== 200) break;
        const list = (data.data && data.data.list) || [];
        if (!list.length) break;
        for (const song of normSongs(list)) songs.push(rememberSong(Object.assign({}, song, { artist: song.artist || artistName || '' })));
        if (songs.length >= 300) return songs.slice(0, 300);
    }
    return songs;
}

// ==================== 播放 ====================

async function play(flag, id, flags) {
    const rid = String(id || '').replace(/^MUSIC_/, '').trim();
    if (!/^\d+$/.test(rid)) return JSON.stringify({ parse: 0, playUrl: '', url: '', header: {} });
    // Metadata runs alongside the existing quality requests, not after them.
    const metadataTask = trackMetadata(rid).catch(() => songCache[rid] || { rid: rid });
    const qualities = [];
    const qualityList = [
        ['无损FLAC', 2000, 'flac'],
        ['高品质320K', 320, 'mp3'],
        ['标准128K', 128, 'mp3']
    ];

    const mobiHeaders = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10)',
        'Referer': 'https://www.kuwo.cn/'
    };

    for (const q of qualityList) {
        try {
            const apiUrl = 'https://nmobi.kuwo.cn/mobi.s?f=web&user=0' +
                '&source=kwplayer_ar_4.4.2.7_B_nuoweida_vh.apk' +
                `&type=convert_url_with_sign&rid=${rid}&bitrate=${q[1]}&format=${q[2]}`;
            const resp = await req(apiUrl, { method: 'get', headers: mobiHeaders, timeout: 5000 });
            let body = resp && (resp.content !== undefined ? resp.content : resp.data);
            if (typeof body === 'string') body = JSON.parse(body);
            if (body && body.code === 200 && body.data && body.data.url) {
                qualities.push([q[0], body.data.url]);
            }
        } catch (e) {}
    }

    if (!qualities.length) {
        return JSON.stringify({ parse: 0, playUrl: '', url: '', header: {} });
    }

    const urls = [];
    for (const q of qualities) {
        urls.push(q[0]);
        urls.push(q[1]);
    }

    const result = {
        parse: 0,
        playUrl: '',
        url: urls,
        header: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.kuwo.cn/'
        }
    };

    const meta = await metadataTask;
    result.mediaType = 'audio';
    result.title = meta.name || '';
    result.artist = meta.artist || '';
    result.album = meta.album || '';
    result.artwork = meta.pic || '';
    result.cover = result.artwork;
    result.lyric = meta.lrc || '';
    result.music = { id: rid, title: result.title, artist: result.artist, album: result.album,
        artwork: result.artwork, lyric: result.lyric };

    // 原始 LRC 给沉浸页，不再二次按歌名匹配；原视频页保留 SSA 兼容。
    try {
        if (result.lyric) {
            const ssa = createSsaSubtitle(result.lyric);
            if (ssa) {
                result.subs = [{
                    name: '5行歌词',
                    url: 'data:text/x-ssa;base64,' + b64encode(ssa),
                    format: 'text/x-ssa',
                    selected: true
                }];
            }
        }
    } catch (e) {}

    return JSON.stringify(result);
}

// ==================== 歌词 / base64 ====================

// btoa 不接受非 Latin-1 字符，中文歌词必须先转 UTF-8 字节
function utf8Bytes(str) {
    const out = [];
    for (let i = 0; i < str.length; i++) {
        let c = str.charCodeAt(i);
        if (c < 0x80) {
            out.push(c);
        } else if (c < 0x800) {
            out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
        } else if (c >= 0xd800 && c <= 0xdbff && i + 1 < str.length) {
            const c2 = str.charCodeAt(i + 1);
            if (c2 >= 0xdc00 && c2 <= 0xdfff) {
                const cp = 0x10000 + ((c & 0x3ff) << 10) + (c2 & 0x3ff);
                out.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3f),
                         0x80 | ((cp >> 6) & 0x3f), 0x80 | (cp & 0x3f));
                i++;
            } else {
                out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
            }
        } else {
            out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
        }
    }
    return out;
}

function b64encode(str) {
    const T = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    const bytes = utf8Bytes(str);
    let out = '';
    for (let i = 0; i < bytes.length; i += 3) {
        const b0 = bytes[i];
        const b1 = i + 1 < bytes.length ? bytes[i + 1] : undefined;
        const b2 = i + 2 < bytes.length ? bytes[i + 2] : undefined;
        out += T.charAt(b0 >> 2);
        out += T.charAt(((b0 & 3) << 4) | ((b1 === undefined ? 0 : b1) >> 4));
        out += b1 === undefined ? '=' : T.charAt(((b1 & 15) << 2) | ((b2 === undefined ? 0 : b2) >> 6));
        out += b2 === undefined ? '=' : T.charAt(b2 & 63);
    }
    return out;
}

function formatTime(seconds) {
    const cs = Math.max(0, Math.round(Number(seconds) * 100) || 0);
    return pad(Math.floor(cs / 6000), 2) + ':' + pad(Math.floor(cs / 100) % 60, 2) + '.' + pad(cs % 100, 2);
}

function formatSsaTime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const cs = Math.floor((seconds * 100) % 100);
    return `${h}:${pad(m, 2)}:${pad(s, 2)}.${pad(cs, 2)}`;
}

function createSsaSubtitle(lrcText) {
    const lines = [];
    const pattern = /^\[(\d+):(\d{2})(?:\.(\d{1,3}))?\](.*)$/;

    for (const line of lrcText.split('\n')) {
        const m = line.match(pattern);
        if (m) {
            const total = parseInt(m[1], 10) * 60 + parseInt(m[2], 10) + (m[3] ? Number('0.' + m[3]) : 0);
            const text = m[4].trim().replace(/[{}]/g, '').replace(/\\/g, '／');
            if (text) lines.push({ start: total, text: text });
        }
    }

    if (!lines.length) return '';

    const ssaHeader =
'[Script Info]\n' +
'ScriptType: v4.00+\n' +
'Collisions: Normal\n' +
'PlayResX: 1280\n' +
'PlayResY: 720\n' +
'Timer: 100.0000\n' +
'WrapStyle: 0\n' +
'\n' +
'[V4+ Styles]\n' +
'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n' +
'Style: WAITING_TOP2,Roboto,55,&H0000FFFF,&H00808080,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,1,1,2,0,0,180,1\n' +
'Style: WAITING_TOP1,Roboto,55,&H0000FFFF,&H00808080,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,1,1,2,0,0,260,1\n' +
'Style: PLAYING_CENTER,Roboto,60,&H0047BFFF,&H00808080,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,2,2,0,0,340,1\n' +
'Style: PLAYED_BOTTOM1,Roboto,55,&H0000FFFF,&H00808080,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,1,1,2,0,0,420,1\n' +
'Style: PLAYED_BOTTOM2,Roboto,55,&H0000FFFF,&H00808080,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,1,1,2,0,0,500,1\n' +
'\n' +
'[Events]\n' +
'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n';

    const events = [];
    for (let i = 0; i < lines.length; i++) {
        const current = lines[i];
        const currentEnd = i + 1 < lines.length ? lines[i + 1].start : current.start + 5.0;

        const wait2 = i + 2 < lines.length ? lines[i + 2] : null;
        const wait1 = i + 1 < lines.length ? lines[i + 1] : null;
        const played1 = i - 1 >= 0 ? lines[i - 1] : null;
        const played2 = i - 2 >= 0 ? lines[i - 2] : null;

        const st = formatSsaTime(current.start);
        const et = formatSsaTime(currentEnd);

        if (wait2) events.push(`Dialogue: 1,${st},${et},WAITING_TOP2,,0,0,0,,${wait2.text}`);
        if (wait1) events.push(`Dialogue: 2,${st},${et},WAITING_TOP1,,0,0,0,,${wait1.text}`);
        events.push(`Dialogue: 3,${st},${et},PLAYING_CENTER,,0,0,0,,${current.text}`);
        if (played1) events.push(`Dialogue: 4,${st},${et},PLAYED_BOTTOM1,,0,0,0,,${played1.text}`);
        if (played2) events.push(`Dialogue: 5,${st},${et},PLAYED_BOTTOM2,,0,0,0,,${played2.text}`);
    }

    return ssaHeader + events.join('\n');
}

// ==================== 搜索 ====================

async function search(wd, quick, pg) {
    let page = parseInt(pg, 10);
    if (!page || page < 1) page = 1;

    let videos = [];
    // 第一页混合展示，后续页只翻歌曲
    if (page === 1) {
        videos = videos.concat(await searchArtist(wd, 1));
        videos = videos.concat(await searchPlaylist(wd, 1));
    }
    videos = videos.concat(await searchSong(wd, page));

    return JSON.stringify({
        list: videos, page: page, pagecount: 9999, limit: 30, total: 999999
    });
}

async function searchArtist(key, pg) {
    const wd = encodeURIComponent(key);
    const pn = (pg - 1) * 10;
    const url = `https://search.kuwo.cn/r.s?client=kt&pn=${pn}&rn=10&all=${wd}` +
                '&vipver=1&ft=artist&encoding=utf8&rformat=json&mobi=1';
    const videos = [];
    try {
        const data = await getJson(url);
        const basePath = data.BASEPICPATH || 'http://img1.kuwo.cn/star/starheads/';
        for (const item of (data.abslist || [])) {
            const aid = item.ARTISTID || item.DC_TARGETID || '';
            if (!aid) continue;
            const pic = item.hts_PICPATH || (item.PICPATH ? basePath + item.PICPATH : '');
            videos.push({
                vod_id: String(aid),
                vod_name: item.ARTIST || '',
                vod_pic: pic,
                vod_remarks: `歌手 · ${item.SONGNUM || 0}首`
            });
        }
    } catch (e) {}
    return videos;
}

async function searchSong(key, pg) {
    const wd = encodeURIComponent(key);
    const pn = (pg - 1) * 30;
    const url = `https://search.kuwo.cn/r.s?client=kt&pn=${pn}&rn=30&all=${wd}` +
                '&vipver=1&ft=music&encoding=utf8&rformat=json&mobi=1';
    let videos = [];
    try {
        const data = await getJson(url);
        for (const item of (data.abslist || [])) {
            let rid = String(item.MUSICRID || item.DC_TARGETID || '')
                .replace('MUSIC_', '').trim();
            if (!/^\d+$/.test(rid)) continue;
            const name = cleanText(item.SONGNAME);
            const artist = cleanText(item.ARTIST);
            const pic = coverUrl(item.web_albumpic_short || item.albumpic || item.hts_albumpic || item.pic);
            rememberSong({ rid: rid, name: name, artist: artist, album: cleanText(item.ALBUM), pic: pic });
            videos.push({
                vod_id: 'song_' + rid,
                vod_name: name,
                vod_pic: pic,
                vod_remarks: '歌曲 · ' + artist
            });
        }
    } catch (e) {}

    // r.s 没结果时退到 www 搜索接口
    if (!videos.length) {
        try {
            const url2 = 'http://wapi.kuwo.cn/api/www/search/searchMusicBykeyWord' +
                         `?key=${wd}&pn=${pg}&rn=30`;
            const data = await getJson(url2);
            for (const item of normSongs(pickList(data))) {
                const rid = String(item.rid || '');
                if (!/^\d+$/.test(rid)) continue;
                videos.push({
                    vod_id: 'song_' + rid,
                    vod_name: String(item.name || '').trim(),
                    vod_pic: item.pic || '',
                    vod_remarks: '歌曲 · ' + (item.artist || '')
                });
            }
        } catch (e) {}
    }
    return videos;
}

async function searchPlaylist(key, pg) {
    const wd = encodeURIComponent(key);
    const videos = [];
    try {
        const url = 'http://wapi.kuwo.cn/api/www/search/searchPlayListBykeyWord' +
                    `?key=${wd}&pn=${pg}&rn=10`;
        const data = await getJson(url);
        for (const item of pickList(data)) {
            const pid = item.id;
            if (!pid) continue;
            videos.push({
                vod_id: 'pl_' + pid,
                vod_name: String(item.name || '').trim(),
                vod_pic: item.img || item.pic || '',
                vod_remarks: `歌单 · ${item.total || 0}首`
            });
        }
    } catch (e) {}
    return videos;
}

// ==================== 导出 ====================

function __jsEvalReturn() {
    return {
        init: init,
        home: home,
        homeVod: homeVod,
        category: category,
        detail: detail,
        play: play,
        search: search
    };
}

const api=__jsEvalReturn(); api.subtitle=createSsaSubtitle; api.base64=b64encode; return api;
}
/* SPDX-License-Identifier: GPL-3.0-only
 * TV-native additions, adapted from the user's Music Hub public API contracts.
 * No browser globals; no Music Hub HTTP gateway. See RESOLVER_ORDER.txt.
 */
const MH_KSALT='OIlwieks28dk2k092lksi2UIkp';
let mhKMid='',mhDailyMemory=Object.create(null);
function mhExtraReset(){mhKMid='';mhDailyMemory=Object.create(null);}
function mhBytes(s){return unescape(encodeURIComponent(String(s))).split('').map(c=>c.charCodeAt(0));}
function mhMd5(text){
  const b=mhBytes(text),n=b.length,sh=[7,12,17,22,5,9,14,20,4,11,16,23,6,10,15,21],k=[];
  for(let i=0;i<64;i++)k[i]=Math.floor(Math.abs(Math.sin(i+1))*4294967296)|0;
  b.push(128);while(b.length%64!==56)b.push(0);
  for(let i=0;i<8;i++)b.push(i<4?(n*8>>>i*8)&255:Math.floor(n/536870912)>>>((i-4)*8)&255);
  let a0=0x67452301,b0=0xefcdab89,c0=0x98badcfe,d0=0x10325476;
  for(let o=0;o<b.length;o+=64){const w=[];for(let i=0;i<16;i++)w[i]=b[o+i*4]|b[o+i*4+1]<<8|b[o+i*4+2]<<16|b[o+i*4+3]<<24;
    let a=a0,bb=b0,c=c0,d=d0;
    for(let i=0;i<64;i++){let f,g;if(i<16){f=bb&c|~bb&d;g=i;}else if(i<32){f=d&bb|~d&c;g=(5*i+1)%16;}else if(i<48){f=bb^c^d;g=(3*i+5)%16;}else{f=c^(bb|~d);g=7*i%16;}
      const v=(a+f+k[i]+w[g])|0,s=sh[Math.floor(i/16)*4+i%4],t=d;d=c;c=bb;bb=(bb+(v<<s|v>>>(32-s)))|0;a=t;
    }a0=a0+a|0;b0=b0+bb|0;c0=c0+c|0;d0=d0+d|0;
  }
  return [a0,b0,c0,d0].map(v=>[0,8,16,24].map(s=>('0'+((v>>>s)&255).toString(16)).slice(-2)).join('')).join('');
}
function mhDig(node,test){
  let best=[],score=0,visited=0;
  function visit(x,d){if(!x||typeof x!=='object'||d>7||++visited>7000)return;
    if(Array.isArray(x)){const good=x.filter(v=>v&&typeof v==='object'&&test(v));if(good.length>score){score=good.length;best=good;}if(good.length)return;x.slice(0,80).forEach(v=>visit(v,d+1));}
    else Object.keys(x).forEach(k=>visit(x[k],d+1));
  }visit(node,0);return best;
}
function mhKPic(v){return mhPic(String(v||'').replace(/\{size\}/g,'400'));}
function mhKSong(r){
  if(!r)return null;r=r.song&&r.song.hash?r.song:r;
  r=Object.assign({},r.base||{},r.audio_info||{},r);
  const id=String(r.hash||r.FileHash||r.filehash||r.Hash||'').toUpperCase();
  let name=mhText(r.songname||r.SongName||r.audio_name||r.filename||r.FileName||r.name),artist=mhText(r.singername||r.SingerName||r.author_name||r.author);
  if(!artist)artist=mhArray(r.singers||r.singerinfo||r.Singers).map(a=>mhText(a.name||a.singername)).filter(Boolean).join(' / ');
  const pos=name.indexOf(' - ');if(pos>=0){if(!artist)artist=name.slice(0,pos);name=name.slice(pos+3);}
  if(!/^[0-9A-F]{32}$/.test(id)||!name)return null;
  const album=r.album_info||{},t=r.trans_param||{};let dur=Number(r.duration||r.timelen||r.timelength||0)||0;if(dur>3600)dur/=1000;
  return {p:'kugou',id,name,artist:artist.replace(/、/g,' / '),album:mhText(r.album_name||r.albumname||album.album_name),albumId:String(r.album_id||r.albumid||album.album_id||''),aid:Number(r.album_audio_id||r.mixsongid||r.MixSongID)||0,duration:dur,pic:mhKPic(r.album_sizable_cover||r.sizable_cover||r.imgurl||r.img||r.cover||t.union_cover||album.sizable_cover),hqHash:String(r['320hash']||r.HQFileHash||'').toUpperCase(),sqHash:String(r.hash_flac||r.sqhash||r.SQFileHash||'').toUpperCase(),hrHash:String(r.hash_high||r.ResFileHash||r.hires_hash||'').toUpperCase()};
}
function mhKRows(d){return mhDig(d,x=>x.hash||x.FileHash||x.filehash||x.audio_info&&x.audio_info.hash||x.song&&x.song.hash);}
function mhKInfo(d){const a=d&&d.data||{};return mhArray(Array.isArray(a)?a:a.info||a.lists||a.list||a.songs);}
function mhKDevice(){if(!mhKMid)mhKMid='239526275778893399526700786998289824956';return mhKMid;}
async function mhKGw(path,params,body,router,base){
  const t=Math.floor(Date.now()/1000),mid=mhKDevice(),p=Object.assign({dfid:'-',mid,uuid:'-',appid:1005,clientver:20489,clienttime:t},params||{});
  const raw=body==null?'':typeof body==='string'?body:JSON.stringify(body),keys=Object.keys(p).sort();
  p.signature=mhMd5(MH_KSALT+keys.map(k=>k+'='+p[k]).join('')+raw+MH_KSALT);
  const h={'User-Agent':'Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi',dfid:'-',mid,clienttime:String(t),'kg-rc':'1','kg-rec':'1','kg-thash':'5d816a0','kg-rf':'B9EDA08A64250DEFFBCADDEE00F8F25F'};
  if(router)h['x-router']=router;if(raw)h['Content-Type']='application/json';
  return await mhRequest((base||'https://gateway.kugou.com')+path+'?'+mhQuery(p),{method:raw?'post':'get',headers:h,body:raw||undefined,timeout:8000});
}
function mhKBody(extra){const t=Date.now();return Object.assign({appid:1005,clientver:20489,clienttime:t,key:mhMd5('1005'+MH_KSALT+'20489'+t),mid:mhKDevice()},extra||{});}
async function mhKApi(path,p){
  for(const base of ['https://mobilecdnbj.kugou.com','http://mobilecdn.kugou.com'])try{const d=await mhRequest(base+path+'?'+mhQuery(Object.assign({version:9108,plat:0},p||{})),{headers:mhHeaders('kugou'),timeout:6500});if(d.status===1||d.error_code===0||d.data)return d;}catch(e){}
  throw new Error('酷狗公开接口暂不可用');
}
async function mhKCategory(section,page,e){
  let rows=[],kind='song',more=false,total=0;
  if(section==='playlists'){
    kind='playlist';const t=Math.floor(Date.now()/1000),body={appid:1005,mid:mhKDevice(),clientver:20489,platform:'android',clienttime:t,userid:0,module_id:1,page,pagesize:30,key:mhMd5('1005'+MH_KSALT+'20489'+t),special_recommend:{withtag:1,withsong:0,sort:1,ugc:1,is_selected:0,withrecommend:1,area_code:1,categoryid:mhInt(e.tag,0,0,1000000)},req_multi:1,retrun_min:5,return_special_falg:1};
    const d=await mhKGw('/v2/special_recommend',{},body,'specialrec.service.kugou.com');rows=mhDig(d,x=>(x.specialid||x.special_id)&&(x.specialname||x.name));
    if(!rows.length)rows=mhKInfo(await mhKApi('/api/v3/special/recommend',{showtype:2,sort:5,page,pagesize:30,tagid:Number(e.tag)||0}));
  }else if(section==='ranks'){
    kind='rank';const d=await mhKApi('/api/v3/rank/list',{withsong:0});mhKInfo(d).forEach(g=>{rows=rows.concat(mhArray(g.list).length?g.list:[g]);});
  }else if(section==='singers'){
    kind='singer';const d=await mhKGw('/ocean/v6/singer/list',{page,pagesize:30,sort:1,category:mhInt(e.artistCat,0,0,9)},null);rows=mhDig(d,x=>x.singerid&&x.singername);
    if(!rows.length)rows=mhKInfo(await mhKApi('/api/v3/singer/list',{classid:mhInt(e.artistCat,0,0,9),page,pagesize:30}));
  }else if(section==='new'){
    const d=await mhKGw('/musicadservice/container/v1/newsong_publish',{}, {rank_id:21608,userid:0,page,pagesize:30,tags:[]});rows=mhKRows(d);
  }else if(section==='albums'){
    kind='album';const d=await mhKGw('/musicadservice/v1/mobile_newalbum_sp',{}, {apiver:20,token:'',page,pagesize:30,withpriv:1});rows=mhDig(d,x=>(x.albumid||x.album_id)&&(x.albumname||x.album_name));
  }else if(section==='radio'){
    kind='radio';const d=await mhKGw('/v1/class_fm_song',{},mhKBody({kguid:0,platform:'android',uid:0,get_tracker:1}),'fm.service.kugou.com');rows=mhDig(d,x=>x.fmid||x.fm_id);
  }
  if(kind==='song')return mhResult(mhSongCards(mhSongsOf('kugou',rows)),page,0,rows.length>=30);
  const list=rows.map(x=>mhCard('kugou',kind,x.specialid||x.special_id||x.rankid||x.singerid||x.albumid||x.album_id||x.fmid||x.fm_id,x.specialname||x.rankname||x.singername||x.albumname||x.album_name||x.fmname||x.fm_name||x.name,mhKPic(x.imgurl||x.sizable_cover||x.flexible_cover||x.banner7url),x.intro||x.update_frequency||x.author_name||'',{fmtype:Number(x.fmtype)||2}));
  if(section==='ranks'||section==='radio')return mhSlice(list.filter(Boolean),page);
  more=rows.length>=30;return mhResult(list,page,total,more);
}
async function mhKDetail(x,limit){
  if(x.kind==='song'){const s=await mhMetadata('kugou',x.id);return mhDetailObject(x,s?[s]:[],{name:s&&s.name,pic:s&&s.pic,artist:s&&s.artist},false);}
  const out=[],cap=limit||mhConfig.maxTracks;let last='',more=false;
  if(x.kind==='radio'){
    const card=mhCards[mhId(x.p,x.kind,x.id)]||{},d=await mhKGw('/v1/app_song_list_offset',{},mhKBody({area_code:1,get_tracker:1,uid:0,data:[{fmid:x.id,fmtype:card.fmtype||2,offset:-1,size:Math.min(cap,100),singername:''}]}),'fm.service.kugou.com');
    return mhDetailObject(x,mhSongsOf('kugou',mhKRows(d)),{},false);
  }
  for(let page=1;out.length<cap&&page<=Math.ceil(cap/100);page++){
    let d;
    if(x.kind==='playlist'){
      const p={need_sort:1,module:'CloudMusic',specialid:x.id,specalidpgc:x.id,clientver:11239,pagesize:100,userid:0,page,type:0,area_code:1,appid:1005},q=mhQuery(p);
      const signature=mhMd5(MH_KSALT+q.split('&').sort().join('')+MH_KSALT);
      try{d=await mhRequest('https://gatewayretry.kugou.com/v2/get_other_list_file?'+q+'&signature='+signature,{headers:{'User-Agent':'Android9-AndroidPhone-11239-18-0-playlist-wifi','x-router':'pubsongscdn.kugou.com',mid:mhKDevice(),dfid:'-',clienttime:String(Math.floor(Date.now()/1000))}});}catch(e){}
      if(!mhKRows(d).length)d=await mhKApi('/api/v3/special/song',{specialid:x.id,page,pagesize:100});
    }else{
      const path=x.kind==='rank'?'/api/v3/rank/song':x.kind==='singer'?'/api/v3/singer/song':x.kind==='album'?'/api/v3/album/song':'';
      if(!path)throw Error('酷狗内容类型无效');const p={page,pagesize:100};p[x.kind==='rank'?'rankid':x.kind==='singer'?'singerid':'albumid']=x.id;d=await mhKApi(path,p);
    }
    const songs=mhSongsOf('kugou',mhKRows(d));if(!songs.length||songs[0].id===last)break;last=songs[0].id;out.push.apply(out,songs);more=songs.length>=100;if(!more)break;
  }
  const seen={};return mhDetailObject(x,out.filter(s=>!seen[s.id]&&(seen[s.id]=1)),{},more);
}
async function mhKSearch(keyword,page){
  let songs=[];for(const u of ['https://songsearch.kugou.com/song_search_v2?'+mhQuery({format:'json',platform:'WebFilter',keyword,page,pagesize:30}),'https://mobilecdnbj.kugou.com/api/v3/search/song?'+mhQuery({format:'json',keyword,page,pagesize:30,showtype:1,version:9108,plat:0})])try{songs=mhSongsOf('kugou',mhKRows(await mhRequest(u,{headers:mhHeaders('kugou')})));if(songs.length)break;}catch(e){}
  return mhResult(mhSongCards(songs),page,0,songs.length>=30);
}
async function mhKMetadata(id,old){
  try{const d=await mhRequest('https://m.kugou.com/app/i/getSongInfo.php?'+mhQuery({cmd:'playInfo',hash:id}),{headers:mhHeaders('kugou'),timeout:5000});
    const s=mhKSong(Object.assign({},d,{hash:id,songname:d.songName||d.songname||old&&old.name,cover:d.imgUrl||d.imgurl}));return s?mhRemember(s):old;
  }catch(e){return old;}
}
async function mhKLyric(id){
  const d=await mhRequest('https://lyrics.kugou.com/search?'+mhQuery({ver:1,man:'yes',client:'pc',hash:id}),{headers:mhHeaders('kugou'),timeout:5000});
  const rows=mhArray(d.candidates||d.data&&d.data.candidates),meta=mhSongs[mhId('kugou','track',id)];let c=rows[0];
  if(c&&meta&&meta.duration>0&&Math.abs(Number(c.duration)/1000-meta.duration)>10){const exact=rows.filter(x=>Math.abs(Number(x.duration)/1000-meta.duration)<=5).sort((a,b)=>Math.abs(Number(a.duration)/1000-meta.duration)-Math.abs(Number(b.duration)/1000-meta.duration));if(exact.length)c=exact[0];}
  if(!c||!c.id||!c.accesskey)return '';
  const r=await mhRequest('https://lyrics.kugou.com/download?'+mhQuery({ver:1,client:'pc',id:c.id,accesskey:c.accesskey,charset:'utf8',fmt:'lrc'}),{headers:mhHeaders('kugou'),timeout:5000});
  const s=String(r.content||r.lyric||'');return s.indexOf('[')>=0?s:mhBase64Utf8(s);
}

// The same named QQ channel groups as the user's HTML; tag IDs are resolved
// against today's official category catalogue instead of trusting old IDs.
const MH_CHANNELS=[
 {id:'hot',name:'热门',items:[['热歌','hot'],['网络流行',3056],['情歌',71],['KTV必点',64],['经典',59],['摇滚',41],['古风',61],['官方歌单',3317]]},
 {id:'mood',name:'心情',items:[['伤感',74],['寂寞',9],['快乐',3142],['甜蜜',20],['安静',13],['励志',16],['怀旧',136],['治愈',7]]},
 {id:'theme',name:'主题',items:[['ACG',3202],['影视',3201],['中国风',68],['古风',61],['网络歌曲',3056],['KTV热歌',64],['经典',59],['儿歌',3200]]},
 {id:'scene',name:'场景',items:[['睡前',27],['背景音乐',107],['运动',132],['学习',3248],['工作',3248],['开车',3901],['夜晚',122],['清晨',101]]},
 {id:'genre',name:'曲风',items:[['流行',3152],['摇滚',41],['R&B',43],['嘻哈',42],['电子',45],['民谣',48],['爵士',46],['轻音乐',49],['古典',47],['乡村',44],['蓝调',51],['后摇',3217]]},
 {id:'lang',name:'语言',items:[['国语',1],['粤语',146],['英语',3],['韩语',4],['日语',5],['闽南语',113],['小语种',170],['法语',149]]},
 {id:'crowd',name:'人群',items:[['校园',39],['90年代',142],['儿歌',3200],['ACG',3202],['怀旧',136],['KTV',64]]},
 {id:'instrument',name:'乐器',items:[['轻音乐',49],['古典',47],['爵士',46],['新世纪',53],['电子',45],['中国传统',3176],['世界音乐',3066],['后摇',3217]]}
];
async function mhChannelCategory(page,e){
  const g=MH_CHANNELS.find(x=>x.id===e.channelGroup)||MH_CHANNELS[0],tags=(await mhPlaylistTags()).qq;
  const aliases={'KTV必点':'KTV金曲','KTV热歌':'KTV金曲','KTV':'KTV金曲','影视':'影视原声','背景音乐':'背景音乐','网络流行':'网络歌曲','嘻哈':'说唱','国语':'华语'};
  const list=g.items.map((a,i)=>{const name=a[0],hit=tags.find(t=>t.n===(aliases[name]||name)),id=a[1]==='hot'?'hot':hit?hit.v:String(a[1]);return mhCard('qq','channel',id,name,'','QQ '+g.name+'频道');});
  // Enrich channel cards with the cover of an actual playlist, cached for five minutes.
  for(let i=0;i<list.length;i+=3)await Promise.all(list.slice(i,i+3).map(async c=>{try{const x=mhParseId(c.vod_id),r=await mhCached('channel-cover:'+x.id,()=>x.id==='hot'?mhQCategory('ranks',1,{}):mhQCategory('playlists',1,{tag:x.id}));const pl=r.list&&r.list[0];if(pl&&pl.vod_pic)c.vod_pic=pl.vod_pic;}catch(e){}}));
  return mhSlice(list,page);
}
async function mhChannelDetail(x){
  if(x.id==='hot'){
    const d=await mhQDetail({p:'qq',kind:'rank',id:'26'});d.list[0].vod_id=mhId(x.p,x.kind,x.id);return d;
  }
  const r=await mhQCategory('playlists',1,{tag:x.id}),parts=await Promise.all(r.list.slice(0,3).map(async c=>{try{return (await mhQDetail(mhParseId(c.vod_id),50)).list[0];}catch(e){return null;}}));
  const seen={},songs=[];parts.filter(Boolean).forEach(d=>String(d.vod_play_url||'').split('#').forEach(ep=>{const id=mhParseId(ep.slice(ep.lastIndexOf('$')+1));if(id&&!seen[id.id]){seen[id.id]=1;const s=mhSongs[mhId('qq','track',id.id)];if(s)songs.push(s);}}));
  return mhDetailObject(x,songs,{desc:'QQ 官方分类歌单合并 · 免登录频道'},songs.length>mhConfig.maxTracks);
}
function mhDay(){const d=new Date();return d.getFullYear()+'-'+(d.getMonth()+1)+'-'+d.getDate();}
function mhShuffle(rows,seed){
  const a=rows.slice();let n=parseInt(mhMd5(seed).slice(0,8),16)>>>0;
  for(let i=a.length-1;i>0;i--){n=(Math.imul(1664525,n)+1013904223)>>>0;const j=n%(i+1),t=a[i];a[i]=a[j];a[j]=t;}return a;
}
function mhDedupe(rows){const seen={};return rows.filter(s=>s&&s.id&&!seen[s.p+':'+s.id]&&(seen[s.p+':'+s.id]=1));}
async function mhDailySongs(p,section,page){
  const key=p+':'+section+':'+mhDay()+':'+page;if(mhDailyMemory[key])return mhDailyMemory[key];
  let songs=[];
  if(p==='qq'){
    if(section==='daily30'){
      const r=await mhQCategory('ranks',1,{}),board=r.list.find(x=>/KTV/i.test(x.vod_name))||r.list.find(x=>x.vod_id==='qq:rank:26');
      if(board){const d=await mhQDetail(mhParseId(board.vod_id),30);songs=String(d.list[0].vod_play_url).split('#').map(ep=>mhSongs[ep.split('$').pop()]).filter(Boolean);}
    }else{
      try{const d=await mhQCall('music.recommend.TrackRelationServer','GetRadarSong',{Page:section==='brush'?page+1:1,ReqType:0,FavSongs:[],EntranceSongs:[]});songs=mhSongsOf('qq',d.VecSongs);}catch(e){}
      if(section==='daily'&&songs.length<30)try{const d=await mhQCall('music.radioProxy.MbTrackRadioSvr','get_radio_track',{id:99,num:5,from:0,scene:0,song_ids:[]});songs=songs.concat(mhSongsOf('qq',d.tracks));}catch(e){}
    }
    if(songs.length<30){const d=await mhQCall('newsong.NewSongServer','get_new_song_info',{type:5});songs=songs.concat(mhSongsOf('qq',d.songlist));}
  }else if(p==='kugou'){
    try{const d=await mhKGw('/singlecardrec.service/v1/single_card_recommend',{card_id:section==='brush'?(page-1)%4+1:1,fakem:'60f7ebf1f812edbac3c63a7310001701760f',area_code:1,platform:'ios'},mhKBody({platform:'android',userid:0,fakem:'60f7ebf1f812edbac3c63a7310001701760f',area_code:1,uuid:'-',client_playlist:[],u_info:'a0c35cd40af564444b5584c2754dedec'}));songs=mhSongsOf('kugou',mhKRows(d));}catch(e){}
    if(songs.length<30){const r=await mhKCategory('ranks',1,{});for(const c of r.list.slice((page-1)%3,(page-1)%3+2)){const d=await mhKDetail(mhParseId(c.vod_id),60);songs=songs.concat(d.list[0].vod_play_url.split('#').map(ep=>mhSongs[ep.split('$').pop()]).filter(Boolean));}}
  }else if(p==='netease'){
    // Same guest strategy as Music Hub buildDailyLocal: public charts, date seed.
    const ranks=await mhNCategory('ranks',1,{}),picks=mhShuffle(ranks.list,mhDay()+':'+section+':'+page).slice(0,2);
    const groups=await Promise.all(picks.map(async c=>{try{const d=await mhNDetail(mhParseId(c.vod_id),60);return d.list[0].vod_play_url.split('#').map(ep=>mhSongs[ep.split('$').pop()]).filter(Boolean);}catch(e){return [];}}));songs=[].concat.apply([],groups);
  }else{
    const r=JSON.parse(await mhKw.category('bang',1,true,{})),picks=mhShuffle(mhArray(r.list),mhDay()+':'+section+':'+page).slice(0,2);
    const groups=await Promise.all(picks.map(async c=>{try{const id=String(c.vod_id).replace(/^bang_/,'').split('~')[0],d=await mhRequest('https://wapi.kuwo.cn/api/www/bang/bang/musicList?'+mhQuery({bangId:id,pn:1,rn:30}),{headers:mhHeaders('kuwo')});return mhArray(d.data&&d.data.musicList).map(x=>mhRemember({p:'kuwo',id:String(x.rid||String(x.musicrid||'').replace('MUSIC_','')),name:mhText(x.name),artist:mhText(x.artist),album:mhText(x.album),pic:mhPic(x.albumpic||x.pic),duration:Number(x.duration)||0}));}catch(e){return [];}}));songs=[].concat.apply([],groups);
  }
  songs=mhDedupe(songs);if(section!=='daily30'||p!=='qq')songs=mhShuffle(songs,mhDay()+':'+p+':'+section+':'+page);
  songs=songs.slice(0,30);mhDailyMemory[key]=songs;
  const keys=Object.keys(mhDailyMemory);if(keys.length>32)delete mhDailyMemory[keys[0]];return songs;
}
async function mhDailyCategory(p,section,page){
  if(page>1&&section!=='brush')return mhResult([],page,0,false);
  const songs=await mhDailySongs(p,section,page),cards=mhSongCards(songs);
  if(songs.length)cards.unshift(mhCard(p,'daily',section==='daily'?'1':section==='daily30'?'2':String(300000+page),section==='brush'?'刷歌 · 本批一起听':section==='daily30'?'Daily30 · 一起听':'今日推荐 · 一起听',songs[0].pic,songs.length+' 首 · 连续播放'));
  const r=mhResult(cards,page,songs.length,section==='brush'&&songs.length>=30);
  r.limit=31;r.total=section==='brush'?(page-1)*31+cards.length+(r.pagecount>page?31:0):cards.length;
  r.msg=section==='brush'?'免登录刷歌 · 当前批次':p==='qq'&&section==='daily30'?'QQ 官方 KTV 榜 Daily30':'免登录公开推荐 · 非账号私人推荐';return r;
}
async function mhDailyDetail(x){const n=Number(x.id),section=n===1?'daily':n===2?'daily30':n>300000&&n<=310000?'brush':'';if(!section)return {list:[]};return mhDetailObject(x,await mhDailySongs(x.p,section,section==='brush'?n-300000:1),{name:section==='brush'?'刷歌':section==='daily30'?'Daily30':'每日推荐',desc:'免登录公开推荐 · '+mhDay()},false);}

/* SPDX-License-Identifier: GPL-3.0-only
 * Direct request contracts/order from Music Hub 1.19.20; no website proxy.
 * AES below encrypts the public EAPI request, not audio or DRM containers.
 */
let mhResolveCache=Object.create(null),mhResolveOrder=[];
function mhGf(a,b){let r=0;for(;b;b>>>=1,a=(a<<1^((a&128)?283:0))&255)if(b&1)r^=a;return r;}
function mhAesHex(text,key){
  const s=[],rk=mhBytes(key);if(rk.length!==16)throw Error('AES key length');
  for(let n=0;n<256;n++){let x=0;if(n){x=1;for(let e=254,b=n;e;e>>>=1,b=mhGf(b,b))if(e&1)x=mhGf(x,b);}
    s[n]=(x^((x<<1|x>>>7)&255)^((x<<2|x>>>6)&255)^((x<<3|x>>>5)&255)^((x<<4|x>>>4)&255)^99)&255;}
  let rc=1;for(let i=16;i<176;i+=4){let t=rk.slice(i-4,i);if(i%16===0){t=[s[t[1]]^rc,s[t[2]],s[t[3]],s[t[0]]];rc=mhGf(rc,2);}for(let j=0;j<4;j++)rk[i+j]=rk[i+j-16]^t[j];}
  const b=mhBytes(text),pad=16-b.length%16;for(let i=0;i<pad;i++)b.push(pad);let out='';
  for(let o=0;o<b.length;o+=16){let a=b.slice(o,o+16);for(let i=0;i<16;i++)a[i]^=rk[i];
    for(let round=1;round<=10;round++){a=a.map(v=>s[v]);const t=a.slice();for(let r=0;r<4;r++)for(let c=0;c<4;c++)a[c*4+r]=t[((c+r)%4)*4+r];
      if(round<10)for(let c=0;c<16;c+=4){const v=a.slice(c,c+4),x=v[0]^v[1]^v[2]^v[3];for(let r=0;r<4;r++)a[c+r]=v[r]^x^mhGf(v[r]^v[(r+1)%4],2);}
      for(let i=0;i<16;i++)a[i]^=rk[round*16+i];}
    out+=a.map(v=>('0'+v.toString(16)).slice(-2)).join('');}return out.toUpperCase();
}
function mhPublicHeaders(extra){return Object.assign({'User-Agent':MH_UA,Accept:'application/json,text/plain,*/*'},extra||{});}
function mhHeader(h,key){const k=Object.keys(h||{}).find(k=>k.toLowerCase()===key.toLowerCase());return k?String(h[k]):'';}
function mhAbsolute(base,value){const u=mhUrl(value);if(u)return u;if(String(value||'').charAt(0)==='/'){const m=/^(https?:\/\/[^/]+)/.exec(base);return m?mhUrl(m[1]+value):'';}return '';}
function mhPickUrl(d){
  if(typeof d==='string')return mhAudioUrl(d.trim());if(!d||typeof d!=='object')return '';
  if(d.freeTrialInfo||d.freeTrialPrivilege||d.is_preview||d.isPreview||d.trial||d.preview)return '';
  if(d.code!=null&&[0,1,200,201].indexOf(Number(d.code))<0)return '';
  for(const k of ['url','play_url','playUrl','audioUrl','music_url','song_url','src','data','result','vipmusic','song']){const v=d[k];if(v===d)continue;
    if(Array.isArray(v)){for(const row of v.slice(0,4)){const u=mhPickUrl(row);if(u)return u;}}
    else {const u=typeof v==='string'?mhAudioUrl(v):v&&typeof v==='object'?mhPickUrl(v):'';if(u)return u;}}
  return '';
}
function mhAudioFormat(url){const m=/\.(flac|mp3|m4a|aac|ogg|wav|ape)(?:[?#]|$)/i.exec(url||'');return m?m[1].toLowerCase():'';}
async function mhResolveRequest(url,o,end){
  const left=end-Date.now();if(left<100)throw Error('解析预算耗尽');
  const r=await req(url,Object.assign({method:'get',headers:mhPublicHeaders(),timeout:Math.min(5000,left),redirect:0},o||{},{timeout:Math.min(o&&o.timeout||5000,left)}));
  if(!r)throw Error('网络无返回');return typeof r==='string'?{code:200,content:r,headers:{}}:r;
}
async function mhResolveData(url,body,headers,end){
  const r=await mhResolveRequest(url,{method:body?'post':'get',headers:mhPublicHeaders(Object.assign(body?{'Content-Type':'application/json'}:{},headers||{})),body:body?JSON.stringify(body):undefined},end);
  if(Number(r.code)<200||Number(r.code)>=300)throw Error('解析接口 HTTP 错误');return mhJson(r.content);
}
async function mhRedirectUrl(url,headers,end){
  // HEAD avoids accidentally loading an entire FLAC through the JS bridge.
  let u=url;for(let i=0;i<5;i++){
    const r=await mhResolveRequest(u,{method:'header',headers:mhPublicHeaders(headers)},end),code=Number(r.code),loc=mhHeader(r.headers,'location');
    if(code>=300&&code<400&&loc){u=mhAbsolute(u,loc);if(!mhAudioUrl(u))return '';continue;}
    if(code>=200&&code<300){const type=mhHeader(r.headers,'content-type');if(/^(audio\/|video\/|application\/octet-stream)/i.test(type))return mhAudioUrl(u);
      if(mhAudioFormat(u)&&!/html|json/i.test(type))return mhAudioUrl(u);}
    return '';
  }return '';
}
async function mhValidateAudio(u,name,end){
  if(!mhAudioUrl(u))return null;
  const r=await mhResolveRequest(u,{method:'header',headers:mhPublicHeaders()},end),code=Number(r.code),loc=mhHeader(r.headers,'location');
  if(code>=300&&code<400&&loc){u=await mhRedirectUrl(u,{},end);if(!u)return null;}
  else if(code>=200&&code<300){const ct=mhHeader(r.headers,'content-type');if(/html|json|text\/plain/i.test(ct))return null;}
  else if(code!==405&&code!==501)return null;
  const fmt=mhAudioFormat(u),degraded=mhConfig.quality!=='HQ'&&fmt!=='flac';
  return {url:u,format:fmt,provider:name,label:name+' · '+(fmt?fmt.toUpperCase():'音质待确认')+(degraded?'（回落）':''),degraded};
}
const MH_QPHP=['http://175.27.166.236/kgqq1/qq.php','https://mcp.nianxinxz.com/share/ceshi/tx.php','https://music.haitangw.cc/kgqq1/qq.php','https://musicapi.haitangw.net/kgqq1/qq.php','https://music.nxinxz.com/kgqq/tx.php'];
function mhLevels(){return mhConfig.quality==='ZQ'?['hires','lossless','exhigh']:mhConfig.quality==='SQ'?['lossless','exhigh']:['exhigh','standard'];}
function mhLx(level){return ({hires:'flac24bit',lossless:'flac',exhigh:'320k',standard:'128k'})[level]||level;}
async function mhHaitang(p,id,end){
  for(const level of mhLevels())try{const r=await mhHaitangLevel(p,id,level,end);if(r)return r;}catch(e){}return null;
}
async function mhHaitangLevel(p,id,level,end){
 const d=await mhResolveData('https://musicserver.haitangw.cc/v1/music/resolve-url',{source:p==='qq'?'tx':'kg',rid:id,level},{},end),r=await mhValidateAudio(mhPickUrl(d),'笒鬼鬼直链',end);
 return r&&(!/hires|lossless/.test(level)||r.format==='flac')?r:null;
}
async function mhQPhp(id,end){
  // PHP mirrors have no hires: quality first, then mirrors, just like qqchain.go.
  for(const level of mhConfig.quality==='HQ'?['exhigh','standard']:['lossless','exhigh','standard'])for(const base of MH_QPHP)try{
    const u=base+'?'+mhQuery({type:'mp3',id,level}),redirect=await mhRedirectUrl(u,{},end);let raw=redirect;
    if(!raw){const d=await mhResolveRequest(u,{},end);const ct=mhHeader(d.headers,'content-type');if(/^audio\//i.test(ct))continue;try{raw=mhPickUrl(mhJson(d.content));}catch(e){raw=mhAudioUrl(d.content);}}
    const r=await mhValidateAudio(raw,'长青海棠 PHP',end);if(r&&(level!=='lossless'||r.format==='flac'))return r;
  }catch(e){}return null;
}
async function mhQTang(id,meta,end){
  const d=await mhResolveData('https://tang.api.s01s.cn/music_open_api.php?'+mhQuery({msg:[meta.name,meta.artist].filter(Boolean).join(' '),type:'json',mid:id}),null,{Referer:'https://charlespikachu.github.io/musicsquare/'},end);
  let root=d;for(let i=0;i<2&&root&&!Array.isArray(root)&&root.data;i++)root=root.data;
  const rows=Array.isArray(root)?root:[root],row=rows.find(r=>r&&String(r.song_mid||r.mid)===id);
  if(!row)return null;const urls=Object.keys(row).filter(k=>/^song_play_url(?:_|$)/i.test(k)&&!/trial|preview|accom|instrument|karaoke/i.test(k)).map(k=>mhPickUrl(row[k])).filter(Boolean);
  urls.sort((a,b)=>mhConfig.quality==='HQ'?(mhAudioFormat(b)==='mp3')-(mhAudioFormat(a)==='mp3'):(mhAudioFormat(b)==='flac')-(mhAudioFormat(a)==='flac'));
  for(const u of urls){const r=await mhValidateAudio(u,'网页QQ · Tang',end);if(r)return r;}return null;
}
function mhMatchText(s){return mhText(s).toLowerCase().replace(/[\s·・\-—_\/、.,，。!！?？'"‘’“”]/g,'');}
function mhArtistParts(s){return mhText(s).split(/\s*(?:\/|&|、|;|，|,|feat\.?|ft\.?)\s*/i).map(mhMatchText).filter(Boolean).sort();}
function mhSameRecording(a,b){
  if(!a.name||!b.name||mhMatchText(a.name)!==mhMatchText(b.name))return false;
  const aa=mhArtistParts(a.artist),bb=mhArtistParts(b.artist);if(!aa.length||aa.join('|')!==bb.join('|'))return false;
  // Live/remix/伴奏/翻唱 suffixes remain in titles, never removed by normalization.
  return !a.duration||!b.duration||Math.abs(a.duration-b.duration)<=5;
}
async function mhKuwoMatch(meta,end){
  if(!mhConfig.allowMatchedFallback||!meta.name||!meta.artist)return null;
  const d=await mhResolveData('https://search.kuwo.cn/r.s?'+mhQuery({client:'kt',pn:0,rn:20,all:meta.name+' '+meta.artist,vipver:1,ft:'music',encoding:'utf8',rformat:'json',mobi:1}),null,{},end);
  const hit=mhArray(d.abslist).find(x=>mhSameRecording(meta,{name:x.SONGNAME,artist:x.ARTIST,duration:Number(x.DURATION)||0}));if(!hit)return null;
  const id=String(hit.MUSICRID||hit.DC_TARGETID||'').replace(/^MUSIC_/,'');if(!/^\d+$/.test(id))return null;
  for(const br of mhConfig.quality==='HQ'?['320kmp3','128kmp3']:['2000kflac','320kmp3','128kmp3'])try{
    const d=await mhResolveData('https://nmobi.kuwo.cn/mobi.s?'+mhQuery({f:'web',user:0,source:'kwplayer_ar_4.4.2.7_B_nuoweida_vh.apk',rid:id,bitrate:parseInt(br,10),type:'convert_url_with_sign',format:br.indexOf('flac')>=0?'flac':'mp3'}),null,{},end);
    const r=await mhValidateAudio(mhPickUrl(d),'酷我严格匹配',end);if(r){r.matchedPlatform='kuwo';r.matchedId=id;return r;}
  }catch(e){}return null;
}
async function mhNEapi(id,level,end){
  const endpoint='/eapi/song/enhance/player/url/v1',path=endpoint.replace('/eapi/','/api/'),text=JSON.stringify({ids:[Number(id)],level,encodeType:'flac'}),digest=mhMd5('nobody'+path+'use'+text+'md5forencrypt');
  const body=mhQuery({params:mhAesHex(path+'-36cd479b6b5-'+text+'-36cd479b6b5-'+digest,'e82ckenh8dichen8')});
  const r=await mhResolveRequest('https://interface3.music.163.com'+endpoint,{method:'post',headers:mhHeaders('netease',{'Content-Type':'application/x-www-form-urlencoded'}),body},end);return mhPickUrl(mhJson(r.content));
}
function mhNBackends(id,lv){const lx=mhLx(lv);return [
 ['官方 EAPI',end=>mhNEapi(id,lv,end)],
 ['ChKsZ','https://api.chksz.top/api/163_music',{id,level:lv},null,{Referer:'https://cp.chksz.top/'}],
 ['笒鬼鬼','https://api.cenguigui.cn/api/netease/music_v1.php',{id,type:'json',level:lv}],
 ['ikun','https://c.wwwweb.top/music/url',null,{source:'wy',musicId:id,quality:lx},{'User-Agent':'lx-music-request/2.9.0','X-Api-Key':''}],
 ['toubiec','https://wyapi.toubiec.cn/api/music/url',null,{id,level:lv},{Origin:'https://wyapi.toubiec.cn',Referer:'https://wyapi.toubiec.cn/'}],
 ['星海主','https://yy.zddyr.top/lx/api/',{source:'netease',songmid:id,quality:lx}],
 ['星海备','https://zrcdy.dpdns.org/lx/api/api.php',{source:'netease',songmid:id,quality:lx}],
 ['bugpk','https://api.bugpk.com/api/163_music',{type:'json',ids:id,level:lv}],
 ['妖狐','https://api.yaohud.cn/api/music/wyvip',{id,level:lx}],
 ['lxmusic88','https://88.lxmusic.xn--fiqs8s/lxmusicv4/url/wy/'+id+'/'+lv,null,null,{'x-request-key':'lxmusic'}],
 ['Huibq','https://lxmusicapi.onrender.com/url/wy/'+id+'/'+lx,null,null,{'X-Request-Key':'share-v3'}],
 ['聚合API','https://api.music.lerd.dpdns.org/wy',null,{musicInfo:{songmid:id},type:lx}],
 ['残像','https://api.canxiang.cn/api/wyymusic',{token:'canxiang_token_2026',type:lx,id}],
 ['GDStudio',end=>mhGD(id,lv,end)],
 ['HYW','http://103.79.184.97/api/music/url',{source:'wy',songId:id,quality:lx,key:'MOLAN-BAIJI'},null,{'X-Card-Key':'MOLAN-BAIJI'}],
 ['溯音163','https://oiapi.net/api/Music_163',{id,type:'json'},null,null,true],
 ['FFAPI','https://ffapi.cn/int/v2/songurl',{url:'https://music.163.com/song?id='+id},null,null,true],
 ['念心直链','http://music.nxinxz.com/wy.php',{id,level:lx,type:'mp3'},null,null,true]
 ];}
async function mhGD(id,lv,end){
 const dom='music.gdstudio.xyz',t=await mhResolveRequest('https://'+dom+'/time',{},end),ts=String(Number(t.content)||Date.now()).slice(0,9),s=mhMd5(dom+'|20260510|'+ts+'|'+encodeURIComponent(id)).slice(-8).toUpperCase();
 const r=await mhResolveRequest('https://'+dom+'/api.php',{method:'post',headers:mhPublicHeaders({'Content-Type':'application/x-www-form-urlencoded',Origin:'https://'+dom,Referer:'https://'+dom+'/','X-Requested-With':'XMLHttpRequest'}),body:mhQuery({types:'url',id,source:'netease',br:lv==='standard'?128:lv==='exhigh'?320:999,s})},end);return mhPickUrl(mhJson(r.content));
}
async function mhTask(t,end){
  if(typeof t[1]==='function')return t[1](end);
  const u=t[1]+(t[2]?'?'+mhQuery(t[2]):'');
  if(/type=mp3/.test(u)){const r=await mhRedirectUrl(u,t[4],end);if(r)return r;}
  const d=await mhResolveData(u,t[3],t[4],end);return mhPickUrl(d);
}
async function mhRunTasks(tasks,end,preferFlac){
  let lower=null;for(const t of tasks){if(end-Date.now()<100)break;try{const r=await mhValidateAudio(await mhTask(t,end),t[0],end);if(!r)continue;if(!preferFlac||r.format==='flac')return r;if(!lower)lower=r;}catch(e){}}
  return lower;
}
async function mhNResolve(id,meta,end){
  if(meta.dj){
   try{const r=await mhValidateAudio(await mhRedirectUrl('https://api.qijieya.cn/meting/?'+mhQuery({server:'netease',type:'url',id}),{},end),'电台网页 · Meting',end);if(r)return r;}catch(e){}
   return mhNPublic(id,end);
  }
  // Music Hub's enabled Molan wrapper precedes the original HTML chain.
  for(const lv of mhLevels())try{const t=mhNBackends(id,lv).find(t=>t[0]==='ikun'),r=await mhValidateAudio(await mhTask(t,Math.min(end,Date.now()+6500)),'墨澜 · ikun',end);if(r&&(!/hires|lossless/.test(lv)||r.format==='flac'))return r;}catch(e){}
  const stellarEnd=Math.min(end,Date.now()+16000),tasks=[];
  mhLevels().forEach((lv,i)=>mhNBackends(id,lv,stellarEnd).forEach(t=>{if(!t[5]||!i)tasks.push(t);}));
  let r=await mhRunTasks(tasks,stellarEnd,mhConfig.quality!=='HQ');if(r)return r;
  try{r=await mhValidateAudio(await mhRedirectUrl('https://api.qijieya.cn/meting/?'+mhQuery({server:'netease',type:'url',id}),{},end),'网页接口 · Meting',end);if(r)return r;}catch(e){}
  for(const lv of mhLevels())try{r=await mhValidateAudio(await mhNEapi(id,lv,end),'网易云官方 EAPI',end);if(r)return r;}catch(e){}
  const third=[];for(const lv of mhLevels()){
    third.push(['TMetu','https://music.tmetu.cn/api/',{miss:'songAll',id,level:lv,withLyric:'true'},null,{Referer:'https://music.tmetu.cn/'}],['青旅音乐','https://music.qinglvai.top/api/index.php',{route:'/music/url',id,level:lv,use:'play',source:'netease'}],['ChKsz','https://api.chksz.com/api/163_music',{id,level:lv},null,{Referer:'https://cp.chksz.top/'}],['XingMian','https://api.xingmian.bbroot.com/API/netease_music_api.php',{id,quality:({hires:'Hi-Res',lossless:'无损',exhigh:'高音质'})[lv]||'无损',apikey:mhBase64Utf8('YzY2OWY2MTI3ODAzMDEwZTQ3ZjI0ZjI2ZGEyY2Q4Y2ZkY2JkNjdiOWIzNzVjZmZhZjNjMzk1MjQ1N2Y4MTMzZA==')}]);
  }
  mhLevels().forEach((lv,i)=>{
    third.push(['FFAPI普通','https://ffapi.cn/int/v1/netease_url',{id,quality:lv}]);
    for(const [name,base] of [['JFJT','https://dm.jfjt.cc/'],['QJQQ','https://metings.qjqq.cn/']])third.push([name,async end=>{const r=await mhResolveRequest(base+'Song_V1',{method:'post',headers:mhPublicHeaders({Referer:base,Origin:base.slice(0,-1),'Content-Type':'application/x-www-form-urlencoded'}),body:mhQuery({url:id,level:lv,type:'json'})},end);return mhPickUrl(mhJson(r.content));}]);
    third.push(['GDStudio普通','https://music-api.gdstudio.xyz/api.php',{types:'url',id,source:'netease',br:lv==='lossless'||lv==='hires'?999:320}]);
    if(!i)third.push(['LZMHHH',async end=>{const base='https://music.lzmhhh.com/',r=await mhResolveRequest(base+'api/music/url',{method:'post',headers:mhPublicHeaders({Referer:base,Origin:base.slice(0,-1),'Content-Type':'application/x-www-form-urlencoded'}),body:mhQuery({id,type:'wy'})},end);return mhPickUrl(mhJson(r.content));}]);
  });
  r=await mhRunTasks(third,end,mhConfig.quality!=='HQ');if(r)return r;
  r=await mhNPublic(id,end);if(r)return r;
  try{return await mhValidateAudio(await mhRedirectUrl(MH_NE+'/song/media/outer/url?id='+id+'.mp3',{},end),'网易云外链保底',end);}catch(e){return null;}
}
async function mhNPublic(id,end){
 const body=mhQuery({ids:JSON.stringify([Number(id)]),br:999000});
 for(const host of ['https://interface3.music.163.com',MH_NE])for(const method of ['post','get'])try{
  const u=host+'/api/song/enhance/player/url'+(method==='get'?'?'+body:''),r=await mhResolveRequest(u,{method,headers:mhHeaders('netease',method==='post'?{'Content-Type':'application/x-www-form-urlencoded'}:{}),body:method==='post'?body:undefined},end),v=await mhValidateAudio(mhPickUrl(mhJson(r.content)),'网易云公开接口',end);if(v)return v;
 }catch(e){}return null;
}
const MH_AK_KEYS=['UE9WTUhLSklYOEE3SUdIMkZNMVA=','WE1VS0lBSjNQOExQWDNQOTcxS1U=','N0tUSTUyVDdWTE9EUjZTVDM3UFQ='];
const MH_XY_KEYS=['c2stMDE0YWQ2NjQ2NWQ0MmZlMzZkNWM5NDc5ZjY4MzdiYjE=','c2stNmNhODBkOTJjZTY3NGY5MzBkY2Q0NWQ5ZDYzYzNlMTY='];
async function mhFormK(base,id,end,warm){
 const h=mhPublicHeaders({Referer:base,Origin:base.replace(/\/$/,''),'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest'});
 if(warm){const r=await mhResolveRequest(base,{headers:mhPublicHeaders({Referer:base})},end),cookies=mhHeader(r.headers,'set-cookie');if(cookies)h.Cookie=cookies.split(/,(?=[^;,]+=)/).map(x=>x.split(';')[0]).join('; ');}
 const r=await mhResolveRequest(base,{method:'post',headers:h,body:mhQuery({input:id,filter:'id',type:'kugou',page:1})},end),d=mhJson(r.content),row=mhArray(d.data||d)[0];
 return row?mhAbsolute(base,row.url)||mhPickUrl(row):'';
}
async function mhKResolve(id,meta,end){
  let r=null;
  const q=mhLevels().map(mhLx).map(q=>q==='flac24bit'?'hires':q);
  const molanEnd=Math.min(end,Date.now()+14000);
  for(let i=0;i<q.length;i++){
   try{r=await mhHaitangLevel('kugou',id,mhLevels()[i],molanEnd);if(r)return r;}catch(e){}
   const quality=q[i],molan=[['墨澜 · 白姬','http://103.79.184.97/api/music/url',{source:'kg',songId:id,quality,key:'MOLAN-BAIJI'},null,{'X-Card-Key':'MOLAN-BAIJI'}],['墨澜 · 星海','https://yy.zddyr.top/lx/api/',{source:'kg',quality,mainHash:id}]];
   for(const t of molan)try{r=await mhValidateAudio(await mhTask(t,molanEnd),t[0],molanEnd);if(r&&(!/hires|flac/.test(quality)||r.format==='flac'))return r;}catch(e){}
  }
  const original=q.map(quality=>['HYW 公益','http://103.79.184.97/api/music/url',{source:'kg',platform:'kg',songId:id,hash:id,quality,key:'6C1F-53W0-GRKI-EVFG'},null,{'User-Agent':'lx-music-mobile/2.0.0','X-Card-Key':'6C1F-53W0-GRKI-EVFG'}]).concat(q.map(quality=>['星海后端','https://yy.zddyr.top/lx/api/',{source:'kg',songmid:id,mainHash:id,hash:id,quality,albumId:meta.albumId||''}]));
  r=await mhRunTasks(original,Math.min(end,Date.now()+12000),false);if(r)return r;
  r=await mhHaitang('kugou',id,Math.min(end,Date.now()+7000));if(r)return r;
  try{r=await mhKuwoMatch(meta,end);if(r)return r;}catch(e){}
  const rest=[];for(const br of mhConfig.quality==='HQ'?['2','1']:['6','5','4','3','2','1'])rest.push(['317AK','https://api.317ak.com/api/yinyue/kugougl',{ckey:mhBase64Utf8(MH_AK_KEYS[Number(br)%3]),i:id,br,type:'json',lrc:1}]);
  MH_XY_KEYS.forEach(key=>rest.push(['闲鱼 Hi-Res','https://apii.xianyuw.cn/api/v1/kugou-music-search',{id,key:mhBase64Utf8(key),no_url:0,br:'hires'}]));
  rest.push(['LZMHHH',async end=>{const base='https://music.lzmhhh.com/',r=await mhResolveRequest(base+'api/music/url',{method:'post',headers:mhPublicHeaders({Referer:base,Origin:base.slice(0,-1),'Content-Type':'application/x-www-form-urlencoded'}),body:mhQuery({id,type:'kg'})},end);return mhPickUrl(mhJson(r.content));}],['小白音乐',end=>mhFormK('https://music.90svip.cn/',id,end)],['Tom 聚合',end=>mhFormK('https://music.tom.moe/',id,end)],['煎饼搜',end=>mhFormK('https://www.jbsou.cn/',id,end,true)]);
  return mhRunTasks(rest,end,false);
}
async function mhDirectResolve(p,id,meta){
  const key=p+':'+id+':'+mhConfig.quality,c=mhResolveCache[key];if(c&&Date.now()-c.t<300000)return c.v;
  const end=Date.now()+mhConfig.resolverBudgetMs;let r=null;
  if(p==='qq'){
    try{r=await mhHaitang(p,id,Math.min(end,Date.now()+14000));}catch(e){}
    if(!r)try{r=await mhQTang(id,meta,Math.min(end,Date.now()+10000));}catch(e){}
    if(!r)try{r=await mhQPhp(id,Math.min(end,Date.now()+12000));}catch(e){}
    if(!r)try{r=await mhKuwoMatch(meta,end);}catch(e){}
    if(!r&&end>Date.now())try{r=await mhOfficialResolve(p,id,meta);}catch(e){}
  }else if(p==='netease')try{r=await mhNResolve(id,meta,end);}catch(e){}
  else if(p==='kugou')try{r=await mhKResolve(id,meta,end);}catch(e){}
  if(r)mhPut(mhResolveCache,mhResolveOrder,key,{t:Date.now(),v:r},80);return r;
}

/* SPDX-License-Identifier: GPL-3.0-only
 * MV always returns mediaType=video and never a music object.
 * Videos are sent to the TV's existing player, not to music immersion.
 */
let mhMvCards=Object.create(null),mhMvOrder=[];
function mhMvReset(){mhMvCards=Object.create(null);mhMvOrder=[];mhKwWebSession=null;}
function mhMvCard(p,id,name,pic,artist){const c=mhCard(p,'mv',id,name,pic,'MV'+(artist?' · '+mhText(artist):''));if(c)mhPut(mhMvCards,mhMvOrder,c.vod_id,c,120);return c;}
let mhKwWebSession=null;
// Anonymous browser-request token, not account authorization or media decryption.
function mhKwSecret(value,key,salt){
 let digits=Array.from(key).map(c=>c.charCodeAt(0)).join(''),stride=Math.floor(digits.length/5);
 const multiplier=parseInt([1,2,3,4,5].map(i=>digits.charAt(i*stride)).join(''),10),increment=Math.ceil(key.length/2),modulus=2147483647;
 if(!(multiplier>=2))return '';
 salt=salt==null?Math.round(Math.random()*1e9)%1e8:salt;digits+=salt;
 while(digits.length>10)digits=String(parseInt(digits.slice(0,10),10)+parseInt(digits.slice(10),10));
 let state=(multiplier*Number(digits)+increment)%modulus,encoded='';
 for(let i=0;i<value.length;i++){const byte=value.charCodeAt(i)^Math.floor(state/modulus*255);encoded+=('0'+byte.toString(16)).slice(-2);state=(multiplier*state+increment)%modulus;}
 return encoded+('00000000'+salt.toString(16)).slice(-8);
}
async function mhKwMvUrls(id){
 const key='Hm_Iuvt_cdb524f42f23cer9b268564v7y735ewrq2324';
 for(let retry=0;retry<2;retry++)try{
  if(!mhKwWebSession||Date.now()-mhKwWebSession.time>600000){
   const r=await req('https://www.kuwo.cn/',{method:'get',headers:mhPublicHeaders({Referer:'https://www.kuwo.cn/'}),timeout:9000}),m=new RegExp('(?:^|[,;]\\s*)'+key+'=([^;,]+)').exec(mhHeader(r&&r.headers,'set-cookie'));
   if(!m)throw Error('酷我匿名网页会话暂不可用');
   mhKwWebSession={cookie:key+'='+m[1],value:decodeURIComponent(m[1]),time:Date.now()};
  }
  const h=mhPublicHeaders({Referer:'https://www.kuwo.cn/',Cookie:mhKwWebSession.cookie,Secret:mhKwSecret(mhKwWebSession.value,key)});
  const d=await mhRequest('https://www.kuwo.cn/api/v1/www/music/playUrl?'+mhQuery({mid:id,type:'mv',httpsStatus:1}),{headers:h});
  const streams=mhMvStreams(d);if(streams.length)return streams;
  mhKwWebSession=null;
 }catch(e){mhKwWebSession=null;}
 return [];
}
async function mhMvCategory(p,page,e){
 const area=String(e.mvArea||'all');let list=[],total=0,more=false;
 if(p==='qq'){
  const d=await mhQCall('MvService.MvInfoProServer','GetAllocMvInfo',{start:(page-1)*30,size:30,version_id:7,area_id:({all:15,cn:16,hk:17,eu:18,jp:19,kr:20})[area]||15,order:1},'web');
  list=mhArray(d.list||d.mvlist).map(x=>mhMvCard(p,x.vid||x.v_id,x.name||x.title||x.mv_name,x.picurl||x.cover_pic||x.pic||x.mv_pic_url,x.singer_name||mhArray(x.singers||x.singer_list).map(s=>s.name||s.singer_name).join(' / ')));
  total=Number(d.total||d.sum)||0;more=list.length>=30;
 }else if(p==='netease'){
  const names={all:'全部',cn:'内地',hk:'港台',eu:'欧美',jp:'日本',kr:'韩国'},d=await mhNCall('/api/mv/all',{limit:30,offset:(page-1)*30,area:names[area]||'全部',type:'全部',order:'最新'});
  list=mhArray(d.data).map(x=>mhMvCard(p,x.id,x.name,x.cover,x.artistName||mhArray(x.artists).map(a=>a.name).join(' / ')));total=Number(d.count)||0;more=!!d.hasMore;
 }else if(p==='kugou'){
  const d=await mhKApi('/api/v3/mv/list',{area:({all:0,cn:1,hk:2,eu:3,jp:4,kr:5})[area]||0,sort:2,page,pagesize:30});
  list=mhKInfo(d).map(x=>mhMvCard(p,String(x.hash||'').toUpperCase(),x.filename||x.name,mhKPic(x.imgurl),x.singername));total=Number(d.data&&d.data.total)||0;more=total?page*30<total:list.length>=30;
 }else{
  const pid=({all:236682871,cn:236682731,hk:236682731,eu:236682735,jp:236742444,kr:236742444})[area]||236682871;
  const d=await mhRequest('https://wapi.kuwo.cn/api/www/music/mvList?'+mhQuery({pid,pn:page,rn:30}),{headers:mhHeaders('kuwo')}),a=d.data||{};
  list=mhArray(a.mvlist).map(x=>mhMvCard(p,x.id||x.rid,x.name,x.pic,x.artist));total=Number(a.total)||0;more=page*30<total;
 }
 return mhResult(list,page,total,more);
}
function mhMvDetail(x){const card=mhMvCards[mhId(x.p,'mv',x.id)]||mhCards[mhId(x.p,'mv',x.id)]||{};return {list:[{vod_id:mhId(x.p,'mv',x.id),vod_name:card.vod_name||'MV',vod_pic:card.vod_pic||'',vod_content:card.vod_remarks||MH_NAMES[x.p]+' MV',vod_play_from:MH_NAMES[x.p]+' MV',vod_play_url:mhLabel(card.vod_name||'播放 MV')+'$'+mhId(x.p,'video',x.id)}]};}
function mhMvStreams(node){
 const out=[],seen={};
 function add(raw,label,score,vkey){let u=mhUrl(raw);if(!u||seen[u]||/^https?:\/\/[^/]+\/?(?:[?#].*)?$/.test(u)||/preview|try[_-]?url/i.test(u)||/\.(?:mp3|m4a|aac|ogg|flac|wav|ape|qmc\w*|mflac\w*|mgg\w*)(?:[?#]|$)/i.test(u))return;if(vkey&&u.indexOf('vkey=')<0)u+=(u.indexOf('?')<0?'?':'&')+'vkey='+encodeURIComponent(vkey);seen[u]=1;out.push({url:u,label,score:Number(score)||0});}
 function walk(x,path,depth){if(!x||depth>6)return;if(typeof x==='string'){if(/url|down|play|m3u8|purl/i.test(path))add(x,path.replace(/.*\./,''),0);return;}
  if(Array.isArray(x)){x.slice(0,30).forEach(v=>walk(v,path,depth+1));return;}if(typeof x!=='object')return;
  if(x.code!=null&&[0,1,1000,200].indexOf(Number(x.code))<0)return;
  const score=Number(x.r||x.filetype||x.fileType||x.bitrate)||0,label=x.r?x.r+'P':path.match(/sq|rq|hd|sd|super|high|low/i)?.[0]||'MV';
  for(const k of ['url','downurl','play_url','freeflow_url','comm_url','wifi_url','purl','m3u8']){const pool=x[k];(Array.isArray(pool)?pool:[pool]).forEach(u=>{if(typeof u==='string')add(u,label,score,x.vkey);else if(u&&typeof u==='object')add(u.url||u.purl,label,score,x.vkey);});}
  Object.keys(x).filter(k=>!['url','purl','downurl','play_url','freeflow_url','comm_url','wifi_url','m3u8'].includes(k)).forEach(k=>walk(x[k],path+'.'+k,depth+1));
 }walk(node,'MV',0);return out.sort((a,b)=>b.score-a.score).slice(0,6);
}
async function mhQMvUrls(id){
 for(const [module,param] of [
  ['music.stream.MvUrlProxy',{vids:[id],request_type:10003,addrtype:3,format:264,maxFiletype:60}],
  ['gosrf.Stream.MvUrlProxy',{vids:[id],request_typet:10003,addrtype:3}],
  ['gosrf.Stream.MvUrlProxy',{vids:[id],from:'h5.playsong'}],
  ['music.stream.MvUrlProxy',{vids:[id],request_type:10001,addrtype:3}]
 ])try{const d=await mhQCall(module,'GetMvUrls',param,'web'),streams=mhMvStreams(d[id]||d.data&&d.data[id]||d);if(streams.length)return streams;}catch(e){}return [];
}
async function mhMvPlay(x){
 try{let streams=[];
  if(x.p==='qq')streams=await mhQMvUrls(x.id);
  else if(x.p==='netease'){for(const r of [1080,720,480]){const d=await mhNCall('/api/song/enhance/play/mv/url',{id:x.id,r});streams=mhMvStreams(d);if(streams.length)break;}}
  else if(x.p==='kugou'){
   try{const p={backupdomain:1,cmd:123,ext:'mp4',ismp3:0,hash:x.id,pid:1,type:1,key:mhMd5(x.id+'57ae12eb6890223e355ccfcb74edf70d'+'1005'+mhKDevice()+'0')};streams=mhMvStreams(await mhKGw('/v2/interface/index',p,null,'trackermv.kugou.com'));}catch(e){}
   if(!streams.length)streams=mhMvStreams(await mhRequest('https://m.kugou.com/app/i/mv.php?'+mhQuery({cmd:100,hash:x.id,ismp3:0}),{headers:mhHeaders('kugou')}));
  }else{
   streams=await mhKwMvUrls(x.id);
  }
  const card=mhMvCards[mhId(x.p,'mv',x.id)]||mhCards[mhId(x.p,'mv',x.id)]||{},h=mhHeaders(x.p);delete h.Cookie;
  return {parse:0,playUrl:'',url:streams.length?[].concat.apply([],streams.map((s,i)=>[(s.label==='MV'?'MV '+(i+1):s.label),s.url])):'',header:h,mediaType:'video',platform:x.p,title:card.vod_name||'MV',msg:streams.length?'':MH_NAMES[x.p]+' MV 暂时没有可用播放地址'};
 }catch(e){return {parse:0,url:'',mediaType:'video',msg:MH_NAMES[x.p]+' MV：'+e.message};}
}

/* SPDX-License-Identifier: GPL-3.0-only
 * 影音TV 音乐库 2.1 — native CatVod/QuickJS, no DOM or WebView.
 * Public catalog adapters adapted from the user's Music Hub 1.19.20.
 * A build step embeds the existing Kuwo r3 spider in an isolated closure.
 */
const MH_NAMES = {qq:'QQ音乐', kuwo:'酷我音乐', netease:'网易云音乐', kugou:'酷狗音乐'};
const MH_SHORT_NAMES = {qq:'QQ', kuwo:'酷我', netease:'网易', kugou:'酷狗'};
const MH_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';
const MH_NE = 'https://music.163.com';
const MH_QQ = 'https://u.y.qq.com/cgi-bin/musicu.fcg';
const MH_SECTIONS = {
  qq:[['daily','每日推荐'],['daily30','Daily30'],['brush','刷歌'],['channels','QQ频道'],['playlists','推荐歌单'],['ranks','官方榜单'],['new','新歌首发'],['singers','热门歌手'],['mv','MV']],
  kuwo:[['daily','每日推荐'],['daily30','Daily30'],['brush','刷歌'],['playlists','精选歌单'],['ranks','榜单速览'],['singers','歌手库'],['mv','MV']],
  netease:[['daily','每日推荐'],['daily30','Daily30'],['brush','刷歌'],['playlists','精选歌单'],['ranks','热门榜单'],['new','新歌首发'],['albums','新碟上架'],['singers','热门歌手'],['dj','精选电台'],['styles','曲风漫游'],['mv','MV']],
  kugou:[['daily','每日推荐'],['daily30','Daily30'],['brush','刷歌'],['playlists','推荐歌单'],['ranks','官方榜单'],['new','新歌速递'],['albums','新碟上架'],['singers','热门歌手'],['radio','电台'],['mv','MV']]
};
let mhConfig = {}, mhKw, mhActive = 'qq';
let mhSongs = Object.create(null), mhSongOrder = [], mhCards = Object.create(null), mhCardOrder = [];
let mhLists = Object.create(null), mhListOrder = [], mhTags = null;

function mhText(v) {
  if(typeof v !== 'string' && typeof v !== 'number') return '';
  return String(v).replace(/<[^>]*>/g,'').replace(/&amp;/g,'&').replace(/&nbsp;/g,' ').replace(/&#39;/g,"'").replace(/&quot;/g,'"').trim();
}
function mhLabel(v) { return mhText(v).replace(/[$#]/g,' ').replace(/\s+/g,' ').trim(); }
function mhUrl(v) {
  v=mhText(v); if(v.indexOf('//')===0)v='https:'+v;
  // No credentials, control characters, local file URLs or executable schemes.
  return /^https?:\/\/[^\s/@]+(?::\d+)?(?:[/?#]|$)/i.test(v) && !/[\x00-\x20\\]/.test(v)?v:'';
}
function mhPic(v) {
  v=mhUrl(v).replace(/^http:/i,'https:');
  if(v.indexOf('music.126.net')>=0 && v.indexOf('?')<0)v+='?param=400y400';
  return v;
}
function mhQPic(mid,singer) { return /^[A-Za-z0-9]+$/.test(mid||'')?'https://y.gtimg.cn/music/photo_new/T00'+(singer?'1':'2')+'R400x400M000'+mid+'.jpg':''; }
function mhInt(v,d,min,max) { v=Number(v);return isFinite(v)?Math.max(min,Math.min(max,Math.floor(v))):d; }
function mhArray(v) { return Array.isArray(v)?v:[]; }
function mhQuery(p) { return Object.keys(p||{}).map(k=>encodeURIComponent(k)+'='+encodeURIComponent(p[k]==null?'':p[k])).join('&'); }
function mhPut(map,order,key,value,max) {
  if(!map[key])order.push(key);map[key]=value;
  while(order.length>max)delete map[order.shift()];
  return value;
}
function mhId(p,kind,id) { return p+':'+kind+':'+encodeURIComponent(String(id)); }
function mhParseId(value) {
  const m=/^(qq|kuwo|netease|kugou):(playlist|rank|singer|album|song|track|dj|style|legacy|channel|mv|video|radio|daily):(.+)$/.exec(String(value||''));
  if(!m)return null;
  let id;try{id=decodeURIComponent(m[3]);}catch(e){return null;}
  if(id.length>150 || /[\s$#\x00-\x1f]/.test(id))return null;
  if(m[1]==='qq' && !/^[A-Za-z0-9]+$/.test(id))return null;
  if(m[1]==='netease' && !/^\d+$/.test(id))return null;
  if(m[1]==='kugou' && !((/^(song|track|mv|video)$/.test(m[2])&&/^[0-9A-Fa-f]{32}$/.test(id))||(!/^(song|track|mv|video)$/.test(m[2])&&/^\d+$/.test(id))))return null;
  if(m[1]==='kuwo' && !/^(?:\d+|(?:song_|pl_|bang_)\d+(?:~\d+)?)$/.test(id))return null;
  return {p:m[1],kind:m[2],id:id};
}
function mhHeaders(p,extra) {
  const h={'User-Agent':MH_UA,Referer:p==='qq'?'https://y.qq.com/':p==='netease'?MH_NE+'/':p==='kugou'?'https://www.kugou.com/':'https://www.kuwo.cn/'};
  const c=mhConfig.cookies && mhConfig.cookies[p];
  if(typeof c==='string' && c && !/[\r\n]/.test(c))h.Cookie=c;
  return Object.assign(h,extra||{});
}
function mhJson(raw) {
  if(raw && typeof raw==='object')return raw;
  raw=String(raw||'').replace(/^\uFEFF/,'').trim();
  try{return JSON.parse(raw);}catch(e){}
  const m=/^[A-Za-z_$][\w.$]*\(([\s\S]*)\)\s*;?$/.exec(raw);
  if(m){try{return JSON.parse(m[1]);}catch(e){}}
  throw new Error('接口未返回 JSON');
}
async function mhRequest(url,options) {
  if(!mhUrl(url))throw new Error('接口地址无效');
  const r=await req(url,Object.assign({method:'get',timeout:9000},options||{}));
  if(!r)throw new Error('网络请求未返回');
  if(r.code!=null && (Number(r.code)<200||Number(r.code)>=300))throw new Error('网络请求失败 HTTP '+Number(r.code));
  return mhJson(r.content!==undefined?r.content:r.body!==undefined?r.body:r.data!==undefined?r.data:r);
}
async function mhQCall(module,method,param,profile) {
  const comm=profile==='web'?{ct:24,cv:4747474,format:'json',platform:'yqq.json',uin:0,g_tk:5381}:profile==='desktop'?{ct:19,cv:2201,format:'json'}:{ct:11,cv:14090008,v:14090008,tmeAppID:'qqmusic',format:'json'};
  const d=await mhRequest(MH_QQ,{method:'post',headers:mhHeaders('qq',{'Content-Type':'application/json'}),body:JSON.stringify({comm:comm,req_0:{module:module,method:method,param:param||{}}})});
  const r=d.req_0;
  if(Number(d.code||0)!==0 || !r || Number(r.code||0)!==0 || !r.data)throw new Error('QQ 接口暂时不可用');
  return r.data;
}
async function mhNCall(path,params,post) {
  const q=mhQuery(params), h=mhHeaders('netease');
  const d=await mhRequest(MH_NE+path+(post?'':q?'?'+q:''),{method:post?'post':'get',headers:post?Object.assign(h,{'Content-Type':'application/x-www-form-urlencoded'}):h,body:post?q:undefined});
  if(d.code!=null && Number(d.code)!==200)throw new Error('网易云接口暂时不可用或需要登录');
  return d;
}
function mhQSong(s) {
  s=s&&(s.songInfo||s.Track||s.musicData||s); if(!s)return null;
  const id=mhText(s.mid||s.songmid||s.songMid), name=mhText(s.title||s.name||s.songname);
  if(!/^[A-Za-z0-9]+$/.test(id)||!name)return null;
  const a=s.album||{}, amid=mhText(a.mid||a.pmid||s.albummid);
  return {p:'qq',id:id,name:name,artist:mhArray(s.singer||s.singers).map(a=>mhText(a.name)).filter(Boolean).join(' / '),album:mhText(a.title||a.name||s.albumname),pic:mhPic(a.pic||s.pic||s.cover)||mhQPic(amid),mediaMid:mhText(s.file&&(s.file.media_mid||s.file.mediaMid)||s.media_mid||s.strMediaMid||id),numericId:String(s.id||s.songid||0),duration:Number(s.interval)||0};
}
function mhNSong(s) {
  s=s&&(s.song||s);if(!s)return null;
  const id=mhText(s.id||s.songId), name=mhText(s.name||s.songName);
  if(!/^\d+$/.test(id)||!name)return null;
  const a=s.al||s.album||{};
  return {p:'netease',id:id,name:name,artist:mhArray(s.ar||s.artists).map(a=>mhText(a.name)).filter(Boolean).join(' / '),album:mhText(a.name),pic:mhPic(a.picUrl||s.picUrl),duration:(Number(s.dt||s.duration)||0)/1000};
}
function mhRemember(s) {
  if(!s)return null;
  const key=mhId(s.p,'track',s.id), old=mhSongs[key]||{};
  // An incomplete later response must not erase a previously known cover/name.
  const merged=Object.assign({},old,s);
  ['name','artist','album','pic','mediaMid','lyric'].forEach(k=>{if(!merged[k]&&old[k])merged[k]=old[k];});
  return mhPut(mhSongs,mhSongOrder,key,merged,600);
}
function mhSongsOf(p,rows) {
  const out=[],seen=Object.create(null);
  mhArray(rows).forEach(r=>{const s=p==='qq'?mhQSong(r):p==='kugou'?mhKSong(r):mhNSong(r);if(s&&!seen[s.id]){seen[s.id]=true;out.push(mhRemember(s));}});
  return out;
}
function mhCard(p,kind,id,name,pic,note,extra) {
  const key=mhId(p,kind,id);
  if(!mhParseId(key)||!mhText(name))return null;
  const card=Object.assign({vod_id:key,vod_name:mhText(name),vod_pic:mhPic(pic),vod_remarks:mhText(note)},extra||{});
  mhPut(mhCards,mhCardOrder,key,card,180);return card;
}
function mhSongCards(songs) { return songs.map(s=>mhCard(s.p,'song',s.id,s.name,s.pic,s.artist)).filter(Boolean); }
function mhResult(list,page,total,hasMore) {
  list=mhArray(list).filter(Boolean);page=mhInt(page,1,1,10000);
  const size=30, count=Number(total)||0;
  return {list:list,page:page,pagecount:hasMore===true?Math.max(page+1,Math.ceil(count/size)):page,limit:size,total:count||((page-1)*size+list.length)};
}
function mhSlice(list,page) { return mhResult(list.slice((page-1)*30,page*30),page,list.length,page*30<list.length); }
async function mhCached(key,loader,ttl) {
  const c=mhLists[key];if(c&&Date.now()-c.t<(ttl||300000))return c.v;
  const v=await loader();
  if(v && (!Array.isArray(v)||v.length))mhPut(mhLists,mhListOrder,key,{t:Date.now(),v:v},40);
  return v;
}
async function mhPlaylistTags() {
  if(mhTags)return mhTags;
  const wanted=mhPlatforms();
  const out={qq:[{n:'全部',v:'all'}],netease:[{n:'全部',v:'全部'}],kuwo:[{n:'最热',v:'hot'},{n:'最新',v:'new'}],kugou:[{n:'推荐',v:'0'}]};
  await Promise.all([
    (async()=>{if(wanted.indexOf('qq')<0)return;try{const d=await mhRequest('https://c.y.qq.com/splcloud/fcgi-bin/fcg_get_diss_tag_conf.fcg?format=json&inCharset=utf8&outCharset=utf-8&g_tk=5381',{headers:mhHeaders('qq')});mhArray(d.data&&d.data.categories).forEach(g=>mhArray(g.items).forEach(x=>{if(x.categoryId&&x.categoryName)out.qq.push({n:mhText(x.categoryName),v:String(x.categoryId)});}));}catch(e){}})(),
    (async()=>{if(wanted.indexOf('netease')<0)return;try{const d=await mhNCall('/api/playlist/catalogue');mhArray(d.sub).forEach(x=>{if(x.name)out.netease.push({n:mhText(x.name),v:mhText(x.name)});});}catch(e){['华语','欧美','日语','韩语','粤语','流行','摇滚','民谣','电子','轻音乐','古风','影视原声','学习','运动','治愈'].forEach(n=>out.netease.push({n:n,v:n}));}})(),
    (async()=>{if(wanted.indexOf('kuwo')<0)return;try{const d=JSON.parse(await mhKw.home(true));const f=d.filters&&d.filters.playlist&&d.filters.playlist[0];if(f&&f.value)out.kuwo=f.value;}catch(e){}})(),
    (async()=>{if(wanted.indexOf('kugou')<0)return;try{const d=await mhKGw('/pubsongs/v1/get_tags_by_type',{}, {tag_type:'collection',tag_id:0,source:3});mhDig(d,x=>x.tag_id!=null&&(x.tag_name||x.name)).forEach(x=>{if(Number(x.tag_id))out.kugou.push({v:String(x.tag_id),n:mhText(x.tag_name||x.name)});});}catch(e){}})()
  ]);
  Object.keys(out).forEach(p=>{const seen={};out[p]=out[p].filter(x=>{if(seen[x.v])return false;seen[x.v]=1;return true;}).slice(0,70);});
  mhTags=out;return out;
}
async function init(ext) {
  let c={};try{c=typeof ext==='string'?JSON.parse(ext||'{}'):ext||{};}catch(e){}
  // CatVod __jsEvalReturn scripts receive {stype, skey, ext}, unlike ESM spiders.
  if(c && c.ext!==undefined){try{c=typeof c.ext==='string'?JSON.parse(c.ext||'{}'):c.ext||{};}catch(e){c={};}}
  const platform=MH_NAMES[MH_BUILD_PLATFORM]?MH_BUILD_PLATFORM:MH_NAMES[c.platform]?c.platform:'';
  mhConfig={platform:platform,quality:['HQ','SQ','ZQ'].indexOf(c.quality)>=0?c.quality:'SQ',cookies:c.cookies||{},maxTracks:mhInt(c.maxTracks,300,30,1000),searchPlatform:platform||(MH_NAMES[c.searchPlatform]?c.searchPlatform:'all'),resolverBudgetMs:mhInt(c.resolverBudgetMs,45000,12000,90000),allowMatchedFallback:c.allowMatchedFallback!==false};
  mhExtraReset();mhMvReset();mhResolveCache=Object.create(null);mhResolveOrder=[];
  mhSongs=Object.create(null);mhSongOrder=[];mhCards=Object.create(null);mhCardOrder=[];mhLists=Object.create(null);mhListOrder=[];mhTags=null;mhActive='qq';
  mhKw=createKuwo((url,opts)=>req(String(url).replace(/^http:\/\/wapi\.kuwo\.cn\//,'https://wapi.kuwo.cn/'),opts));
  await mhKw.init();
}
function mhPlatforms() { return mhConfig.platform?[mhConfig.platform]:Object.keys(MH_NAMES); }
function mhCategoryTarget(tid,extend) {
  const parts=String(tid||'').split('/'),p=parts[0];
  if(!MH_NAMES[p] || mhPlatforms().indexOf(p)<0 || parts.length>2)return null;
  const section=parts.length===2?parts[1]:(MH_SECTIONS[p].some(x=>x[0]===extend.section)?extend.section:MH_SECTIONS[p][0][0]);
  if(!MH_SECTIONS[p].some(x=>x[0]===section))return null;
  // Top-level category ID wins over stale filters restored by the host.
  return {p:p,section:section};
}
async function home(filter) {
  const classes=[],filters={},ps=mhPlatforms();
  const tags=filter?await mhPlaylistTags():{};
  ps.forEach(p=>{
    const all=[{key:'tag',name:'歌单分类',value:tags[p]||[]}];
    // Build per-platform options, then attach only the options relevant to each tab.
    if(p==='qq')all.push({key:'area',name:'歌手地区',value:[['-100','全部'],['200','内地'],['2','港台'],['5','欧美'],['4','日本'],['3','韩国']].map(x=>({v:x[0],n:x[1]}))},{key:'sex',name:'歌手类型',value:[['-100','全部'],['0','男歌手'],['1','女歌手'],['2','组合']].map(x=>({v:x[0],n:x[1]}))});
    if(p==='netease')all.push({key:'artistCat',name:'歌手分类',value:[['1001','华语男'],['1002','华语女'],['1003','华语组合'],['2001','欧美男'],['2002','欧美女'],['2003','欧美组合'],['6001','日本男'],['6002','日本女'],['6003','日本组合'],['7001','韩国男'],['7002','韩国女'],['7003','韩国组合'],['4001','其他男'],['4002','其他女'],['4003','其他组合']].map(x=>({v:x[0],n:x[1]}))},{key:'newArea',name:'新歌地区',value:[['0','全部'],['7','华语'],['96','欧美'],['8','日本'],['16','韩国']].map(x=>({v:x[0],n:x[1]}))});
    if(p==='kuwo')all.push({key:'artistCat',name:'歌手分类',value:[['1','华语男'],['2','华语女'],['3','华语组合'],['4','日韩男'],['5','日韩女'],['6','日韩组合'],['7','欧美男'],['8','欧美女'],['9','欧美组合'],['0','其他']].map(x=>({v:x[0],n:x[1]}))});
    if(p==='qq')all.push({key:'channelGroup',name:'频道分类',value:MH_CHANNELS.map(g=>({v:g.id,n:g.name}))});
    if(p==='kugou')all.push({key:'artistCat',name:'歌手分类',value:[['0','全部'],['1','华语男'],['2','华语女'],['3','华语组合'],['4','日韩男'],['5','日韩女'],['6','日韩组合'],['7','欧美男'],['8','欧美女'],['9','欧美组合']].map(x=>({v:x[0],n:x[1]}))});
    if(p!=='kuwo')all.push({key:'mvArea',name:'MV地区',value:[['all','全部'],['cn','内地'],['hk','港台'],['eu','欧美'],['jp','日本'],['kr','韩国']].map(x=>({v:x[0],n:x[1]}))});
    MH_SECTIONS[p].forEach(s=>{
      const keys=s[0]==='playlists'?['tag']:s[0]==='singers'?(p==='qq'?['area','sex']:['artistCat']):s[0]==='new'&&p==='netease'?['newArea']:s[0]==='channels'?['channelGroup']:s[0]==='mv'?['mvArea']:[];
      const id=p+'/'+s[0],options=filter?all.filter(f=>keys.indexOf(f.key)>=0&&f.value.length):[];
      const entry={type_id:id,type_name:(ps.length>1?MH_SHORT_NAMES[p]+'·':'')+s[1]};
      if(options.length){entry.filters=options;}
      classes.push(entry);
    });
  });
  // Support hosts reading filters from either Result.filters or Class.filters.
  classes.forEach(c=>{if(c.filters)filters[c.type_id]=c.filters;});
  return JSON.stringify({class:classes,filters:filters});
}
async function homeVod() { return category(mhPlatforms()[0]+'/playlists',1,false,{}); }
async function category(tid,pg,filter,extend) {
  const page=mhInt(pg,1,1,10000);let e=extend||{};
  if(typeof e==='string'){try{e=JSON.parse(e);}catch(err){e={};}}
  if(!e||typeof e!=='object'||Array.isArray(e))e={};
  const target=mhCategoryTarget(tid,e);
  if(!target)return JSON.stringify(mhResult([],page,0,false));
  const p=target.p,section=target.section;
  mhActive=p;
  try{
    if(['daily','daily30','brush'].indexOf(section)>=0)return JSON.stringify(await mhDailyCategory(p,section,page));
    if(section==='mv')return JSON.stringify(await mhMvCategory(p,page,e));
    if(section==='channels')return JSON.stringify(await mhChannelCategory(page,e));
    return JSON.stringify(p==='qq'?await mhQCategory(section,page,e):p==='netease'?await mhNCategory(section,page,e):p==='kugou'?await mhKCategory(section,page,e):await mhKwCategory(section,page,e));
  }
  catch(err){return JSON.stringify(Object.assign(mhResult([],page,0,false),{msg:MH_NAMES[p]+'：'+err.message}));}
}
async function mhQCategory(section,page,e) {
  if(section==='playlists') {
    const tag=e.tag||'all';let d,rows,total,more;
    if(tag==='all') {
      d=await mhQCall('music.playlist.PlaylistSquare','GetRecommendFeed',{From:(page-1)*30,Size:30});rows=mhArray(d.List).map(x=>x.Playlist&&x.Playlist.basic).filter(Boolean);more=!!d.HasMore;
    }else{
      const id=mhInt(tag,10000000,1,100000000),url='https://c.y.qq.com/splcloud/fcgi-bin/fcg_get_diss_by_tag.fcg?'+mhQuery({picmid:1,g_tk:5381,loginUin:0,hostUin:0,format:'json',inCharset:'utf8',outCharset:'utf-8',platform:'yqq.json',needNewCode:0,categoryId:id,sortId:3,sin:(page-1)*30,ein:page*30-1});
      d=await mhRequest(url,{headers:mhHeaders('qq')});if(Number(d.code||0)!==0)throw new Error('歌单分类接口暂不可用');rows=mhArray(d.data&&d.data.list);total=Number(d.data&&d.data.sum)||0;more=page*30<total;
    }
    const list=rows.map(x=>{const c=x.cover||{};return mhCard('qq','playlist',x.tid||x.dissid||x.id,x.title||x.dissname,mhPic(typeof c==='object'?c.default_url:c)||x.imgurl,x.creator&&(x.creator.nick||x.creator.name)||'QQ 歌单');});
    return mhResult(list,page,total,more);
  }
  if(section==='ranks') {
    const list=await mhCached('qq:ranks',async()=>{let d;try{d=await mhQCall('music.musicToplist.Toplist','GetAll');}catch(err){d=await mhQCall('musicToplist.ToplistInfoServer','GetAll',{},'web');}
      const out=[];mhArray(d.group).forEach(g=>mhArray(g.toplist).forEach(x=>{if(!/MV|视频/i.test(x.title||''))out.push(mhCard('qq','rank',x.topId||x.id,x.title,x.headPicUrl||x.frontPicUrl||x.picUrl,x.updateTime||x.period||g.groupName));}));return out.filter(Boolean);});
    return mhSlice(list,page);
  }
  if(section==='new') {
    const type=mhInt(e.newType,5,1,6),songs=await mhCached('qq:new:'+type,async()=>{const d=await mhQCall('newsong.NewSongServer','get_new_song_info',{type:type});return mhSongsOf('qq',d.songlist);});
    return mhSlice(mhSongCards(songs),page);
  }
  const d=await mhQCall('music.musichallSinger.SingerList','GetSingerListIndex',{area:mhInt(e.area,-100,-100,200),sex:mhInt(e.sex,-100,-100,2),genre:-100,index:-100,sin:(page-1)*80,cur_page:page});
  const list=mhArray(d.singerlist).map(x=>mhCard('qq','singer',x.singer_mid||x.mid,x.singer_name||x.name,x.singer_pic||mhQPic(x.singer_mid||x.mid,true),'QQ 歌手'));
  // The upstream singer endpoint fixes pages at 80, not at the general 30-card size.
  const total=Number(d.total)||0,r=mhResult(list,page,total,list.length>0&&(total?page*80<total:list.length>=80));r.limit=80;r.pagecount=total?Math.ceil(total/80):r.pagecount;return r;
}
async function mhNCategory(section,page,e) {
  if(section==='playlists') {
    const d=await mhNCall('/api/playlist/list',{cat:e.tag||'全部',order:'hot',offset:(page-1)*30,limit:30,total:true});
    return mhResult(mhArray(d.playlists).map(x=>mhCard('netease','playlist',x.id,x.name,x.coverImgUrl,x.creator&&x.creator.nickname)),page,d.total,!!d.more);
  }
  if(section==='ranks') {
    const list=await mhCached('netease:ranks',async()=>{const d=await mhNCall('/api/toplist/detail');return mhArray(d.list).map(x=>mhCard('netease','rank',x.id,x.name,x.coverImgUrl,x.updateFrequency));});return mhSlice(list,page);
  }
  if(section==='new') {
    const area=mhInt(e.newArea,0,0,96),songs=await mhCached('netease:new:'+area,async()=>{const d=await mhNCall('/api/v1/discovery/new/songs',{areaId:area,total:true});return mhSongsOf('netease',d.data);});return mhSlice(mhSongCards(songs),page);
  }
  if(section==='albums') {
    const d=await mhNCall('/api/album/new',{limit:30,offset:(page-1)*30,area:'ALL'});
    return mhResult(mhArray(d.albums).map(x=>mhCard('netease','album',x.id,x.name,x.picUrl,x.artist&&x.artist.name)),page,d.total,page*30<Number(d.total));
  }
  if(section==='singers') {
    const d=await mhNCall('/api/artist/list',{categoryCode:mhInt(e.artistCat,1001,1001,7003),initial:-1,offset:(page-1)*30,limit:30});
    return mhResult(mhArray(d.artists).map(x=>mhCard('netease','singer',x.id,x.name,x.picUrl||x.img1v1Url,(x.musicSize||'')+' 首歌曲')),page,0,!!d.more);
  }
  if(section==='dj') {
    const list=await mhCached('netease:dj',async()=>{const d=await mhNCall('/api/djradio/recommend/v1');return mhArray(d.djRadios).map(x=>mhCard('netease','dj',x.id,x.name,x.picUrl,x.dj&&x.dj.nickname));});return mhSlice(list,page);
  }
  const list=await mhCached('netease:styles',async()=>{const d=await mhNCall('/api/tag/list/get'),out=[];
    function walk(rows,depth){if(depth>2)return;mhArray(rows).forEach(x=>{if(x.tagId&&x.tagName)out.push(mhCard('netease','style',x.tagId,x.tagName,x.picUrl,'曲风漫游'));walk(x.childrenTags,depth+1);});}
    walk(d.data,0);return out.filter(Boolean);});return mhSlice(list,page);
}
function mhKwPrefix(result,detailMode) {
  const d=typeof result==='string'?JSON.parse(result):result;
  mhArray(d.list).forEach(x=>{
    x.vod_id=mhId('kuwo','legacy',x.vod_id);x.vod_pic=mhPic(x.vod_pic);
    if(detailMode && x.vod_play_url)x.vod_play_url=String(x.vod_play_url).split('$$$').map(line=>line.split('#').slice(0,mhConfig.maxTracks).map(ep=>{const at=ep.lastIndexOf('$');return at<0?'':mhLabel(ep.slice(0,at))+'$'+mhId('kuwo','track',ep.slice(at+1));}).filter(Boolean).join('#')).join('$$$');
  });return d;
}
async function mhKwCategory(section,page,e) {
  const tid=section==='playlists'?'playlist':section==='ranks'?'bang':/^[0-9]$/.test(String(e.artistCat))?String(e.artistCat):'1';
  const r=mhKwPrefix(await mhKw.category(tid,page,true,{tag:e.tag||'hot'}));
  // Existing r3's 9999 pages were placeholders. Stop on a short/empty page.
  const list=mhArray(r.list),total=Number(r.total)||0;
  if(total===999999 || Number(r.pagecount)===9999){r.pagecount=list.length>=30?page+1:page;r.total=(page-1)*30+list.length+(list.length>=30?30:0);r.limit=30;}
  return r;
}
function mhDetailObject(parsed,songs,info,partial) {
  const card=mhCards[mhId(parsed.p,parsed.kind,parsed.id)]||{},cap=mhConfig.maxTracks;
  songs=songs.slice(0,cap);
  const episodes=songs.map(s=>mhLabel(s.name+(s.artist?' - '+s.artist:''))+'$'+mhId(s.p,'track',s.id));
  return {list:[{vod_id:mhId(parsed.p,parsed.kind,parsed.id),vod_name:mhText(info.name)||card.vod_name||MH_NAMES[parsed.p],vod_pic:mhPic(info.pic)||card.vod_pic||songs[0]&&songs[0].pic||'',vod_content:(mhText(info.desc)||MH_NAMES[parsed.p]+' · 原生音乐资源库')+(partial?'（本次加载 '+songs.length+' 首）':''),vod_remarks:songs.length+' 首',vod_actor:mhText(info.artist),vod_play_from:MH_NAMES[parsed.p],vod_play_url:episodes.join('#')}]};
}
async function mhQDetail(x,limit) {
  let songs=[],info={},total=0;const cap=limit||mhConfig.maxTracks;
  if(x.kind==='song') {const s=await mhMetadata(x.p,x.id);songs=s?[s]:[];info={name:s&&s.name,pic:s&&s.pic,artist:s&&s.artist};}
  else if(x.kind==='playlist') {
    let first='';
    for(let page=0;page<Math.ceil(cap/100);page++) {
      const d=await mhQCall('srf_diss_info.DissInfoServer','CgiGetDiss',{disstid:Number(x.id),num:Math.min(100,cap-songs.length),orderlist:1,page_no:page,onlysonglist:page?1:0,enc_host_uin:''},'web');
      const a=d.dirinfo||d.dirInfo||{},rows=mhSongsOf('qq',d.songlist||d.songList);
      if(page===0){info={name:a.title||a.dissname,pic:a.picurl||a.logo,desc:a.desc,artist:a.host_nick||a.nickname};total=Number(a.songnum||a.song_num||d.total_song_num)||0;}
      if(!rows.length||rows[0].id===first)break;first=rows[0].id;songs=songs.concat(rows);
      if(rows.length<100 || songs.length>=cap || total&&songs.length>=total)break;
    }
  }else if(x.kind==='rank'||x.kind==='singer') {
    let last='';const rank=x.kind==='rank',size=rank?100:30;
    for(let offset=0;offset<cap;offset+=size) {
      const d=await mhQCall(rank?'music.musicToplist.Toplist':'musichall.song_list_server',rank?'GetDetail':'GetSingerSongList',rank?{topId:Number(x.id),offset:offset,num:Math.min(size,cap-offset),withTags:true}:{singerMid:x.id,order:1,number:Math.min(size,cap-offset),begin:offset});
      const a=d.data||d.topinfo||{},rows=mhSongsOf('qq',d.songInfoList||d.songList||d.songlist);
      if(offset===0){info={name:a.title||a.titleDetail,pic:a.headPicUrl||a.frontPicUrl,desc:a.intro};total=Number(a.totalNum||a.total_num||d.totalNum)||0;}
      if(!rows.length||rows[0].id===last)break;last=rows[0].id;songs=songs.concat(rows);
      if(rows.length<size||total&&songs.length>=total)break;
    }
  }else throw new Error('QQ 尚未接入这个内容类型');
  const seen={};songs=songs.filter(s=>!seen[s.id]&&(seen[s.id]=1));return mhDetailObject(x,songs,info,total>songs.length);
}
async function mhNSongDetails(ids) {
  const all=[];
  for(let i=0;i<ids.length;i+=100){const d=await mhNCall('/api/song/detail',{ids:JSON.stringify(ids.slice(i,i+100).map(Number))});all.push.apply(all,mhSongsOf('netease',d.songs));}
  return all;
}
async function mhNDetail(x,limit) {
  let songs=[],info={},partial=false;const cap=limit||mhConfig.maxTracks;
  if(x.kind==='song'){const s=await mhMetadata(x.p,x.id);songs=s?[s]:[];info={name:s&&s.name,pic:s&&s.pic,artist:s&&s.artist};}
  else if(x.kind==='playlist'||x.kind==='rank') {
    let d;try{d=await mhNCall('/api/v6/playlist/detail',{id:x.id,n:cap,s:0});}catch(e){d=await mhNCall('/api/playlist/detail',{id:x.id,n:cap,s:0});}
    const pl=d.playlist||d.result;if(!pl)throw new Error('歌单内容暂时不可用');
    info={name:pl.name,pic:pl.coverImgUrl,desc:pl.description,artist:pl.creator&&pl.creator.nickname};
    songs=mhSongsOf('netease',pl.tracks);const ids=mhArray(pl.trackIds).map(v=>String(v.id||v)).filter(v=>/^\d+$/.test(v)).slice(0,cap);
    if(ids.length) {
      const have={};songs.forEach(s=>{have[s.id]=s;});const missing=ids.filter(id=>!have[id]);
      if(missing.length)(await mhNSongDetails(missing)).forEach(s=>{have[s.id]=s;});
      songs=ids.map(id=>have[id]).filter(Boolean); // Preserve playlist order, never reverse it.
    }
    partial=Number(pl.trackCount||mhArray(pl.trackIds).length)>cap;
  }else if(x.kind==='album') {
    const d=await mhNCall('/api/v1/album/'+x.id);songs=mhSongsOf('netease',d.songs);const a=d.album||{};info={name:a.name,pic:a.picUrl,desc:a.description,artist:a.artist&&a.artist.name};
  }else if(x.kind==='singer') {
    const d=await mhNCall('/api/artist/'+x.id);songs=mhSongsOf('netease',d.hotSongs);const a=d.artist||{};info={name:a.name,pic:a.picUrl||a.img1v1Url,desc:a.briefDesc,artist:a.name};
  }else if(x.kind==='dj') {
    const d=await mhNCall('/api/dj/program/byradio',{radioId:x.id,offset:0,limit:Math.min(cap,100),asc:false});
    songs=mhSongsOf('netease',mhArray(d.programs).map(p=>p.mainSong)).map(s=>mhRemember(Object.assign({},s,{dj:true})));info={name:d.programs&&d.programs[0]&&d.programs[0].radio&&d.programs[0].radio.name};partial=!!d.more;
  }else if(x.kind==='style') {
    const d=await mhNCall('/api/style-tag/home/song',{cursor:0,size:Math.min(cap,100),tagId:x.id,sort:0});
    const a=d.data||{},rows=mhArray(a.songs||a.songList||a.items||d.songs);songs=mhSongsOf('netease',rows.map(s=>s.songInfo||s.song||s));partial=!!a.hasMore;
  }else throw new Error('网易云尚未接入这个内容类型');
  return mhDetailObject(x,songs,info,partial);
}
async function detail(ids) {
  const raw=Array.isArray(ids)?ids[0]:ids,x=mhParseId(raw);
  if(!x || x.kind==='track'||x.kind==='video')return JSON.stringify({list:[]});
  try {
    if(x.kind==='mv')return JSON.stringify(mhMvDetail(x));
    if(x.kind==='daily')return JSON.stringify(await mhDailyDetail(x));
    if(x.kind==='channel')return JSON.stringify(await mhChannelDetail(x));
    return JSON.stringify(x.p==='kuwo'?mhKwPrefix(await mhKw.detail(x.kind==='song'?'song_'+x.id:x.id),true):x.p==='qq'?await mhQDetail(x):x.p==='kugou'?await mhKDetail(x):await mhNDetail(x));
  }
  catch(e){return JSON.stringify({list:[{vod_id:String(raw),vod_name:MH_NAMES[x.p]+' · 加载失败',vod_content:e.message,vod_play_from:MH_NAMES[x.p],vod_play_url:''}]});}
}
async function mhMetadata(p,id) {
  const key=mhId(p,'track',id),old=mhSongs[key];if(old&&old.name&&old.pic&&(p!=='qq'||old.mediaMid))return old;
  try {
    if(p==='qq'){const d=await mhQCall('music.pf_song_detail_svr','get_song_detail_yqq',{song_mid:id},'web');return mhRemember(mhQSong(d.track_info))||old;}
    if(p==='kugou')return await mhKMetadata(id,old);
    return (await mhNSongDetails([id]))[0]||old;
  }catch(e){return old;}
}
function mhBase64Utf8(v) {
  // QuickJS has no Node Buffer; decode UTF-8 without depending on atob.
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',str=String(v||'').replace(/\s/g,''),bytes=[];let bits=0,value=0;
  for(let i=0;i<str.length;i++){const n=alphabet.indexOf(str[i]);if(n<0)continue;value=(value<<6)|n;bits+=6;if(bits>=8){bits-=8;bytes.push((value>>bits)&255);}}
  try{return decodeURIComponent(bytes.map(b=>'%'+('0'+b.toString(16)).slice(-2)).join(''));}catch(e){return '';}
}
async function mhLyric(p,id) {
  try {
    if(p==='kugou')return await mhKLyric(id);
    if(p==='netease'){const d=await mhNCall('/api/song/lyric',{id:id,lv:-1,kv:-1,tv:-1});return d.lrc&&d.lrc.lyric||'';}
    const d=await mhRequest('https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?'+mhQuery({songmid:id,format:'json',g_tk:5381,nobase64:1,inCharset:'utf8',outCharset:'utf-8'}),{headers:mhHeaders('qq'),timeout:5000});
    let l=mhText(d.lyric);if(l&&l.indexOf('[')<0)l=mhBase64Utf8(l);return l;
  }catch(e){return '';}
}
function mhAudioUrl(v) {
  const u=mhUrl(v);return u && !/(?:preview|try[_-]?url|RS02|(?:^|\/)C400|\.(?:m3u8|mpd|mflac\w*|mgg\w*|qmc\w*)(?:[?#]|$))/i.test(u)?u:'';
}
async function mhOfficialResolve(p,id,meta) {
  if(p==='netease') {
    const d=await mhNCall('/api/song/enhance/player/url',{ids:JSON.stringify([Number(id)]),br:320000},true),a=mhArray(d.data)[0];
    if(a && Number(a.code||200)===200 && !a.freeTrialInfo && !a.freeTrialPrivilege && mhAudioUrl(a.url))return {url:a.url,label:'网易云官方 '+Math.round(Number(a.br||128000)/1000)+'K',provider:'official',format:mhText(a.type)};
    return null;
  }
  const mid=meta&&meta.mediaMid||id,uinCookie=mhConfig.cookies&&mhConfig.cookies.qq||'',um=/(?:^|;\s*)(?:uin|wxuin|qqmusic_uin)=o?(\d+)/.exec(uinCookie),uin=um?um[1]:'0';
  const body={comm:{uin:Number(uin)||0,format:'json',ct:24,cv:0},req_0:{module:'vkey.GetVkeyServer',method:'CgiGetVkey',param:{guid:String(Date.now()),songmid:[id,id],filename:['M800'+mid+'.mp3','M500'+mid+'.mp3'],songtype:[0,0],uin:uin,loginflag:uin==='0'?0:1,platform:'20'}}};
  const d=await mhRequest(MH_QQ,{method:'post',headers:mhHeaders('qq',{'Content-Type':'application/json'}),body:JSON.stringify(body)}),a=d.req_0&&d.req_0.data;
  if(!a)return null;
  const host=mhUrl(mhArray(a.sip)[0])||'https://dl.stream.qqmusic.qq.com/';
  for(const item of mhArray(a.midurlinfo)) {if(item.subcode!=null&&Number(item.subcode)!==0)continue;const u=mhAudioUrl(/^https?:/.test(item.purl||'')?item.purl:host.replace(/\/?$/,'/')+(item.purl||''));if(item.purl&&u)return {url:u,label:/M800/.test(item.filename||item.purl)?'QQ 官方 320K':'QQ 官方 128K',provider:'official',format:'mp3'};}
  return null;
}
async function play(flag,id,flags) {
  const x=mhParseId(id);if(x&&x.kind==='video')return JSON.stringify(await mhMvPlay(x));
  if(!x||x.kind!=='track')return JSON.stringify({parse:0,url:'',msg:'歌曲 ID 无效'});
  if(x.p==='kuwo') {
    const d=JSON.parse(await mhKw.play(flag,x.id,flags));
    if(d.music)d.music.id=mhId('kuwo','track',x.id);d.platform='kuwo';return JSON.stringify(d);
  }
  const metaTask=mhMetadata(x.p,x.id),lyricTask=mhLyric(x.p,x.id);
  let meta=await metaTask||{name:'',artist:'',album:'',pic:''};
  const found=await mhDirectResolve(x.p,x.id,meta),lyric=await lyricTask;
  const playbackHeader=mhHeaders(found&&found.matchedPlatform||x.p);delete playbackHeader.Cookie;
  const result={parse:0,playUrl:'',url:found?[found.label,found.url]:'',header:found?playbackHeader:{},mediaType:'audio',platform:x.p,title:meta.name||'',artist:meta.artist||'',album:meta.album||'',artwork:meta.pic||'',cover:meta.pic||'',lyric:lyric,music:{id:mhId(x.p,'track',x.id),title:meta.name||'',artist:meta.artist||'',album:meta.album||'',artwork:meta.pic||'',lyric:lyric}};
  if(!found)result.msg=MH_NAMES[x.p]+'直连解析未返回完整音源，接口可能限流或本曲不可用';
  else result.audioInfo={format:found.format||'',provider:found.provider,degraded:!!found.degraded,matchedPlatform:found.matchedPlatform||'',matchedId:found.matchedId||''};
  // SSA remains available in the original player; immersion receives exact raw LRC.
  if(lyric)try{const ssa=mhKw.subtitle(lyric);if(ssa)result.subs=[{name:'歌词',format:'text/x-ssa',selected:true,url:'data:text/x-ssa;base64,'+mhKw.base64(ssa)}];}catch(e){}
  return JSON.stringify(result);
}
async function mhQSearch(keyword,page) {
  const param={searchid:String(Date.now())+String(Math.floor(Math.random()*1000000)).padStart(6,'0'),query:keyword,search_type:0,num_per_page:30,page_num:page,highlight:false,grp:true,selectors:{},vec_selectors:[]};
  const d=await mhQCall('music.search.SearchCgiService','DoSearchForQQMusicMobile',param,'desktop');
  const body=d.body||{},bucket=body.item_song||{},rows=Array.isArray(bucket)?bucket:mhArray(bucket.items||bucket.list||d.song&&d.song.list);
  const list=mhSongCards(mhSongsOf('qq',rows));return mhResult(list,page,bucket.total_num||d.meta&&d.meta.sum,list.length>=30);
}
async function mhNSearch(keyword,page) {
  const d=await mhNCall('/api/search/get/web',{s:keyword,type:1,offset:(page-1)*30,limit:30}),a=d.result||{};
  const songs=mhSongsOf('netease',a.songs),missing=songs.filter(s=>!s.pic);
  if(missing.length)try{await mhNSongDetails(missing.map(s=>s.id));}catch(e){}
  return mhResult(mhSongCards(songs.map(s=>mhSongs[mhId('netease','track',s.id)]||s)),page,a.songCount,page*30<Number(a.songCount));
}
async function search(keyword,quick,pg) {
  const k=mhText(keyword).slice(0,120),page=mhInt(pg,1,1,1000);if(!k)return JSON.stringify({list:[]});
  let ps=mhConfig.searchPlatform==='all'?Object.keys(MH_NAMES):[mhConfig.searchPlatform],kw=k;
  const prefix=/^(QQ|酷我|酷狗|网易云|网易)[:：]\s*(.+)$/i.exec(k);
  if(prefix){ps=[/^QQ$/i.test(prefix[1])?'qq':prefix[1]==='酷我'?'kuwo':prefix[1]==='酷狗'?'kugou':'netease'];kw=prefix[2];}
  if(mhConfig.platform&&ps[0]!==mhConfig.platform)return JSON.stringify({list:[],msg:'当前为'+MH_NAMES[mhConfig.platform]+'独立资源库，请切换对应站源搜索'});
  const results=await Promise.all(ps.map(async p=>{try{return p==='qq'?await mhQSearch(kw,page):p==='netease'?await mhNSearch(kw,page):p==='kugou'?await mhKSearch(kw,page):mhKwPrefix(await mhKw.search(kw,quick,page));}catch(e){return {list:[],msg:MH_NAMES[p]+'搜索暂不可用'};}}));
  const list=[];let more=false;
  // Interleave independent platforms. Same titles are not merged into wrong IDs.
  const max=Math.max.apply(null,results.map(r=>mhArray(r.list).length));
  for(let i=0;i<max;i++)results.forEach((r,j)=>{const x=r.list&&r.list[i];if(x){x.vod_remarks=MH_NAMES[ps[j]]+(x.vod_remarks?' · '+x.vod_remarks:'');list.push(x);}});
  results.forEach(r=>{if(Number(r.pagecount)>page)more=true;});
  return JSON.stringify(Object.assign(mhResult(list,page,0,more),{msg:results.map(r=>r.msg||'').filter(Boolean).join('；')}));
}
function destroy() { mhSongs=Object.create(null);mhSongOrder=[];mhCards=Object.create(null);mhCardOrder=[];mhLists=Object.create(null);mhListOrder=[];mhTags=null;mhKw=null;mhExtraReset();mhMvReset();mhResolveCache=Object.create(null);mhResolveOrder=[]; }
export function __jsEvalReturn() { return {init:init,home:home,homeVod:homeVod,category:category,detail:detail,play:play,search:search,destroy:destroy}; }
