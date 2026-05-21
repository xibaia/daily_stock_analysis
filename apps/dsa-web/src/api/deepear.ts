import { toCamelCase } from './utils';
import apiClient from './index';
import type { DeepEarSessionResponse } from '../types/deepear';

export const deepearApi = {
  async getSession(): Promise<DeepEarSessionResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/deepear/session');
    return toCamelCase<DeepEarSessionResponse>(response.data);
  },
};
