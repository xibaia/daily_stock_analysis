import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../api/error';
import { deepearApi } from '../../api/deepear';
import DeepEarPage from '../DeepEarPage';

vi.mock('../../api/deepear', () => ({
  deepearApi: {
    getSession: vi.fn(),
  },
}));

describe('DeepEarPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the embedded iframe after the session bridge loads', async () => {
    vi.mocked(deepearApi.getSession).mockResolvedValue({
      enabled: true,
      publicUrl: 'http://127.0.0.1:8765',
      token: 'bridge-token',
      user: { id: 1, username: 'deepear-bot' },
      expiresHintSeconds: 604800,
    });

    render(
      <MemoryRouter>
        <DeepEarPage />
      </MemoryRouter>,
    );

    const iframe = await screen.findByTestId('deepear-iframe');
    expect(iframe).toBeInTheDocument();
    expect(iframe).toHaveAttribute('src', 'http://127.0.0.1:8765/login?embedded=1');
    expect(screen.getByText(/连接已建立/)).toBeInTheDocument();
  });

  it('shows an empty state when the integration is disabled', async () => {
    vi.mocked(deepearApi.getSession).mockResolvedValue({
      enabled: false,
      publicUrl: null,
      token: null,
      user: null,
      expiresHintSeconds: null,
    });

    render(
      <MemoryRouter>
        <DeepEarPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('DeepEar 集成尚未启用')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新检查' })).toBeInTheDocument();
  });

  it('shows the API error and supports opening the bridge in a new tab', async () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({
      postMessage: vi.fn(),
    } as unknown as Window);

    vi.mocked(deepearApi.getSession).mockResolvedValue({
      enabled: true,
      publicUrl: 'http://127.0.0.1:8765',
      token: 'bridge-token',
      user: { id: 1, username: 'deepear-bot' },
      expiresHintSeconds: 604800,
    });

    render(
      <MemoryRouter>
        <DeepEarPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '新标签页打开' }));

    expect(openSpy).toHaveBeenCalledWith('http://127.0.0.1:8765/login?embedded=1', '_blank');
    openSpy.mockRestore();
  });

  it('renders backend bridge errors and allows retry', async () => {
    vi.mocked(deepearApi.getSession)
      .mockRejectedValueOnce(
        Object.assign(new Error('boom'), {
          parsedError: createParsedApiError({
            title: 'DeepEar 连接失败',
            message: '无法连接 DeepEar 服务。',
            rawMessage: '无法连接 DeepEar 服务。',
            status: 503,
            category: 'http_error',
          }),
        }),
      )
      .mockResolvedValueOnce({
        enabled: false,
        publicUrl: null,
        token: null,
        user: null,
        expiresHintSeconds: null,
      });

    render(
      <MemoryRouter>
        <DeepEarPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('DeepEar 连接失败')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新连接' }));

    await waitFor(() => {
      expect(deepearApi.getSession).toHaveBeenCalledTimes(2);
    });
  });
});
