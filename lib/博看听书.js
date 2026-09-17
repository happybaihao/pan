import { Crypto, load, _ } from 'assets://js/lib/cat.js';

let HOST = 'https://api.bookan.com.cn';
let SEARCH_HOST = 'https://es.bookan.com.cn';
const INSTANCE_ID = '25304';
let siteKey = '', siteType = 0, sourceKey = '', ext = '';

const headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
};

const CATEGORY_CONFIG = {
    class: [
        { type_id: '1305', type_name: '少年读物' },
        { type_id: '1304', type_name: '儿童文学' },
        { type_id: '1320', type_name: '国学经典' },
        { type_id: '1306', type_name: '文艺少年' },
        { type_id: '1309', type_name: '育儿心经' },
        { type_id: '1310', type_name: '心理哲学' },
        { type_id: '1307', type_name: '青春励志' },
        { type_id: '1312', type_name: '历史小说' },
        { type_id: '1303', type_name: '故事会' },
        { type_id: '1317', type_name: '音乐戏剧' },
        { type_id: '1319', type_name: '相声评书' },
    ],
    forceOrder: [
        '相声评书', '国学经典', '故事会', '历史小说', '音乐戏剧',
        '青春励志', '少年读物', '儿童文学', '文艺少年', '育儿心经', '心理哲学'
    ]
};

function init(cfg) {
    siteKey = cfg.skey;
    siteType = cfg.stype;
    sourceKey = cfg.sourceKey;
    ext = cfg.ext;
    if (ext && ext.startsWith('http')) HOST = ext;
}

function sortClasses() {
    const order = CATEGORY_CONFIG.forceOrder || [];
    const orderMap = new Map();
    order.forEach((name, i) => orderMap.set(name, i));
    return [...CATEGORY_CONFIG.class].sort((a, b) => {
        const ai = orderMap.get(a.type_name) ?? 999;
        const bi = orderMap.get(b.type_name) ?? 999;
        return ai - bi;
    });
}

async function request(url) {
    try {
        const res = await req(url, { headers });
        if (res.code !== 200) return null;
        return JSON.parse(res.content || '{}');
    } catch (e) {
        return null;
    }
}

function formatItem(item, remark = '') {
    return {
        vod_id: String(item.id || ''),
        vod_name: String(item.name || item.title || ''),
        vod_pic: String(item.cover || ''),
        vod_remarks: String(item.author || remark || '')
    };
}

async function home() {
    const cls = sortClasses();
    return JSON.stringify({ class: cls, filters: {} });
}

async function homeVod() {
    try {
        const list = [];
        const classes = sortClasses();
        for (const c of classes.slice(0, 6)) {
            const data = await request(`${HOST}/voice/book/list?instance_id=${INSTANCE_ID}&page=1&num=24&category_id=${c.type_id}`);
            const items = data?.data?.list || [];
            for (const item of items) {
                const fi = formatItem(item, c.type_name);
                if (fi.vod_id) list.push(fi);
            }
        }
        return JSON.stringify({ list: list.slice(0, 60) });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function category(tid, page, filter, extend) {
    page = Math.max(1, Number(page));
    try {
        const url = `${HOST}/voice/book/list?instance_id=${INSTANCE_ID}&page=${page}&num=24&category_id=${tid}`;
        const data = await request(url);
        const items = data?.data?.list || [];
        const list = items.map(i => formatItem(i)).filter(i => i.vod_id);
        return JSON.stringify({
            page: page,
            pagecount: 999,
            list: list
        });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function detail(id) {
    try {
        const units = [];
        let page = 1, total = 999;
        while (units.length < total && page <= 10) {
            const u = `${HOST}/voice/album/units?album_id=${id}&page=${page}&num=200&order=1`;
            const d = await request(u);
            const list = d?.data?.list || [];
            if (list.length === 0) break;
            total = d?.data?.total || list.length;
            units.push(...list);
            page++;
        }
        const info = await request(`${HOST}/voice/album/get?album_id=${id}`);
        const album = info?.data || {};
        const episodes = [];
        units.forEach((c, i) => {
            const url = c.file || '';
            if (url) episodes.push(`${i + 1}.${c.title || '第' + (i + 1) + '集'}$${url}`);
        });
        const vod = {
            vod_id: id,
            vod_name: album.title || '未知专辑',
            vod_pic: album.cover || '',
            vod_author: album.author || '',
            vod_content: album.description || '暂无简介',
            vod_play_from: '博看听书',
            vod_play_url: episodes.join('#')
        };
        return JSON.stringify({ list: [vod] });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function search(wd) {
    try {
        const url = `${SEARCH_HOST}/api/v3/voice/book?instanceId=${INSTANCE_ID}&keyword=${encodeURIComponent(wd)}&pageNum=1&limitNum=30`;
        const data = await request(url);
        const items = data?.data?.list || [];
        const list = items.map(i => formatItem(i)).filter(i => i.vod_id);
        return JSON.stringify({ list: list });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function play(flag, id, flags) {
    return JSON.stringify({
        parse: 0,
        url: id,
        header: headers
    });
}

export function __jsEvalReturn() {
    return { init, home, homeVod, category, detail, search, play };
}
