export type DeepEarUser = {
  id: number;
  username: string;
};

export type DeepEarSessionResponse = {
  enabled: boolean;
  publicUrl: string | null;
  token: string | null;
  user: DeepEarUser | null;
  expiresHintSeconds: number | null;
};
