/**
 * Cloudflare Pages 边缘反向代理函数
 * 路由：/api/* -> 代理转发给 Azure VM 后端 Flask 服务
 */
export async function onRequest(context) {
  const url = new URL(context.request.url);

  // 1. 读取 Cloudflare 网页后台配置的私密环境变量 BACKEND_URL
  const backend = context.env.BACKEND_URL;

  // 防护与引导：若未配置或误配为前端自身域名，给出明确诊断提示，避免自环死循环
  if (!backend || backend.includes(url.host)) {
    return new Response(JSON.stringify({
      code: 500,
      error: "BACKEND_URL_NOT_CONFIGURED",
      message: "Cloudflare 边缘代理未检测到有效的后端地址 (BACKEND_URL)。",
      solution: "请前往 Cloudflare Pages 后台 -> Settings -> Environment variables 添加 BACKEND_URL = http://你的VM公网IP:5000，并在 Deployments 页面点击【重新部署 (Retry deployment)】！",
      current_env: backend || "未设置"
    }, null, 2), {
      status: 500,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*"
      }
    });
  }

  // 拼接后端目标 URL (保留 /api/... 路径与 ?query 参数)
  const targetUrl = new URL(url.pathname + url.search, backend);

  // 重置 Host 头以适配反向代理
  const newHeaders = new Headers(context.request.headers);
  newHeaders.set("Host", targetUrl.host);
  newHeaders.set("X-Forwarded-Host", url.host);
  newHeaders.set("X-Forwarded-Proto", url.protocol.replace(":", ""));

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
      error: "BACKEND_UNREACHABLE",
      message: `Cloudflare 边缘代理连接后端失败: ${err.message}`,
      target_url: targetUrl.toString(),
      diagnosis: "请按顺序排查：1. Azure 控制台 VM 的【网络安全组(NSG)】是否添加入站规则放行 5000 端口；2. VM 内部是否开启了 ufw (执行 sudo ufw allow 5000)；3. 虚拟机中 python app.py 是否在正常运行中。"
    }, null, 2), {
      status: 502,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*"
      }
    });
  }
}
