import { useEffect, useState } from "react";
export const base = import.meta.env.VITE_API_BASE_URL || "/api";
export const qs = (values: Record<string, string | number>) =>
  new URLSearchParams(
    Object.entries(values).map(([k, v]) => [k, String(v)]),
  ).toString();

export async function request<T>(
  path: string,
  signal?: AbortSignal,
  body?: string,
): Promise<T> {
  const response = await fetch(base + path, {
    signal,
    ...(body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        }
      : {}),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(
      typeof payload.detail === "string"
        ? payload.detail
        : "Request failed (" +
          response.status +
          "). Check the input and try again.",
    );
  }
  return response.json();
}

export function useApi<T>(path: string | null, body?: string) {
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify([path, body, attempt]);
  const [result, setResult] = useState<{
    key: string;
    data?: T;
    error?: string;
  }>();
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    request<T>(path, controller.signal, body)
      .then((data) => {
        if (!controller.signal.aborted) setResult({ key, data });
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setResult({ key, error: String(e.message || e) });
      });
    return () => controller.abort();
  }, [path, body, key]);
  const current = result?.key === key ? result : undefined;
  return {
    data: current?.data,
    error: current?.error,
    retry: () => setAttempt((n) => n + 1),
  };
}
