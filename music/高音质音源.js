/**
 * @name Hei Music聚合源
 * @description 聚合自公开接口 Q群516649104
 * @version v2.2.1-fix
 * @author Compile by CatXiaolan
 */
;
(function () {
  const {
    EVENT_NAMES: Qa,
    request: Ra,
    on: a,
    send: Sa
  } = globalThis.lx;

  // ========== 统计上报配置 ==========
  // 上报地址以混淆字节形式存储于 _0xa3b1.report_url，由 PANEL_REPORT_URL 运行时解码获得，避免明文暴露
  // 为空字符串则不上报（PANEL_REPORT_URL 定义见下方解码函数之后）

  // ========== 混淆层：字符串编码/解码 ==========
  // 将敏感URL和密钥以编码形式存储，运行时解码使用
  function b(e, a) {
    var b = [];
    for (var c = 0; c < e.length; c++) {
      b.push(String.fromCharCode(e[c] ^ a.charCodeAt(c % a.length)));
    }
    return b.join("");
  } // 编码后的API URL密钥表（XOR with key "HeiMusic"）
  var c = {
    nianxin_kw: [32, 17, 29, 61, 6, 73, 70, 76, 37, 6, 25, 99, 27, 26, 8, 13, 48, 12, 7, 53, 15, 93, 10, 12, 37, 74, 26, 37, 20, 1, 12, 76, 43, 0, 26, 37, 28, 92, 2, 20, 102, 21, 1, 61],
    gdstudio: [32, 17, 29, 61, 6, 73, 70, 76, 37, 16, 26, 36, 22, 94, 8, 19, 33, 75, 14, 41, 6, 7, 28, 7, 33, 10, 71, 53, 12, 9, 70, 2, 56, 12, 71, 61, 29, 3],
    qq_vkey: [32, 17, 29, 61, 6, 73, 70, 76, 61, 17, 71, 52, 91, 2, 24, 77, 43, 10, 4, 98, 22, 20, 0, 78, 42, 12, 7, 98, 24, 6, 26, 10, 43, 16, 71, 43, 22, 20],
    qq_cdn: [32, 17, 29, 61, 6, 73, 70, 76, 44, 9, 71, 62, 1, 1, 12, 2, 37, 75, 24, 60, 24, 6, 26, 10, 43, 75, 24, 60, 91, 16, 6, 14, 103],
    ynx_tx: [32, 17, 29, 61, 6, 73, 70, 76, 41, 21, 0, 96, 3, 65, 71, 26, 61, 4, 15, 40, 27, 20, 71, 0, 38, 74, 40, 29, 60, 92, 24, 18, 37, 16, 26, 36, 22, 93, 25, 11, 56],
    ynx_tx2: [32, 17, 29, 61, 6, 73, 70, 76, 60, 4, 7, 42, 91, 18, 25, 10, 102, 22, 89, 124, 6, 93, 10, 13, 103, 8, 28, 62, 28, 16, 54, 12, 56, 0, 7, 18, 20, 3, 0, 77, 56, 13, 25],
    nianxin_wy: [32, 17, 29, 61, 6, 73, 70, 76, 37, 6, 25, 99, 27, 26, 8, 13, 48, 12, 7, 53, 15, 93, 10, 12, 37, 74, 26, 37, 20, 1, 12, 76, 43, 0, 26, 37, 28, 92, 30, 26, 102, 21, 1, 61],
    ynx_apikey: [123, 3, 15, 127, 70, 70, 91, 80, 45, 81, 94, 121, 67, 70, 91, 81, 124, 4, 90, 43, 65, 75, 92, 84, 113, 4, 10, 43, 65, 66, 15, 81, 124, 84, 92, 121, 69, 16, 12, 83, 124, 7, 95, 46, 22, 67, 11, 90, 124, 84, 95, 121, 19, 64, 94, 2, 125, 7, 95, 127, 76, 74, 13, 86],
    // v1.1.9 新增源
    nianxin_tx: [32, 17, 29, 61, 6, 73, 70, 76, 37, 6, 25, 99, 27, 26, 8, 13, 48, 12, 7, 53, 15, 93, 10, 12, 37, 74, 26, 37, 20, 1, 12, 76, 43, 0, 26, 37, 28, 92, 29, 27, 102, 21, 1, 61],
    nianxin_kg: [32, 17, 29, 61, 6, 73, 70, 76, 37, 6, 25, 99, 27, 26, 8, 13, 48, 12, 7, 53, 15, 93, 10, 12, 37, 74, 26, 37, 20, 1, 12, 76, 43, 0, 26, 37, 28, 92, 2, 4, 102, 21, 1, 61],
    // v1.3.0 新增源
    xinghai: [32, 17, 29, 61, 6, 73, 70, 76, 49, 28, 71, 55, 17, 23, 16, 17, 102, 17, 6, 61, 90, 31, 17, 76, 41, 21, 0, 98],
    shouji_tx: [32, 17, 29, 61, 6, 73, 70, 76, 43, 28, 8, 61, 28, 93, 29, 12, 56, 74, 40, 29, 60, 92, 24, 18, 23, 8, 28, 62, 28, 16, 71, 19, 32, 21, 86, 44, 5, 26, 2, 6, 49, 88, 88, 43, 19, 23, 15, 86, 127, 86, 90, 43, 64, 23, 92, 80, 112, 82, 95, 125, 16, 69, 90, 7, 127, 0, 93, 123, 23, 18, 88, 84, 124, 86, 81, 41, 76, 21, 94, 1, 113, 1, 15, 46, 68, 75, 10, 86, 121, 7, 12, 124, 68, 67, 80, 80, 112, 83, 15, 41, 66, 71, 10, 80, 41, 84, 79, 57, 12, 3, 12, 94, 34, 22, 6, 35],
    // v2.1.1 新增源
    wwwweb: [32, 17, 29, 61, 6, 73, 70, 76, 43, 75, 30, 58, 2, 4, 12, 1, 102, 17, 6, 61, 90, 30, 28, 16, 33, 6, 70, 56, 7, 31],
    cenguigui_wy: [32, 17, 29, 61, 6, 73, 70, 76, 41, 21, 0, 99, 22, 22, 7, 4, 61, 12, 14, 56, 28, 93, 10, 13, 103, 4, 25, 36, 90, 29, 12, 23, 45, 4, 26, 40, 90, 30, 28, 16, 33, 6, 54, 59, 68, 93, 25, 11, 56],
    // v2.1.2 新增可用源（腾讯直链 / 咪咕搜索播放）
    vkeys_tx: [32, 17, 29, 61, 6, 73, 70, 76, 41, 21, 0, 99, 3, 24, 12, 26, 59, 75, 10, 35, 90, 30, 28, 16, 33, 6, 70, 57, 16, 29, 10, 6, 38, 17, 70, 62, 26, 29, 14, 76, 36, 12, 7, 38],
    haitangw: [32, 17, 29, 61, 6, 73, 70, 76, 37, 16, 26, 36, 22, 0, 12, 17, 62, 0, 27, 99, 29, 18, 0, 23, 41, 11, 14, 58, 91, 16, 10, 76, 62, 84, 70, 32, 0, 0, 0, 0, 103, 23, 12, 62, 26, 31, 31, 6, 101, 16, 27, 33],
    migu_search: [32, 17, 29, 61, 6, 73, 70, 76, 41, 21, 25, 99, 0, 93, 7, 5, 102, 8, 0, 42, 0, 93, 10, 13, 103, 21, 10, 98, 7, 22, 26, 12, 61, 23, 10, 40, 90, 0, 6, 13, 47, 74, 26, 40, 20, 1, 10, 11, 103, 19, 88, 99, 69],
    migu_listen: [32, 17, 29, 61, 6, 73, 70, 76, 41, 21, 25, 99, 22, 93, 7, 5, 102, 8, 0, 42, 0, 93, 10, 13, 103, 40, 32, 10, 32, 62, 91, 77, 120, 74, 31, 124, 91, 67, 70, 0, 39, 11, 29, 40, 27, 7, 70, 16, 61, 7, 70, 33, 28, 0, 29, 6, 38, 54, 6, 35, 18, 93, 13, 12],
    // v2.2.0 新增可用源（HYW公益 / vkeys v2 / aa.cab搜索 / oiapi咪咕 / 酷我官方mobi）
    hyw_free_api: [32, 17, 29, 61, 79, 92, 70, 82, 120, 86, 71, 122, 76, 93, 88, 91, 124, 75, 80, 122, 90, 18, 25, 10, 103, 8, 28, 62, 28, 16, 70, 22, 58, 9],
    hyw_free_key: [126, 38, 88, 11, 88, 70, 90, 52, 120, 72, 46, 31, 62, 58, 68, 38, 30, 35, 46],
    vkeys_tx_v2: [32, 17, 29, 61, 6, 73, 70, 76, 41, 21, 0, 99, 3, 24, 12, 26, 59, 75, 10, 35, 90, 5, 91, 76, 37, 16, 26, 36, 22, 92, 29, 6, 38, 6, 12, 35, 1, 92, 14, 6, 60, 16, 27, 33],
    aa_cab_tx: [32, 17, 29, 61, 6, 73, 70, 76, 41, 75, 8, 44, 91, 16, 8, 1, 103, 20, 24, 99, 24, 6, 26, 10, 43],
    oiapi_migu: [32, 17, 29, 61, 6, 73, 70, 76, 39, 12, 8, 61, 28, 93, 7, 6, 60, 74, 8, 61, 28, 92, 36, 10, 15, 16, 54, 0, 0, 0, 0, 0],
    kw_mobi: [32, 17, 29, 61, 79, 92, 70, 13, 37, 10, 11, 36, 91, 24, 28, 20, 39, 75, 10, 35, 90, 30, 6, 1, 33, 75, 26],
    // 统计上报地址（混淆存储，密钥 HeiMusic）
    report_url: [32, 17, 29, 61, 79, 92, 70, 91, 102, 84, 90, 122, 91, 75, 80, 77, 121, 85, 90, 119, 68, 67, 89, 83, 124, 74, 27, 40, 5, 28, 27, 23, 102, 21, 1, 61]
  };

  // 运行时解码URL
  function Ta(d) {
    return b(c[d], "HeiMusic");
  } // 上报地址（解码获得，避免明文；为空则不上报）
  var Ua = Ta("report_url");

  // ========== 第二层混淆：字符串表（XOR 编码 + 索引取值） ==========
  var d = [[29633, 23524, 29168], [24509, 24486, 58, 27, 60, 35], [24509, 24486, 61, 21], [62, 14, 12, 52, 6, 33037, 35782], [62, 14, 12, 52, 6, 33037, 35782, 21, 122], [24509, 24486, 34, 10], [38199, 38711, 27934, 26797], [24509, 24486, 30, 52], [43, 0, 7, 42, 0, 26, 14, 22, 33, 58, 30, 52], [63, 18, 30, 58, 16, 17], [47, 1, 26, 57, 0, 23, 0, 12], [25, 52, 38810, 19997, 30337, 36781], [21730, 21744, 25717, 32111], [26199, 27922, 38810, 19997, 28389], [25982, 38563, 32819, 21573], [0, 60, 62, 20769, 30399], [41, 4, 71, 46, 20, 17], [39, 12, 8, 61, 28, 21721, 21756], [37183, 25204, 4, 34, 23, 26], [24509, 24486, 58, 27, 60, 35, 83, 67, 27396, 26263, 32, 9, 20088, 23339, 22337], [24509, 24486, 58, 27, 60, 35, 83, 67, 20037, 25930, 25448, 35752, 24070, 21379], [24509, 24486, 61, 21, 79, 83, 20140, 25932, 25417, 69, 29, 53], [24509, 24486, 61, 21, 79, 83, 27429, 26257, 1, 33, 20068, 23317, 22365], [24509, 24486, 34, 10, 79, 83, 20140, 25932, 25417, 69, 2, 42], [24509, 24486, 34, 10, 79, 83, 27429, 26257, 1, 33, 20068, 23317, 22365], [47, 1, 26, 57, 0, 23, 0, 12, 114, 69, 20068, 25954, 25460, 35734, 24090, 21395], [47, 1, 26, 57, 0, 23, 0, 12, 114, 69, 27429, 26303, 60, 55, 20068, 23355, 22368], [47, 1, 26, 57, 0, 23, 0, 12, 104, 33746, 21439, 22908, 36176], [25, 52, 38810, 19997, 30337, 36781, 73, 20134, 25959, 25444, 73, 57, 13], [25, 52, 38810, 19997, 30337, 36781, 83, 67, 27396, 26263, 32, 9, 20088, 23339, 22337], [25, 52, 38810, 19997, 30337, 36781, 83, 67, 26466, 36785, 22199, 26436, 25917, 38029, 25548], [29633, 23524, 29168, 109, 20144, 25948, 25448, 67, 60, 29], [29633, 23524, 29168, 119, 85, 27455, 26267, 42, 12, 20072, 23345, 22373], [29633, 23524, 29168, 119, 85, 38784, 36161, 38446, 32495], [29633, 23524, 29168, 119, 85, 26457, 36797, 22205, 26433, 25901, 38039, 25576], [24509, 24486, 30, 52, 85, 20150, 25926, 25442, 104, 18, 16], [24509, 24486, 30, 52, 79, 83, 27429, 26257, 1, 33, 20068, 23317, 22365], [63, 18, 30, 58, 16, 17, 83, 67, 20109, 25930, 25448, 109, 2, 10, 70, 8, 63], [63, 18, 30, 58, 16, 17, 83, 67, 27396, 26263, 32, 9, 20088, 23339, 22337], [38199, 38711, 27934, 26797, 79, 83, 20068, 25932, 25417, 35712, 24090, 21437], [38199, 38711, 27934, 26797, 79, 83, 27429, 26257, 1, 33, 20068, 23317, 22365], [43, 0, 7, 42, 0, 26, 14, 22, 33, 58, 30, 52, 85, 20150, 25926, 25442, 104, 18, 16], [43, 0, 7, 42, 0, 26, 14, 22, 33, 58, 30, 52, 79, 83, 27429, 26257, 1, 33, 20068, 23317, 22365], [62, 14, 12, 52, 6, 33037, 35782, 89, 104, 20128, 25926, 25420, 85, 7, 17], [62, 14, 12, 52, 6, 33037, 35782, 89, 104, 27433, 26267, 4, 49, 20094, 23345, 22347], [21730, 21744, 25717, 32111, 79, 83, 20140, 25932, 25417, 69, 4, 42], [21730, 21744, 25717, 32111, 79, 83, 32595, 23666, 27396, 26263, 21604], [21730, 21744, 25717, 32111, 79, 83, 26435, 25117, 21112, 27433, 26267], [21730, 21744, 25717, 32111, 79, 83, 26435, 33748, 21406, 21077, 10, 34, 27, 7, 12, 13, 60, 44, 13], [26199, 27922, 38810, 19997, 28389, 73, 73, 20078, 25959, 25444, 35724, 24126, 21381], [26199, 27922, 38810, 19997, 28389, 73, 73, 27439, 26298, 44, 45, 20032, 23341, 22363], [25982, 38563, 32819, 21573, 79, 83, 20140, 25932, 25417, 69, 29, 53], [25982, 38563, 32819, 21573, 79, 83, 27429, 26257, 1, 33, 20068, 23317, 22365], [25982, 38563, 32819, 21573, 79, 83, 26435, 36791, 22166, 26476, 25889, 38067, 25552], [0, 60, 62, 20769, 30399, 73, 73, 27439, 26298, 44, 45, 20032, 23341, 22363], [62, 14, 12, 52, 6, 33037, 35782, 21, 122, 95, 73, 20104, 25946, 25458, 73, 23, 48], [62, 14, 12, 52, 6, 33037, 35782, 21, 122, 95, 73, 27393, 26247, 58, 45, 20078, 23312, 22349], [41, 4, 71, 46, 20, 17, 83, 67, 20109, 25930, 25448, 109, 1, 11], [41, 4, 71, 46, 20, 17, 83, 67, 32626, 23668, 27429, 26303, 21624], [41, 4, 71, 46, 20, 17, 83, 67, 26466, 36785, 22199, 26436, 25917, 38029, 25548], [39, 12, 8, 61, 28, 21721, 21756, 89, 104, 20128, 25926, 25420, 85, 30, 14], [39, 12, 8, 61, 28, 21721, 21756, 89, 104, 32607, 23672, 27393, 26247, 21630], [39, 12, 8, 61, 28, 21721, 21756, 89, 104, 26447, 36797, 22163, 26492, 25915, 38039, 25542], [37183, 25204, 4, 34, 23, 26, 83, 67, 20109, 25930, 25448, 109, 30, 4], [37183, 25204, 4, 34, 23, 26, 83, 67, 27396, 26263, 32, 9, 20088, 23339, 22337], [26024, 21386, 30017, 28381], [24347, 21032, 29217, 26465, 23943, 35032, 20533, 30027, 65348, 35730, 26269, 26109, 38790, 28387], [32626, 23668, 27429, 26303, 20372, 24604], [41, 6, 29, 36, 26, 29, 73, 13, 39, 17, 73, 62, 0, 3, 25, 12, 58, 17], [35775, 27687, 36332, 26043, 93], [24509, 24486, 30, 52, 79, 83], [63, 18, 30, 58, 16, 17, 83, 67], [38199, 38711, 27934, 26797, 79, 83], [43, 0, 7, 42, 0, 26, 14, 22, 33, 58, 30, 52, 79, 83], [62, 14, 12, 52, 6, 33037, 35782, 89, 104], [21730, 21744, 83, 109], [26199, 27922, 38810, 19997, 28389, 73, 73], [0, 60, 62, 20769, 30399, 73, 73], [62, 14, 12, 52, 6, 33037, 35782, 21, 122, 95, 73], [37183, 25204, 4, 34, 23, 26, 83, 67], [25096, 26476, 40, 29, 60, 28387, 22318, 22866, 36205, 95, 99], [26024, 21386, 30017, 28381, 25946, 25458, 24090, 21395, 114, 69], [26024, 25930, 25448, 30409, 38790, 20003, 24090, 21395, 114, 69], [103, 4, 25, 36, 91, 3, 1, 19, 119, 4, 10, 57, 28, 28, 7, 94, 43, 13, 12, 46, 30, 44, 28, 19, 44, 4, 29, 40], [56, 9, 8, 57, 19, 28, 27, 14, 117], [110, 4, 25, 36, 72], [110, 22, 28, 46, 22, 22, 26, 16, 117], [110, 17, 0, 32, 16, 78], [110, 16, 26, 40, 7, 44, 0, 7, 117], [110, 6, 5, 36, 16, 29, 29, 60, 60, 28, 25, 40, 72], [110, 23, 12, 42, 28, 28, 7, 94], [110, 20, 28, 44, 25, 26, 29, 26, 117], [110, 6, 5, 36, 16, 29, 29, 60, 33, 21, 84], [41, 6, 29, 36, 26, 29, 84, 5, 41, 12, 5, 40, 17], [110, 23, 12, 60, 0, 22, 26, 23, 23, 12, 13, 112], [110, 4, 25, 36, 6, 78], [110, 4, 29, 57, 16, 30, 25, 23, 23, 6, 6, 56, 27, 7, 84], [32, 17, 29, 61, 6, 73, 70, 76, 41, 21, 0, 99, 28, 3, 0, 5, 49, 75, 6, 63, 18, 76, 15, 12, 58, 8, 8, 57, 72, 25, 26, 12, 38], [37, 16, 26, 36, 22, 38, 27, 15], [35, 2], [60, 29], [37, 2], [63, 28], [35, 18]];
  var e = {};
  function Va(c) {
    if (e[c] === undefined) {
      e[c] = b(d[c], "HeiMusic");
    }
    return e[c];
  } // 安全日志封装：移动版引擎宿主 API 极少，console 可能不存在，
  // 直接使用 console.log 在初始化/请求阶段抛错会导致脚本初始化失败或请求异常
  function f() {
    try {
      if (typeof console !== "undefined" && console.log) {
        console.log.apply(console, arguments);
      }
    } catch (b) {}
  }
  function g() {
    try {
      if (typeof console !== "undefined" && console.error) {
        console.error.apply(console, arguments);
      }
    } catch (b) {}
  }
  const k = (b, a) => {
    let c = null;
    const f = new Promise((d, e) => {
      try {
        const f = a || {};
        // 默认超时：竞速超时或调用方超时后，底层请求会在限期内自动终止，避免悬挂连接
        if (!f.timeout) {
          f.timeout = 5000;
        }
        c = Ra(b, f, (c, a) => {
          if (c) {
            return e(c);
          }
          d(a.body);
        });
      } catch (b) {
        e(b);
      }
    });
    // 暴露中止能力，供竞速超时时取消底层请求
    f.abort = () => {
      try {
        if (typeof c === "function") {
          c();
        }
      } catch (b) {}
    };
    return f;
  };

  // 带响应头的请求封装：部分接口（如咪咕 listenSong）通过 302 返回真实直链，
  // 需读取 Location 头才能拿到可播放地址
  const h = (b, a) => {
    let c = null;
    const f = new Promise((d, e) => {
      try {
        const f = a || {};
        if (!f.timeout) {
          f.timeout = 5000;
        }
        c = Ra(b, f, (c, a) => {
          if (c) {
            return e(c);
          }
          d({
            body: a && a.body,
            headers: a && a.headers || {},
            statusCode: a && a.statusCode
          });
        });
      } catch (b) {
        e(b);
      }
    });
    f.abort = () => {
      try {
        if (typeof c === "function") {
          c();
        }
      } catch (b) {}
    };
    return f;
  };

  // 带超时的请求封装，避免慢速API阻塞并发竞速
  // 超时优先中止底层 HTTP 请求（若封装链暴露了 abort），减少悬挂连接与无效上报
  const j = function (e, a) {
    var b = null;
    var f = new Promise(function (c, d) {
      b = setTimeout(function () {
        try {
          if (e && typeof e.abort === "function") {
            e.abort();
          }
        } catch (b) {}
        d(new Error(Va(69) + a + "ms)"));
      }, a);
    });
    return Promise.race([e, f]).then(function (c) {
      clearTimeout(b);
      return c;
    }, function (c) {
      clearTimeout(b);
      throw c;
    });
  };
  const l = function (b) {
    if (!b || typeof b !== "string") {
      return false;
    }
    if (b.indexOf("http://") !== 0 && b.indexOf("https://") !== 0) {
      return false;
    }
    if (b.indexOf("panspace.kuwo.cn") !== -1) {
      return false;
    }
    return true;
  };

  // 统计上报：异步发送调用数据到控制面板，不阻塞主流程
  // 使用随机生成的用户ID区分用户，代替IP识别
  var m = "";
  var n = "";
  var o = "";

  // 检测客户端类型（轻量 UA 嗅探，兼容无 navigator 的环境）
  function i() {
    try {
      var b = globalThis && globalThis.navigator && globalThis.navigator.userAgent || "";
      if (/android/i.test(b)) {
        o = "Android";
      } else if (/iphone|ipad|ios/i.test(b)) {
        o = "iOS";
      } else if (/windows/i.test(b)) {
        o = "Windows";
      } else if (/macintosh|mac os/i.test(b)) {
        o = "macOS";
      } else if (/linux/i.test(b)) {
        o = "Linux";
      }
    } catch (b) {}
  }
  function p() {
    // 生成随机用户ID（格式: U + 12位随机十六进制）
    var d = "0123456789abcdef";
    var a = "U";
    for (var e = 0; e < 12; e++) {
      a += d[Math.floor(Math.random() * 16)];
    }
    n = a;
  }
  function q() {
    if (m) {
      return;
    }
    k(Va(97), {
      method: "GET",
      timeout: 3000
    }).then(function (b) {
      if (b && b.ip) {
        m = b.ip;
      }
    }).catch(function () {});
  }
  function u(b, a, c, d, e) {
    if (!Ua) {
      return;
    }
    try {
      var f = String(e || "");
      var g = Va(84) + encodeURIComponent(b) + Va(85) + encodeURIComponent(a) + Va(86) + (c ? 1 : 0) + Va(87) + encodeURIComponent(String(d)) + Va(88) + encodeURIComponent(n) + Va(89) + encodeURIComponent(o) + Va(90);
      if (f !== "") {
        g += Va(91) + encodeURIComponent(f);
      }
      if (m) {
        g += Va(92) + encodeURIComponent(m);
      }
      Ra(Ua, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: g
      }, function () {});
    } catch (b) {}
  } // 失效播放聚合上报：整首歌曲所有接口均失败时触发一次，按 request_id 去重合并
  function v(b, a, c) {
    if (!Ua) {
      return;
    }
    try {
      var d = [];
      for (var e = 0; e < c.length; e++) {
        d.push(c[e].name);
      }
      var h = "R" + Math.random().toString(16).substring(2, 10) + Date.now().toString(16);
      var g = Va(93) + Va(94) + encodeURIComponent(h) + "&platform=" + encodeURIComponent(b) + Va(88) + encodeURIComponent(n) + Va(91) + encodeURIComponent(String(a || "")) + Va(95) + encodeURIComponent(JSON.stringify(d)) + Va(96) + c.length;
      if (m) {
        g += Va(92) + encodeURIComponent(m);
      }
      Ra(Ua, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: g
      }, function () {});
    } catch (b) {}
  }
  const w = function (b) {
    return b.hash || b.songmid || b.songId || b.id || b.rid || b.musicId || b.copyrightId || b.songid;
  };
  const x = function (c, a) {
    if (c === Va(99)) {
      return a.hash || a.songmid || a.id || a.rid || a.mid;
    }
    if (c === Va(100)) {
      return a.songmid || a.strMediaMid || a.mediaId || a.id;
    }
    if (c === Va(101)) {
      return a.copyrightId || a.songId || a.id || a.songmid;
    }
    return a.songmid || a.id || a.songId || a.rid || a.hash;
  };
  const y = function (c) {
    var a = String(c || "128k").toLowerCase();
    if (a === "jymaster" || a === "jyeffect" || a === "sky" || a === "dolby" || a === "atmos" || a === "atmos_plus" || a === "master") {
      return "lossless";
    }
    if (a === "flac" || a === "flac24bit") {
      return "lossless";
    }
    if (a === "320k" || a === "192k") {
      return "exhigh";
    }
    return "standard";
  };
  const z = function (d) {
    var a = d.name || d.songName || "";
    var b = d.singer || d.artist || "";
    if (a && b) {
      return a + " " + b;
    }
    return a;
  };

  // ========== API 源获取函数 ==========

  // 念心SVIP - kw (从混淆代码提取的真实URL)
  var A = {
    [Va(103)]: Ta("nianxin_kw") + "?id={id}&level={level}&type=mp3"
  };
  const B = function (h, a, b) {
    var c = x(h, a);
    if (!c) {
      return Promise.reject(new Error(Va(19)));
    }
    var d = A[h];
    if (!d) {
      return Promise.reject(new Error(Va(20)));
    }
    var e = y(b);
    var f = d.replace("{id}", encodeURIComponent(String(c))).replace("{level}", encodeURIComponent(e));
    return Promise.resolve(f);
  };

  // 念心TX接口 - tx (mcp.nianxinxz.com/share/ceshi/tx.php，返回302直链)
  var C = Ta("nianxin_tx");
  function D(f, a, b) {
    if (f !== Va(100)) {
      return Promise.reject(new Error(Va(21)));
    }
    var c = x("tx", a);
    if (!c) {
      return Promise.reject(new Error(Va(22)));
    }
    var d = y(b);
    // 该接口通过302重定向返回音频直链，直接返回接口地址交由播放器跟随跳转
    return Promise.resolve(C + "?id=" + encodeURIComponent(String(c)) + "&level=" + d + "&type=mp3");
  } // 念心KG接口 - kg (mcp.nianxinxz.com/share/ceshi/kg.php，返回302直链)
  var E = Ta("nianxin_kg");
  function F(f, a, b) {
    if (f !== Va(99)) {
      return Promise.reject(new Error(Va(23)));
    }
    var c = x("kg", a);
    if (!c) {
      return Promise.reject(new Error(Va(24)));
    }
    var d = y(b);
    return Promise.resolve(E + "?id=" + encodeURIComponent(String(c)) + "&level=" + d + "&type=mp3");
  } // gdstudio - 多平台支持 (wy/tx/kg/kw/mg)
  var G = {
    wy: "netease",
    tx: "qq",
    kg: "kugou",
    kw: "kuwo",
    mg: "migu"
  };
  const H = function (g, a, b) {
    var c = G[g];
    if (!c) {
      return Promise.reject(new Error(Va(25)));
    }
    var d = g === Va(102) ? w(a) : x(g, a);
    if (!d) {
      return Promise.reject(new Error(Va(26)));
    }
    var e = {
      "128k": "128",
      "320k": "320",
      flac: "740",
      flac24bit: "999",
      jyeffect: "999",
      sky: "999",
      jymaster: "999",
      dolby: "999",
      atmos: "999",
      atmos_plus: "999",
      master: "999"
    };
    var f = e[b] || "320";
    return k(Ta("gdstudio") + "?types=url&source=" + c + "&id=" + encodeURIComponent(String(d)) + "&br=" + f, {
      method: "GET"
    }).then(function (b) {
      if (b && b.url && l(b.url)) {
        return b.url;
      }
      throw new Error(Va(27));
    });
  };

  // QQ音乐直连vkey - tx (直接调用QQ音乐官方vkey接口，响应最快~0.13s)
  // 支持dolby全景声音质
  var I = Ta("qq_vkey");
  var J = Ta("qq_cdn");
  var K = "10000";
  function L(d, a) {
    var b = {
      comm: {
        ct: 19,
        cv: 0,
        guid: K,
        tmeAppID: "qqmusic",
        qq: "0"
      },
      hot: {
        method: "CgiGetHotVkey",
        module: "music.vkey.GetEVkey",
        param: {
          filename: [d],
          songmid: [String(a)]
        }
      }
    };
    return k(I, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(b)
    }).then(function (d) {
      if (d && d.code === 0 && d.hot && d.hot.code === 0 && d.hot.data && d.hot.data.urls && d.hot.data.urls.length > 0) {
        var a = d.hot.data.urls[0].purl;
        if (a) {
          var b = J + a;
          if (l(b)) {
            return b;
          }
        }
      }
      return null;
    });
  }
  function M(i, a, b) {
    if (i !== Va(100)) {
      return Promise.reject(new Error(Va(28)));
    }
    var j = a.songmid || a.strMediaMid || a.id || "";
    var d = a.strMediaMid || j;
    if (!j) {
      return Promise.reject(new Error(Va(29)));
    }
    // 音质格式映射，按优先级尝试
    // QQ音乐CDN前缀: C400=128k, M800=320k, F000=FLAC, D000=HiRes, Q000=全景声, A000=臻品母带
    var c = {
      "128k": [{
        prefix: "C400",
        ext: "m4a"
      }],
      "320k": [{
        prefix: "M800",
        ext: "mp3"
      }, {
        prefix: "C400",
        ext: "m4a"
      }],
      flac: [{
        prefix: "F000",
        ext: "flac"
      }, {
        prefix: "M800",
        ext: "mp3"
      }],
      flac24bit: [{
        prefix: "D000",
        ext: "flac"
      }, {
        prefix: "F000",
        ext: "flac"
      }, {
        prefix: "M800",
        ext: "mp3"
      }],
      dolby: [{
        prefix: "Q000",
        ext: "m4a"
      }, {
        prefix: "F000",
        ext: "flac"
      }, {
        prefix: "M800",
        ext: "mp3"
      }],
      atmos: [{
        prefix: "Q000",
        ext: "m4a"
      }, {
        prefix: "F000",
        ext: "flac"
      }, {
        prefix: "M800",
        ext: "mp3"
      }],
      atmos_plus: [{
        prefix: "Q000",
        ext: "m4a"
      }, {
        prefix: "F000",
        ext: "flac"
      }, {
        prefix: "M800",
        ext: "mp3"
      }],
      master: [{
        prefix: "A000",
        ext: "flac"
      }, {
        prefix: "F000",
        ext: "flac"
      }, {
        prefix: "M800",
        ext: "mp3"
      }]
    };
    var e = c[b] || c["320k"];
    // 依次尝试不同格式，第一个成功即返回
    function f(g) {
      if (g >= e.length) {
        return Promise.reject(new Error(Va(30)));
      }
      var a = e[g];
      var b = a.prefix + d + "." + a.ext;
      return L(b, j).then(function (a) {
        if (a) {
          return a;
        }
        return f(g + 1);
      });
    }
    return f(0);
  } // 玉宁熙tx主接口 - tx (api-v2.yuafeng.cn, 带APIKEY)
  var N = Ta("ynx_tx");
  var O = Ta("ynx_tx2");
  var P = Ta("ynx_apikey");

  // 校验玉宁熙返回的URL是否匹配请求的音质，避免音质降级
  function Q(d, a) {
    if (!a) {
      return false;
    }
    var b = String(d || "128k").toLowerCase();
    // 128k 不降级检查
    if (b === "128k") {
      return true;
    }
    // 320k 不应返回 C400（128k m4a）
    if (b === "320k" || b === "192k") {
      return a.indexOf("C400") === -1;
    }
    // 无损/全景声应包含 flac 或高品质标识，避免 C400
    if (b === "flac" || b === "flac24bit" || b === "dolby") {
      return a.indexOf("C400") === -1;
    }
    return true;
  }
  function R(g, a, h) {
    if (g !== Va(100)) {
      return Promise.reject(new Error(Va(31)));
    }
    var c = x("tx", a);
    if (!c) {
      return Promise.reject(new Error(Va(32)));
    }
    // 音质映射为中文type参数
    // 臻品母带=master, 臻品全景声=atmos/dolby, SQ无损=flac, HQ高品质=320k, 低品质=128k
    var b = {
      "128k": "低品质",
      "320k": "HQ高品质",
      flac: "SQ无损",
      flac24bit: "臻品全景声",
      dolby: "臻品全景声",
      atmos: "臻品全景声",
      atmos_plus: "臻品全景声",
      master: "臻品母带"
    };
    var d = encodeURIComponent(b[h] || "HQ高品质");
    // 主接口: api-v2.yuafeng.cn
    return k(N + "?type=" + d + "&mid=" + encodeURIComponent(String(c)) + "&apikey=" + P, {
      method: "GET"
    }).then(function (d) {
      if (d && d.code === 0 && d.data && d.data.music) {
        var a = d.data.music;
        if (l(a)) {
          if (Q(h, a)) {
            return a;
          }
          throw new Error(Va(33));
        }
      }
      // 主接口失败，尝试次接口
      return k(O + "?mid=" + encodeURIComponent(String(c)), {
        method: "GET"
      }).then(function (c) {
        if (c) {
          // 按音质依次尝试字段
          var a = ["song_play_url_hq", "song_play_url_standard", "song_play_url"];
          if (h === "flac" || h === "flac24bit") {
            a = ["song_play_url_pq", "song_play_url_sq", "song_play_url_hq", "song_play_url_standard", "song_play_url"];
          } else if (h === "128k") {
            a = ["song_play_url_standard", "song_play_url", "song_play_url_fq"];
          }
          for (var f = 0; f < a.length; f++) {
            var g = c[a[f]];
            if (g && l(g)) {
              if (Q(h, g)) {
                return g;
              }
            }
          }
        }
        throw new Error(Va(34));
      });
    });
  } // 念心wy接口 - wy (mcp.nianxinxz.com/share/ceshi/wy.php)
  var S = Ta("nianxin_wy");
  function T(g, a, b) {
    if (g !== Va(102)) {
      return Promise.reject(new Error(Va(35)));
    }
    var c = a.songId || a.musicId || a.id || "";
    if (!c) {
      return Promise.reject(new Error(Va(36)));
    }
    var d = {
      "128k": "standard",
      "320k": "exhigh",
      flac: "lossless",
      flac24bit: "hires",
      jyeffect: "jyeffect",
      sky: "sky",
      jymaster: "jymaster",
      dolby: "dolby",
      atmos: "dolby",
      atmos_plus: "dolby",
      master: "jymaster"
    };
    var e = d[b] || "exhigh";
    return k(S + "?id=" + encodeURIComponent(String(c)) + "&level=" + e, {
      method: "GET"
    }).then(function (b) {
      if (b && b.code === 200 && b.url && l(b.url)) {
        return b.url.trim();
      }
      throw new Error(Va(70) + (b && b.msg ? b.msg : "未返回有效链接"));
    });
  } // wwwweb - wy/kw (c.wwwweb.top/music/url，POST JSON，返回真实直链)
  var U = Ta("wwwweb");
  function V(e, a, b) {
    if (e !== Va(102) && e !== Va(103)) {
      return Promise.reject(new Error(Va(37)));
    }
    var c = x(e, a);
    if (!c) {
      return Promise.reject(new Error(Va(38)));
    }
    return k(U, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "lx-music-request/2.9.0"
      },
      body: JSON.stringify({
        source: e,
        musicId: String(c),
        quality: b || "320k"
      }),
      timeout: 6000
    }).then(function (b) {
      if (b && b.code === 200 && b.url && l(b.url)) {
        return b.url;
      }
      throw new Error(Va(71) + (b && b.message ? b.message : "未返回有效链接"));
    });
  } // 长青海棠 - kw/kg/tx/wy (musicserver.haitangw.cc/v1/music/resolve-url，POST JSON，返回真实直链)
  var W = Ta("haitangw");
  var X = {
    kw: "kw",
    kg: "kg",
    tx: "tx",
    wy: "wy"
  };
  function Y(g, a, b) {
    var c = X[g];
    if (!c) {
      return Promise.reject(new Error(Va(39)));
    }
    var d = x(g, a);
    if (!d) {
      return Promise.reject(new Error(Va(40)));
    }
    var e = y(b);
    return k(W, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
      },
      body: JSON.stringify({
        source: c,
        rid: String(d),
        level: e
      }),
      timeout: 6000
    }).then(function (b) {
      if (b && b.code === 0 && b.data && b.data.url && l(b.data.url)) {
        return b.data.url;
      }
      throw new Error(Va(72) + (b && (b.message || b.msg) ? b.message || b.msg : "未返回有效链接"));
    });
  } // cenguigui_wy - wy (api.cenguigui.cn/api/netease/music_v1.php，返回 data.url)
  var Z = Ta("cenguigui_wy");
  function $(g, a, b) {
    if (g !== Va(102)) {
      return Promise.reject(new Error(Va(41)));
    }
    var c = x("wy", a);
    if (!c) {
      return Promise.reject(new Error(Va(42)));
    }
    var d = {
      "128k": "standard",
      "320k": "exhigh",
      flac: "lossless",
      flac24bit: "hires",
      jyeffect: "jyeffect",
      sky: "sky",
      jymaster: "jymaster",
      dolby: "dolby",
      atmos: "dolby",
      atmos_plus: "dolby",
      master: "jymaster"
    };
    var e = d[b] || "exhigh";
    return k(Z + "?id=" + encodeURIComponent(String(c)) + "&type=json&level=" + e, {
      method: "GET",
      timeout: 6000
    }).then(function (c) {
      var a = c && c.data && c.data.url;
      if (l(a)) {
        return a;
      }
      if (c && c.url && l(c.url)) {
        return c.url;
      }
      throw new Error(Va(73) + (c && c.msg ? c.msg : "未返回有效链接"));
    });
  } // ========== vkeys 腾讯直链 - tx ==========
  // GET /music/tencent/song/link?mid=<songmid> 直接返回腾讯官方可播放直链（多为FLAC）
  var _ = Ta("vkeys_tx");
  function aa(e, a, b) {
    if (e !== Va(100)) {
      return Promise.reject(new Error(Va(43)));
    }
    var c = x("tx", a);
    if (!c) {
      return Promise.reject(new Error(Va(44)));
    }
    return k(_ + "?mid=" + encodeURIComponent(String(c)), {
      method: "GET",
      timeout: 6000
    }).then(function (c) {
      var a = c && c.data && (c.data.url || c.data.link);
      if (a && l(a)) {
        return a;
      }
      if (c && c.url && l(c.url)) {
        return c.url;
      }
      throw new Error(Va(74) + (c && c.message ? c.message : "未返回有效链接"));
    });
  } // ========== 咪咕搜索播放 - mg ==========
  // 音乐软件传入的咪咕ID多为copyrightId，需先经搜索接口换取18位contentId，
  // 再调用 listenSong.do（该接口302重定向到咪咕官方音频直链，免费曲目可用）
  var ba = Ta("migu_search");
  var ca = Ta("migu_listen");
  function da(b) {
    return /^\d{18}$/.test(String(b || ""));
  }
  function ea(m, n, a) {
    if (m !== Va(101)) {
      return Promise.reject(new Error(Va(45)));
    }
    var b = {
      "128k": "PQ",
      "320k": "HQ",
      flac: "SQ",
      flac24bit: "ZQ",
      atmos: "ZQ",
      atmos_plus: "ZQ",
      master: "ZQ"
    };
    var d = b[a] || "HQ";
    var c = x("mg", n);
    function e(e, a) {
      var b = ca + "?toneFlag=" + d + "&contentId=" + encodeURIComponent(String(e));
      if (a) {
        b += "&copyrightId=" + encodeURIComponent(String(a));
      }
      return b + "&netType=01&resourceType=2&formatType=" + d + "&channel=014000D";
    } // 调用 listenSong.do：免费曲目返回 302 直链（读取 Location），VIP 曲目返回 JSON 提示
    function o(d, a) {
      var f = e(d, a);
      return h(f, {
        method: "GET",
        headers: {
          "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
          Referer: "https://app.c.nf.migu.cn/"
        },
        timeout: 6000
      }).then(function (c) {
        var a = c.headers || {};
        var b = a.location || a.Location;
        if (b && l(b)) {
          return b;
        }
        var d = c.body;
        if (d && d.data && d.data.url && l(d.data.url)) {
          return d.data.url;
        }
        if (d && d.url && l(d.url)) {
          return d.url;
        }
        // JSON 响应说明无试听地址（多为 VIP 曲目）；否则视为已重定向到音频，直接返回接口地址
        if (d && typeof d === "object" && (d.info || d.msg || d.code)) {
          throw new Error(Va(75) + (d.info || d.msg || "无试听地址"));
        }
        return f;
      });
    } // 同时拿到18位contentId与独立copyrightId时可直接解析；否则走搜索补齐参数
    var f = n.copyrightId ? String(n.copyrightId) : "";
    if (da(c) && f && !da(f)) {
      return o(c, f);
    }
    var g = z(n);
    if (!g) {
      return Promise.reject(new Error(Va(46)));
    }
    return k(ba + "?keyword=" + encodeURIComponent(g) + "&pageNo=1&pageSize=5", {
      method: "GET",
      headers: {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
        Referer: "https://music.migu.cn/"
      },
      timeout: 6000
    }).then(function (b) {
      var a = b && b.data;
      if (!a || !a.length) {
        throw new Error(Va(47));
      }
      // 优先匹配同名同歌手，其次同名，最后取第一条
      var c = null;
      var h = String(n.name || n.songName || "");
      var e = String(n.singer || n.artist || "");
      for (var f = 0; f < a.length; f++) {
        var i = !h || String(a[f].songName || "") === h;
        var l = !e || String(a[f].singer || "").indexOf(e) !== -1;
        if (i && l) {
          c = a[f];
          break;
        }
        if (!c && i) {
          c = a[f];
        }
      }
      if (!c) {
        c = a[0];
      }
      var p = c.contentId || c.songId || "";
      if (!p) {
        throw new Error(Va(48));
      }
      return o(p, c.copyrightId || "");
    });
  } // ========== 星海音乐源后端 - 多平台支持 (tx/kg/kw/wy/mg) ==========
  // 使用 yy.zddyr.top 后端，支持全平台高品质音源
  var fa = {
    tx: "qq",
    kg: "kg",
    kw: "kw",
    wy: "netease",
    mg: "migu"
  };
  var ga = Ta("xinghai");
  function ha(g, a, b) {
    var c = fa[g];
    if (!c) {
      return Promise.reject(new Error(Va(49)));
    }
    var d = g === Va(99) ? a.hash || a.songmid || a.id || "" : x(g, a);
    if (!d) {
      return Promise.reject(new Error(Va(50)));
    }
    var e = "source=" + encodeURIComponent(c) + "&songmid=" + encodeURIComponent(String(d)) + Va(91) + encodeURIComponent(b || "320k");
    // 酷狗额外参数
    if (g === Va(99)) {
      if (a.hash) {
        e += "&hash=" + encodeURIComponent(String(a.hash));
      }
      if (a.albumId) {
        e += "&albumId=" + encodeURIComponent(String(a.albumId));
      }
    }
    // 网易云额外参数
    if (g === Va(102)) {
      if (a.name) {
        e += "&name=" + encodeURIComponent(String(a.name));
      }
      if (a.singer) {
        e += "&singer=" + encodeURIComponent(String(a.singer));
      }
    }
    return k(ga + "?" + e, {
      method: "GET",
      timeout: 8000
    }).then(function (b) {
      if (b && b.code === 200 && b.url && l(b.url)) {
        return b.url;
      }
      throw new Error(Va(76) + (b && b.msg ? b.msg : "获取失败"));
    });
  } // ========== 收集の聚合接口 (tx) ==========
  var ia = Ta("shouji_tx");
  function ja(e, a, b) {
    if (e !== Va(100)) {
      return Promise.reject(new Error(Va(51)));
    }
    var c = x("tx", a) || w(a);
    if (!c) {
      return Promise.reject(new Error(Va(52)));
    }
    return k(ia + "&mid=" + encodeURIComponent(String(c)), {
      method: "GET",
      timeout: 5000
    }).then(function (c) {
      var a = c && (c.url || c.data && c.data.url) || "";
      if (l(a)) {
        return a;
      }
      throw new Error(Va(53));
    });
  } // ========== v2.2.0 新增可用源 ==========
  // HYW公益 - 全平台 (103.79.184.97 卡密鉴权，query 携带 key + X-Card-Key 头)
  var ka = Ta("hyw_free_api");
  var la = Ta("hyw_free_key");
  function ma(g, a, b) {
    var c = x(g, a);
    if (!c) {
      return Promise.reject(new Error(Va(54)));
    }
    // 该接口各平台仅开放 128k/320k/flac/flac24bit，其余音质映射到最接近档位
    var d = {
      "128k": "128k",
      "192k": "320k",
      "320k": "320k",
      flac: "flac",
      flac24bit: "flac24bit",
      hires: "flac24bit",
      jyeffect: "flac24bit",
      sky: "flac24bit",
      dolby: "flac24bit",
      atmos: "flac24bit",
      atmos_plus: "flac24bit",
      jymaster: "flac24bit",
      master: "flac24bit"
    };
    var e = d[b] || "320k";
    return k(ka + "?source=" + encodeURIComponent(g) + "&songId=" + encodeURIComponent(String(c)) + Va(91) + encodeURIComponent(e) + "&key=" + encodeURIComponent(la), {
      method: "GET",
      headers: {
        "User-Agent": "Mozilla/5.0",
        "X-Card-Key": la
      },
      timeout: 5000
    }).then(function (c) {
      var a = c && (c.url || c.data && c.data.url) || "";
      if (a && l(a)) {
        return a;
      }
      throw new Error(Va(77) + (c && (c.msg || c.message) || "获取失败"));
    });
  } // vkeys腾讯v2 - tx (api.vkeys.cn/v2/music/tencent/geturl?mid=&quality=)
  var na = Ta("vkeys_tx_v2");
  function oa(g, a, b) {
    if (g !== Va(100)) {
      return Promise.reject(new Error(Va(55)));
    }
    var c = x("tx", a);
    if (!c) {
      return Promise.reject(new Error(Va(56)));
    }
    var d = {
      "128k": "6",
      "192k": "7",
      "320k": "8",
      flac: "10",
      flac24bit: "11",
      hires: "11",
      jyeffect: "11",
      sky: "13",
      dolby: "13",
      atmos: "13",
      atmos_plus: "13",
      jymaster: "14",
      master: "14"
    };
    var e = d[b] || "8";
    return k(na + "?mid=" + encodeURIComponent(String(c)) + Va(91) + e, {
      method: "GET",
      timeout: 6000
    }).then(function (c) {
      var a = c && c.data && (c.data.url || c.data.link);
      if (a && l(a)) {
        return a;
      }
      throw new Error(Va(78) + (c && (c.message || c.msg) || "未返回有效链接"));
    });
  } // aa.cab - tx 搜索式取链 (a.aa.cab/qq.music?msg=&n=1&type=)
  var pa = Ta("aa_cab_tx");
  function qa(g, a, b) {
    if (g !== Va(100)) {
      return Promise.reject(new Error(Va(57)));
    }
    var c = z(a);
    if (!c) {
      return Promise.reject(new Error(Va(58)));
    }
    // type: 0=M500(128k) 1=M800(320k) 4=F000(FLAC) 5=母带
    var d = {
      "128k": "0",
      "192k": "1",
      "320k": "1",
      flac: "4",
      flac24bit: "4",
      hires: "4",
      jyeffect: "4",
      sky: "5",
      dolby: "5",
      atmos: "5",
      atmos_plus: "5",
      jymaster: "5",
      master: "5"
    };
    var e = d[b] || "1";
    return k(pa + "?msg=" + encodeURIComponent(c) + "&n=1&type=" + e, {
      method: "GET",
      timeout: 6000
    }).then(function (c) {
      if (c) {
        var a = c.data && (c.data.music || c.data.url) || c.playUrl || c.url;
        if (a && l(a)) {
          return a;
        }
      }
      throw new Error(Va(59));
    });
  } // oiapi咪咕 - mg 搜索式取链 (oiapi.net/api/MiGu_Music?msg=&br=&n=)
  var ra = Ta("oiapi_migu");
  function sa(g, a, b) {
    if (g !== Va(101)) {
      return Promise.reject(new Error(Va(60)));
    }
    var c = z(a);
    if (!c) {
      return Promise.reject(new Error(Va(61)));
    }
    var d = {
      "128k": "LQ",
      "192k": "HQ",
      "320k": "HQ",
      flac: "SQ",
      flac24bit: "SQ",
      hires: "SQ",
      jyeffect: "SQ",
      sky: "SQ",
      dolby: "SQ",
      atmos: "SQ",
      atmos_plus: "SQ",
      jymaster: "SQ",
      master: "SQ"
    };
    var e = d[b] || "HQ";
    return k(ra + "?msg=" + encodeURIComponent(c) + "&br=" + e + "&n=1", {
      method: "GET",
      timeout: 6000
    }).then(function (c) {
      var a = c && (c.data && c.data.url || c.url);
      if (a && l(a)) {
        return a;
      }
      throw new Error(Va(62));
    });
  } // 酷我官方mobi - kw (nmobi.kuwo.cn 官方接口，响应最快~0.1s)
  var ta = Ta("kw_mobi");
  function ua(f, a, b) {
    if (f !== Va(103)) {
      return Promise.reject(new Error(Va(63)));
    }
    var c = x("kw", a);
    if (!c) {
      return Promise.reject(new Error(Va(64)));
    }
    // 实测该接口 flac 参数返回 48k AAC，故 flac 及以上音质统一降级为 320kmp3
    var d = b === "128k" ? "128kmp3" : "320kmp3";
    return k(ta + "?f=web&user=0&source=kwplayerhd_ar_6.6.6.6_tianbao_T1A_qirui.apk&type=convert_url_with_sign&rid=" + encodeURIComponent(String(c)) + "&br=" + d, {
      method: "GET",
      headers: {
        "User-Agent": "Mozilla/5.0 (Linux; Android) AppleWebKit/537.36"
      },
      timeout: 5000
    }).then(function (c) {
      var a = c && c.data && c.data.url;
      if (a && l(a)) {
        return a;
      }
      throw new Error(Va(79) + (c && (c.msg || c.message) || "获取失败"));
    });
  } // ========== API 源列表 ==========
  // txTier: TX平台专用分层竞速优先级，1=优先层（真实音质、响应快），2=备用层
  const va = [
  // 公网源
  {
    name: Va(0),
    fetch: R,
    sources: [Va(100)],
    txTier: 2
  }, {
    name: Va(1),
    fetch: B,
    sources: [Va(103)]
  }, {
    name: Va(2),
    fetch: D,
    sources: [Va(100)],
    txTier: 1
  }, {
    name: Va(3),
    fetch: aa,
    sources: [Va(100)],
    txTier: 1
  }, {
    name: Va(4),
    fetch: oa,
    sources: [Va(100)],
    txTier: 1
  }, {
    name: Va(5),
    fetch: F,
    sources: [Va(99)]
  }, {
    name: Va(6),
    fetch: Y,
    sources: [Va(103), Va(99), Va(100), Va(102)],
    txTier: 2
  }, {
    name: Va(7),
    fetch: T,
    sources: [Va(102)]
  }, {
    name: Va(8),
    fetch: $,
    sources: [Va(102)]
  }, {
    name: Va(9),
    fetch: V,
    sources: [Va(102), Va(103)]
  }, {
    name: Va(10),
    fetch: H,
    sources: [Va(102), Va(100), Va(99), Va(103), Va(101)]
  },
  // v1.1.7 新增源
  {
    name: Va(11),
    fetch: M,
    sources: [Va(100)],
    txTier: 2
  }, {
    name: Va(12),
    fetch: ea,
    sources: [Va(101)]
  },
  // v1.3.0 新增源 - 星海后端
  {
    name: Va(13),
    fetch: ha,
    sources: [Va(100), Va(99), Va(103), Va(102), Va(101)],
    txTier: 2
  }, {
    name: Va(14),
    fetch: ja,
    sources: [Va(100)],
    txTier: 2
  },
  // v2.2.0 新增可用源 - HYW公益 / vkeys v2 / aa.cab / oiapi咪咕 / 酷我mobi
  {
    name: Va(15),
    fetch: ma,
    sources: [Va(100), Va(99), Va(103), Va(102)],
    txTier: 2
  }, {
    name: Va(16),
    fetch: qa,
    sources: [Va(100)],
    txTier: 2
  }, {
    name: Va(17),
    fetch: sa,
    sources: [Va(101)]
  }, {
    name: Va(18),
    fetch: ua,
    sources: [Va(103)]
  }];

  // ========== 核心逻辑：并发竞速策略 ==========
  // 对同一平台的所有可用源同时发起请求，取最快返回的有效URL
  // 每个源设置4秒超时，避免慢速API阻塞；任一成功即返回
  var wa = 4000;

  // 并发竞速：所有候选源同时请求，任一成功即返回
  function xa(i, m, b, n) {
    if (i.length === 0) {
      return Promise.reject(new Error(Va(65)));
    }
    // 单源直接返回（带超时）
    if (i.length === 1) {
      var a = Date.now();
      return j(i[0].fetch(m, b, n), wa).then(function (b) {
        var c = Date.now() - a;
        var d = !!(b && l(b));
        u(m, i[0].name, d, c, n);
        if (d) {
          return b;
        }
        return Promise.reject(new Error(i[0].name + ": 无效URL"));
      }).catch(function (b) {
        var c = Date.now() - a;
        u(m, i[0].name, false, c, n);
        v(m, n, i);
        throw b;
      });
    }
    // 多源并发竞速
    var d = [];
    var g = false;
    return new Promise(function (h, a) {
      var c = i.length;
      function o() {
        c--;
        if (c === 0 && !g) {
          v(m, n, i);
          a(new Error(Va(80) + d.join("\n")));
        }
      }
      for (var e = 0; e < i.length; e++) {
        (function (k) {
          var a = Date.now();
          j(k.fetch(m, b, n), wa).then(function (b) {
            if (g) {
              return;
            }
            var c = Date.now() - a;
            if (b && l(b)) {
              u(m, k.name, true, c, n);
              g = true;
              h(b);
            } else {
              u(m, k.name, false, c, n);
              d.push(k.name + ": 无效URL");
              o();
            }
          }).catch(function (b) {
            if (g) {
              return;
            }
            var c = Date.now() - a;
            u(m, k.name, false, c, n);
            d.push(k.name + ": " + (b.message || b));
            o();
          });
        })(i[e]);
      }
    });
  } // TX 平台延迟并发：优先层立即启动，备用层延迟500ms加入竞速
  // 避免串行等待（原方案最坏12s），最坏情况仅需5s超时
  function ya(e, k, n, c, o) {
    if (e.length === 0 && k.length === 0) {
      return Promise.reject(new Error(Va(65)));
    }
    if (k.length === 0) {
      return xa(e, n, c, o);
    }
    if (e.length === 0) {
      return xa(k, n, c, o);
    }
    var f = [];
    var g = false;
    var d = 0;
    var a = e.concat(k);
    return new Promise(function (b, h) {
      function p() {
        d--;
        if (d === 0 && !g) {
          v(n, o, a);
          h(new Error(Va(80) + f.join("\n")));
        }
      }
      function i(h) {
        d++;
        var a = Date.now();
        j(h.fetch(n, c, o), wa).then(function (c) {
          if (g) {
            return;
          }
          var d = Date.now() - a;
          if (c && l(c)) {
            u(n, h.name, true, d, o);
            g = true;
            b(c);
          } else {
            u(n, h.name, false, d, o);
            f.push(h.name + ": 无效URL");
            p();
          }
        }).catch(function (b) {
          if (g) {
            return;
          }
          var c = Date.now() - a;
          u(n, h.name, false, c, o);
          f.push(h.name + ": " + (b.message || b));
          p();
        });
      } // 优先层立即启动
      for (var m = 0; m < e.length; m++) {
        i(e[m]);
      }
      // 备用层延迟300ms启动，给优先层先发优势
      setTimeout(function () {
        if (g) {
          return;
        }
        for (var b = 0; b < k.length; b++) {
          i(k[b]);
        }
      }, 300);
    });
  }
  const za = function (i, a, b) {
    // 版本被面板停用（精确清单/版本下限）时拒绝所有请求，与面板说明对齐
    if (La) {
      return Promise.reject(new Error(Va(66)));
    }
    // 应用面板的最大音质限制：超出档位自动降级到允许的最高音质
    b = Ka(b);
    // 筛选支持该平台的源
    var j = [];
    for (var k = 0; k < va.length; k++) {
      if (va[k].sources.indexOf(i) !== -1) {
        j.push(va[k]);
      }
    }
    if (j.length === 0) {
      return Promise.reject(new Error(Va(81) + i));
    }
    // 按面板统计的请求速度（平均响应时间）重排优先级：快者先发
    j = Xa(j, i);
    // TX 平台使用延迟并发：优先层立即启动，备用层延迟300ms加入
    // 优先层为真实音质源（念心TX、vkeys腾讯/v2），备用层为玉宁熙、aa.cab 等
    if (i === Va(100)) {
      var l = [];
      var f = [];
      for (var g = 0; g < j.length; g++) {
        if (j[g].txTier === 1) {
          l.push(j[g]);
        } else {
          f.push(j[g]);
        }
      }
      return ya(l, f, i, a, b);
    }
    return xa(j, i, a, b);
  };

  // ========== _0x6b10 对象（对齐官方示例结构）==========
  const Aa = {
    [Va(103)]: {
      [Va(98)]: function (c, a) {
        return za("kw", c, a);
      }
    },
    [Va(99)]: {
      [Va(98)]: function (c, a) {
        return za("kg", c, a);
      }
    },
    [Va(100)]: {
      [Va(98)]: function (c, a) {
        return za("tx", c, a);
      }
    },
    [Va(102)]: {
      [Va(98)]: function (c, a) {
        return za("wy", c, a);
      }
    },
    [Va(101)]: {
      [Va(98)]: function (c, a) {
        return za("mg", c, a);
      }
    }
  };

  // 注册应用 API 请求事件
  // 官方约定：回调必须返回 Promise；此处对平台缺失/参数缺失/同步异常全部兜底为 Promise.reject，
  // 避免同步抛错掩盖真实原因（初始化与请求阶段的异常在部分宿主中会导致脚本判定失败）
  a(Qa.request, function (h) {
    try {
      var a = h ? h.source : "";
      var b = h ? h.action : "";
      var c = h && h.info || {};
      switch (b) {
        case Va(98):
          {
            var d = Aa[a];
            if (!d || typeof d[Va(98)] !== "function") {
              return Promise.reject(new Error(Va(82) + a));
            }
            if (!c.musicInfo) {
              return Promise.reject(new Error(Va(67)));
            }
            return d[Va(98)](c.musicInfo, c.type).catch(function (b) {
              f(b);
              return Promise.reject(b);
            });
          }
        default:
          g("action(" + b + ") not support");
          return Promise.reject(new Error(Va(68)));
      }
    } catch (b) {
      return Promise.reject(b);
    }
  });

  // ========== 更新检查 ==========
  // 脚本初始化时异步检查面板是否有新版本，若有则发送 updateAlert 事件
  // 参考文档: https://www.lxmusic.cn/docs/music-source/
  var Ba = "v2.2.1-fix";
  function Ca(i, c) {
    var d = String(i).replace(/^v/i, "").split(".");
    var e = String(c).replace(/^v/i, "").split(".");
    var a = Math.max(d.length, e.length);
    for (var b = 0; b < a; b++) {
      var j = parseInt(d[b] || "0", 10);
      var k = parseInt(e[b] || "0", 10);
      if (j > k) {
        return 1;
      }
      if (j < k) {
        return -1;
      }
    }
    return 0;
  } // ========== 消息收集器 ==========
  // LX 文档硬性限制：updateAlert 每次运行脚本只能调用一次（官方 preload 再次调用直接 reject）。
  // 因此广播/定向通知/停用提示/更新日志/用户ID 全部先入队，最后合并为唯一一条弹窗。
  var Da = [];
  function Ea(b) {
    if (!b) {
      return;
    }
    Da.push(String(b));
  } // 合并收集到的全部消息并只发送一次 updateAlert（总量截断 1024 字符）
  function Fa(a) {
    if (Da.length === 0) {
      return;
    }
    var b = Da.join(`

`);
    if (b.length > 1024) {
      b = b.substring(0, 1024);
    }
    Da = [];
    try {
      var d = Sa(Qa.updateAlert, {
        log: b,
        updateUrl: a || ""
      });
      // send 返回 Promise；官方环境重复调用等异常在此兜底，避免未处理 rejection
      if (d && typeof d.catch === "function") {
        d.catch(function () {});
      }
    } catch (b) {}
  } // ========== 最大音质限制（面板 check_update 下发，用户规则优先于全局规则）==========
  var Ha = "";
  // 档位高低：standard <= 128k <= 320k <= flac <= flac24bit
  var Ia = {
    standard: 0,
    "128k": 1,
    "320k": 2,
    flac: 3,
    flac24bit: 4
  };
  function Ka(f) {
    if (!Ha) {
      return f;
    }
    var a = String(f || "128k").toLowerCase();
    var b = String(Ha).toLowerCase();
    var c = Ia[a];
    var d = Ia[b];
    // 未知档位不做降级，避免误伤应用新增的音质
    if (c === undefined || d === undefined || c <= d) {
      return f;
    }
    return b;
  } // ========== 版本停用 / 请求速度优先级（面板 check_update 下发）==========
  // 停用标志：命中精确停用清单或版本低于下限时置真，后续所有请求直接拒绝
  var La = false;
  // 请求速度优先级：平台 => 按平均响应时间升序的接口名数组
  var Wa = {};
  // 按面板下发的速度优先级排序候选源（未记录的接口排尾；无数据保持原顺序）
  function Xa(f, a) {
    var b = Wa ? Wa[a] : null;
    if (!b || b.length === 0) {
      return f;
    }
    var g = {};
    for (var c = 0; c < b.length; c++) {
      g[b[c]] = c;
    }
    return f.slice().sort(function (d, c) {
      var a = g[d.name] !== undefined ? g[d.name] : 9999;
      var b = g[c.name] !== undefined ? g[c.name] : 9999;
      return a - b;
    });
  }
  function Oa() {
    if (!Ua) {
      return;
    }
    // 从 report.php 地址推导出 api.php 地址
    var b = Ua.replace(/\/report\.php.*$/, Va(83));
    if (b === Ua) {
      return;
    }
    // 附带用户标识，便于面板统计与定向下发
    b += Va(88) + encodeURIComponent(n || "");
    k(b, {
      method: "GET",
      timeout: 5000
    }).then(function (f) {
      if (!f) {
        return;
      }
      // 面板公告（广播）与定向通知 —— 先入队，最后统一弹出
      Ea(f.broadcast);
      Ea(f.notify);
      // 面板下发的最大音质限制，后续播放请求按此降级
      if (f.max_quality !== undefined) {
        Ha = String(f.max_quality || "");
      }
      // 按请求速度排序的接口优先级（v2.2.1+）
      if (f.source_priority && typeof f.source_priority === "object") {
        Wa = f.source_priority;
      }
      // 版本停用判断：精确停用清单 + 版本下限（一键停用旧版本下发）
      var a = f.disabled_versions;
      var b = Object.prototype.toString.call(a) === "[object Array]" && a.indexOf(Ba) !== -1;
      var g = f.disabled_below ? String(f.disabled_below) : "";
      if (!b && g && Ca(Ba, g) < 0) {
        b = true;
      }
      if (b) {
        La = true;
        Ea("您当前使用的版本 " + Ba + " 已被停用，请升级到最新版本。");
      }
      // 更新日志（停用状态下不再提示更新，只提示升级）
      var d = "";
      if (!b && f.version && Ca(f.version, Ba) > 0) {
        Ea(f.log || "发现新版本 " + f.version);
        d = f.updateUrl || "";
      }
      // 推送用户ID：随更新提示/公告内容一起弹出（v2.2.1+）
      if (f.push_user_id && n) {
        Ea("你的用户ID：" + n + "\n（可向管理员报备此ID，用于换取定向通知/白名单/音质权限，请勿泄露）");
      }
      // 唯一一次 updateAlert：合并广播/通知/停用/更新/用户ID
      Fa(d);
    }).catch(function (b) {
      // 更新检查失败不影响正常使用
    });
  } // 脚本初始化完成后发送 inited 事件告知应用
  // 官方约定：send(inited) 之前任何异常都会导致脚本初始化失败，
  // 因此将 inited 放在最前，用户标识/IP 检测与面板检查等非关键初始化放在其后并各自兜底
  Sa(Qa.inited, {
    sources: {
      [Va(103)]: {
        name: "酷我音乐",
        type: "music",
        actions: [Va(98)],
        qualitys: ["128k", "320k", "flac", "flac24bit"]
      },
      [Va(99)]: {
        name: "酷狗音乐",
        type: "music",
        actions: [Va(98)],
        qualitys: ["128k", "320k", "flac", "flac24bit"]
      },
      [Va(100)]: {
        name: "QQ音乐",
        type: "music",
        actions: [Va(98)],
        // 仅声明文档有效音质（128k/320k/flac/flac24bit），非法值会被官方过滤且可能导致严格端校验失败
        qualitys: ["128k", "320k", "flac", "flac24bit"]
      },
      [Va(102)]: {
        name: "网易云音乐",
        type: "music",
        actions: [Va(98)],
        qualitys: ["128k", "320k", "flac", "flac24bit"]
      },
      [Va(101)]: {
        name: "咪咕音乐",
        type: "music",
        actions: [Va(98)],
        qualitys: ["128k", "320k", "flac", "flac24bit"]
      }
    }
  });
  try {
    p();
  } catch (b) {}
  try {
    i();
  } catch (b) {}
  try {
    q();
  } catch (b) {}
  try {
    Oa();
  } catch (b) {}

  // ===== 测试钩子（仅沙箱回归测试显式开启；LX 环境不定义 __HM_TEST__，自动跳过） =====
  if (typeof globalThis !== "undefined" && globalThis.__HM_TEST__) {
    globalThis.__hm_test = {
      version: Ba,
      API_SOURCES: va,
      isValidUrl: l,
      handleGetMusicUrl: za,
      fetchHywFree: ma,
      fetchVkeysV2: oa,
      fetchAaCabTx: qa,
      fetchOiapiMigu: sa,
      fetchKwMobi: ua,
      sortByPriority: function (c, a) {
        return Xa(c, a);
      },
      setPriority: function (b) {
        Wa = b;
      },
      isDisabled: function () {
        return La;
      }
    };
  }
})();