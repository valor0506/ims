import { useEffect, useRef, useCallback } from 'react';

export function useWebSocket(url: string, onMessage: (data: string) => void) {
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    ws.current = new WebSocket(url);

    ws.current.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.current.onmessage = (event) => {
      onMessage(event.data);
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.current.onclose = () => {
      console.log('WebSocket disconnected');
    };

    return () => {
      ws.current?.close();
    };
  }, [url, onMessage]);

  const send = useCallback((data: string) => {
    ws.current?.send(data);
  }, []);

  return { send };
}