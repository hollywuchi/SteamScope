/**
 * Cloudflare Pages 边缘反向代理函数
 * 路由：/api/* -> 代理转发给后端 Flask 服务
 * 优势：
 * 1. 纯服务端代理（状态码 200），浏览器无感、无跨域问题
 * 2. 避免 Cloudflare _redirects 无法指向外部完整 URL 的限制 (代码: 100324)
 * 3. 优先读取 Cloudflare 网页后台配置的 BACKEND_URL 环境变量，安全隐藏服务器真实 IP
 */
export async function onRequest(context) {
  const url = new URL(context.request.url);

  // 优先从 Cloudflare 后台环境变量获取，若未配置则回退到当前域名或你的后端域名
  const backend = context.env.BACKEND_URL || "https://steam.skycat.studio";

  // 拼接后端目标 URL (保留 /api/... 路径与 ?query 参数)
  const targetUrl = new URL(url.pathname + url.search, backend);

  // 处理客户端请求头，重置 Host 头以适配反向代理
  const newHeaders = new Headers(context.request.headers);
  newHeaders.set("Host", targetUrl.host);
  newHeaders.set("X-Forwarded-Host", url.host);
  newHeaders.set("X-Forwarded-Proto", url.protocol.replace(":", ""));

  const requestInit = {
    method: context.request.method,
    headers: newHeaders,
    redirect: "follow",
  };

  // 非 GET/HEAD 请求保留 body 流
  if (context.request.method !== "GET" && context.request.method !== "HEAD") {
    requestInit.body = context.request.body;
  }

  try {
    const response = await fetch(targetUrl.toString(), requestInit);

    // 复制响应头并增加 CORS 支持
    const respHeaders = new Headers(response.headers);
    respHeaders.set("Access-Control-Allow-Origin", "*");
    respHeaders.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
    respHeaders.set("Access-Control-Allow-Headers", "Content-Type, Authorization");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: respHeaders,
    });
  } catch (err) {
    return new Response(JSON.stringify({
      code: 502,
      message: `Cloudflare Pages 边缘代理无法连接后端: ${err.message}`,
      target: targetUrl.toString()
    }), {
      status: 502,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*"
      }
    });
  }
}
