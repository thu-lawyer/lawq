// 律问 · 小程序入口
App({
  globalData: {
    // 服务器地址优先读本地设置（关于页可改），未设置时用默认值
    token: wx.getStorageSync("lawq_token") || "",
  },
  baseUrl() {
    return wx.getStorageSync("lawq_base") || require("./config").BASE_URL;
  },
});
