// 律问 · 网络层：普通请求 + SSE 流式问答
const { createUtf8Decoder } = require("./utf8");

function baseUrl() {
  return getApp().baseUrl().replace(/\/+$/, "");
}

function token() {
  return getApp().globalData.token || "";
}

function request(path, { method = "GET", data = null } = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: baseUrl() + path,
      method,
      data: data || undefined,
      header: { "X-Token": token() },
      success: (res) => {
        if (res.statusCode === 401) { reject({ code: 401, message: "需要访问口令" }); return; }
        if (res.statusCode === 429) { reject({ code: 429, message: "提问太频繁，请稍候" }); return; }
        if (res.statusCode >= 400) { reject({ code: res.statusCode, message: (res.data && res.data.detail) || "请求失败" }); return; }
        resolve(res.data);
      },
      fail: () => reject({ code: 0, message: "网络错误：请检查「关于」页里的服务器地址" }),
    });
  });
}

/**
 * 流式问答。回调：onHits(hits) onDelta(text) onDone() onError({message, code})
 * 返回 requestTask，可 abort()
 */
function askStream(question, { onHits, onDelta, onDone, onError }) {
  const decode = createUtf8Decoder();
  let buf = "";
  let settled = false; // 防止 headers/success/done 多路重复回调
  const settle = (fn, arg) => {
    if (settled) return;
    settled = true;
    fn && fn(arg);
  };
  const dispatch = (raw) => {
    if (settled || !raw.startsWith("data:")) return;
    let ev;
    try { ev = JSON.parse(raw.slice(5).trim()); } catch { return; }
    if (ev.type === "hits") onHits && onHits(ev.hits);
    else if (ev.type === "delta") onDelta && onDelta(ev.text);
    else if (ev.type === "done") settle(onDone);
    else if (ev.type === "error") onError && onError({ message: ev.message });
  };

  const task = wx.request({
    url: baseUrl() + "/api/ask",
    method: "POST",
    enableChunked: true,
    header: { "Content-Type": "application/json", "X-Token": token() },
    data: { question },
    success: (res) => {
      // enableChunked 下若未走到流式回调，这里兜底判定状态码
      if (settled) return;
      if (res.statusCode === 401) settle(onError, { code: 401, message: "需要访问口令" });
      else if (res.statusCode >= 400) settle(onError, { code: res.statusCode, message: "服务错误 " + res.statusCode });
      else settle(onDone);
    },
    fail: () => settle(onError, { message: "网络错误：请检查「关于」页里的服务器地址" }),
  });

  // 响应头一到就判定状态码：401/5xx 立即失败并中断，不 等 success
  task.onHeadersReceived((res) => {
    const code = res.statusCode || 0;
    if (code === 401) {
      settle(onError, { code: 401, message: "需要访问口令" });
      try { task.abort(); } catch {}
    } else if (code >= 400) {
      settle(onError, { code, message: "服务错误 " + code });
      try { task.abort(); } catch {}
    }
  });

  task.onChunkReceived((res) => {
    buf += decode(res.data);
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (chunk) dispatch(chunk);
    }
  });
  return task;
}

module.exports = { request, askStream, baseUrl, token };
