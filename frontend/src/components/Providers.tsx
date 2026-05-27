"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Navbar } from "@/components/Navbar";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={client}>
      <Navbar />
      <main className="min-h-screen">{children}</main>
    </QueryClientProvider>
  );
}
