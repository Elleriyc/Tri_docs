"use client";

import { useEffect, useRef, useState } from "react";
import * as signalR from "@microsoft/signalr";

export interface DocumentNotification {
  documentId: string;
  status: "UPLOADED" | "QUEUED" | "PROCESSING" | "PROCESSED" | "ERROR";
  message: string;
  tags?: string[];
}

export function useDocumentNotifications(documentId: string | null): {
  notification: DocumentNotification | null;
  isConnected: boolean;
} {
  const [notification, setNotification] = useState<DocumentNotification | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const connectionRef = useRef<signalR.HubConnection | null>(null);

  useEffect(() => {
    if (!documentId) return;

    const connection = new signalR.HubConnectionBuilder()
      .withUrl(`${process.env.NEXT_PUBLIC_FUNCTIONS_URL ?? "http://localhost:7071"}/api/negotiate`)
      .withAutomaticReconnect()
      .build();

    connectionRef.current = connection;

    connection.on("documentUpdate", (data: DocumentNotification) => {
      if (data.documentId === documentId) {
        setNotification(data);
      }
    });

    connection.onclose(() => setIsConnected(false));
    connection.onreconnecting(() => setIsConnected(false));
    connection.onreconnected(() => setIsConnected(true));

    connection
      .start()
      .then(() => setIsConnected(true))
      .catch((err) => console.error("SignalR connection error:", err));

    return () => {
      connection.stop();
    };
  }, [documentId]);

  return { notification, isConnected };
}
