// 律问 · 关于页：服务器地址 / 口令 / 用法说明
const api = require("../../utils/api");

Page({
  data: {
    base: "",
    baseInput: "",
    pwd: "",
    hasToken: false,
    stats: null,
  },

  onShow() {
    const base = wx.getStorageSync("lawq_base") || "";
    this.setData({
      base,
      baseInput: base,
      hasToken: !!(wx.getStorageSync("lawq_token") || getApp().globalData.token),
    });
    this.loadStats();
  },

  async loadStats() {
    try {
      const s = await api.request("/api/stats");
      this.setData({ stats: s });
    } catch (e) { /* 静默：可能是地址未配置 */ }
  },

  onBase(e) { this.setData({ baseInput: e.detail.value }); },
  saveBase() {
    const v = this.data.baseInput.trim().replace(/\/+$/, "");
    if (v && !/^https?:\/\//.test(v)) {
      wx.showToast({ title: "地址需以 http:// 或 https:// 开头", icon: "none" });
      return;
    }
    if (v) wx.setStorageSync("lawq_base", v);
    else wx.removeStorageSync("lawq_base");
    this.setData({ base: v });
    wx.showToast({ title: "已保存", icon: "success" });
    this.loadStats();
  },

  onPwd(e) { this.setData({ pwd: e.detail.value }); },
  doLogin() {
    wx.request({
      url: api.baseUrl() + "/api/login",
      method: "POST",
      data: { password: this.data.pwd },
      success: (res) => {
        if (res.statusCode !== 200) { wx.showToast({ title: "口令不正确", icon: "none" }); return; }
        getApp().globalData.token = res.data.token;
        wx.setStorageSync("lawq_token", res.data.token);
        this.setData({ hasToken: true, pwd: "" });
        wx.showToast({ title: "已登录", icon: "success" });
      },
      fail: () => wx.showToast({ title: "网络错误，请先检查服务器地址", icon: "none" }),
    });
  },
});
