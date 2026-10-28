/**
 * Cloudflare Pages Advanced 模式核心代理脚本 (_worker.js)
 * 放置在 templates/ 构建输出目录中，自动激活 Cloudflare Worker 运行环境，
 * 解锁 Cloudflare 仪表盘中的【运行时变量和密钥】功能！
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. 拦截所有 /api/* 的请求并转发给 Azure VM 后端 Flask 服务
    if (url.pathname.startsWith("/api/")) {
      // 优先从环境变量获取，默认使用通过 Cloudflare 橙色云朵加密保护的后端安全域名
      const backend = env.BACKEND_URL || "https://api.skycat.studio";

      const targetUrl = new URL(url.pathname + url.search, backend);
      const newHeaders = new Headers(request.headers);
      newHeaders.set("Host", targetUrl.host);

      const modifiedRequest = new Request(targetUrl, {
        method: request.method,
        headers: newHeaders,
        body: (request.method !== "GET" && request.method !== "HEAD") ? request.body : undefined,
        redirect: request.redirect,
      });

      try {
        const apiResponse = await fetch(modifiedRequest);
        const respHeaders = new Headers(apiResponse.headers);
        respHeaders.set("Access-Control-Allow-Origin", "*");
        respHeaders.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
        respHeaders.set("Access-Control-Allow-Headers", "Content-Type, Authorization");

        return new Response(apiResponse.body, {
          status: apiResponse.status,
          statusText: apiResponse.statusText,
          headers: respHeaders,
        });
      } catch (e) {
        return new Response(JSON.stringify({
          code: 502,
          error: "PROXY_FAILED",
          message: `Cloudflare 边缘节点无法连接至目标后端: ${e.message}`,
          target_url: targetUrl.toString()
        }, null, 2), {
          status: 502,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*"
          }
        });
      }
    }

    // 2. 其余所有请求（HTML 页面、视频、图片等）由 Cloudflare Pages 边缘静态分发
    return env.ASSETS.fetch(request);
  },
};
