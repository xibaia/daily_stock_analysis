/**
 * 复制文本到剪贴板，支持非安全上下文（HTTP）降级
 *
 * 在 HTTPS / localhost 等安全上下文中优先使用 navigator.clipboard.writeText()；
 * 在 HTTP 内网等非安全上下文中自动降级到 document.execCommand('copy')。
 *
 * @param text 要复制的文本
 * @returns 是否复制成功
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  // 优先使用现代 Clipboard API（仅在安全上下文中可用）
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // 如果 Clipboard API 失败（权限被拒等），继续走降级方案
    }
  }

  // 降级方案：execCommand 必须在同步上下文中执行，
  // 因此不能与 await 混在同一条执行路径中
  return syncCopyToClipboard(text);
}

/**
 * 同步降级复制方案。
 *
 * 浏览器要求 execCommand('copy') 必须在用户交互（如 click）的
 * 同步执行路径中调用，不能包装在 async 函数里。
 */
function syncCopyToClipboard(text: string): boolean {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  textarea.style.top = '0';
  textarea.setAttribute('aria-hidden', 'true');

  document.body.appendChild(textarea);
  textarea.focus();
  textarea.setSelectionRange(0, text.length);

  let success = false;
  try {
    success = document.execCommand('copy');
  } catch {
    success = false;
  }
  document.body.removeChild(textarea);
  return success;
}
