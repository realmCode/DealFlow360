import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { isDealFlowError } from "@/api/errors";
import { AuthProvider } from "@/app/auth";
import { router } from "@/app/router";
import { Toaster, TooltipProvider } from "@/design-system";

import "@/design-system/tokens.css";
import "@/design-system/base.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The backend has no push channel, so freshness comes from focus
      // refetching plus targeted invalidation after every mutation.
      staleTime: 20_000,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      retry: (count, error) => {
        // 4xx will not become a different answer on retry.
        if (isDealFlowError(error) && error.status >= 400 && error.status < 500) return false;
        return count < 2;
      },
    },
    mutations: { retry: false },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider delayDuration={200} skipDelayDuration={300}>
          <RouterProvider router={router} />
          <Toaster />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
