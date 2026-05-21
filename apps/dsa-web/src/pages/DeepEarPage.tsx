import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink, RadioTower, RefreshCcw } from 'lucide-react';
import { deepearApi } from '../api/deepear';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import type { DeepEarSessionResponse } from '../types/deepear';
import { ApiErrorAlert, AppPage, Button, Card, EmptyState, InlineAlert, Loading, PageHeader } from '../components/common';

const SSO_MESSAGE_TYPE = 'DSA_DEEPEAR_SSO';

function buildEmbeddedLoginUrl(publicUrl: string): string {
  const url = new URL('/login', publicUrl.endsWith('/') ? publicUrl : `${publicUrl}/`);
  url.searchParams.set('embedded', '1');
  return url.toString();
}

const DeepEarPage: React.FC = () => {
  const [session, setSession] = useState<DeepEarSessionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    document.title = 'DeepEar - DSA';
  }, []);

  const loadSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await deepearApi.getSession();
      setSession(response);
    } catch (err: unknown) {
      setSession(null);
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const embedUrl = useMemo(() => {
    if (!session?.enabled || !session.publicUrl) {
      return '';
    }
    return buildEmbeddedLoginUrl(session.publicUrl);
  }, [session]);

  const targetOrigin = useMemo(() => {
    if (!session?.enabled || !session.publicUrl) {
      return '';
    }
    return new URL(session.publicUrl).origin;
  }, [session]);

  const ssoPayload = useMemo(() => {
    if (!session?.enabled || !session.token || !session.user) {
      return null;
    }
    return {
      type: SSO_MESSAGE_TYPE,
      token: session.token,
      user: session.user,
    };
  }, [session]);

  const postSsoMessage = useCallback(
    (targetWindow: Window | null | undefined) => {
      if (!targetWindow || !targetOrigin || !ssoPayload) {
        return;
      }
      targetWindow.postMessage(ssoPayload, targetOrigin);
    },
    [ssoPayload, targetOrigin],
  );

  const handleIframeLoad = useCallback(() => {
    postSsoMessage(iframeRef.current?.contentWindow);
    window.setTimeout(() => postSsoMessage(iframeRef.current?.contentWindow), 500);
  }, [postSsoMessage]);

  const handleOpenInNewTab = useCallback(() => {
    if (!embedUrl) {
      return;
    }
    const popup = window.open(embedUrl, '_blank');
    if (!popup) {
      return;
    }
    window.setTimeout(() => postSsoMessage(popup), 400);
    window.setTimeout(() => postSsoMessage(popup), 1200);
  }, [embedUrl, postSsoMessage]);

  return (
    <AppPage className="space-y-6">
      <PageHeader
        eyebrow="External Workspace"
        title="DeepEar"
        description="以嵌入方式访问 DeepEar 控制台，使用当前 DSA 登录态桥接到统一服务账号。"
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => void loadSession()}
              isLoading={loading}
              loadingText="刷新中..."
            >
              <RefreshCcw className="h-4 w-4" />
              刷新连接
            </Button>
            <Button variant="outline" onClick={handleOpenInNewTab} disabled={!embedUrl || loading}>
              <ExternalLink className="h-4 w-4" />
              新标签页打开
            </Button>
          </>
        }
      />

      {loading ? (
        <Card>
          <Loading label="正在连接 DeepEar..." />
        </Card>
      ) : null}

      {!loading && error ? (
        <ApiErrorAlert error={error} actionLabel="重新连接" onAction={() => void loadSession()} />
      ) : null}

      {!loading && !error && session && !session.enabled ? (
        <EmptyState
          title="DeepEar 集成尚未启用"
          description="请先在后端环境变量中启用 DeepEar 桥接配置，然后刷新本页。"
          icon={<RadioTower className="h-8 w-8" />}
          action={
            <Button variant="secondary" onClick={() => void loadSession()}>
              重新检查
            </Button>
          }
        />
      ) : null}

      {!loading && !error && session?.enabled && embedUrl ? (
        <Card padding="none" className="overflow-hidden">
          <div className="border-b border-border/60 px-5 py-4">
            <InlineAlert
              variant="info"
              title="连接已建立"
              message="页面加载完成后会自动向 DeepEar 发送一次桥接登录消息；如果没有自动进入，请点击“刷新连接”后再试一次。"
            />
          </div>
          <iframe
            ref={iframeRef}
            title="DeepEar Workspace"
            src={embedUrl}
            onLoad={handleIframeLoad}
            className="h-[calc(100vh-16rem)] min-h-[720px] w-full bg-background"
            referrerPolicy="strict-origin-when-cross-origin"
            data-testid="deepear-iframe"
          />
        </Card>
      ) : null}
    </AppPage>
  );
};

export default DeepEarPage;
