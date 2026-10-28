/**
 * Cloudflare Pages 官方标准边缘函数
 * 路径：/api/* -> 读取后台 BACKEND_URL 环境变量，代理转发至后端
 */
export async function onRequest(context) {
  const url = new URL(context.request.url);

  // 从 Cloudflare 后台设置读取私密环境变量 BACKEND_URL
  const backend = context.env.BACKEND_URL;

  if (!backend) {
    return new Response(JSON.stringify({
      code: 500,
      error: "BACKEND_URL_NOT_SET",
      message: "未在 Cloudflare 后台设置 BACKEND_URL 环境变量。请前往设置添加：BACKEND_URL = http://你的VM公网IP:5000"
    }, null, 2), {
      status: 500,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*"
      }
    });
  }

  const targetUrl = new URL(url.pathname + url.search, backend);
  const newHeaders = new Headers(context.request.headers);
  newHeaders.set("Host", targetUrl.host);

  const requestInit = {
    method: context.request.method,
    headers: newHeaders,
    redirect: "follow",
  };

  if (context.request.method !== "GET" && context.request.method !== "HEAD") {
    requestInit.body = context.request.body;
  }

  try {
    const response = await fetch(targetUrl.toString(), requestInit);
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
      error: "BACKEND_CONNECT_FAILED",
      message: `无法连接到后端服务器: ${err.message}`
    }, null, 2), {
      status: 502,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*"
      }
    });
  }
}
