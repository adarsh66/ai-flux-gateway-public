# Validation only: build with --no-push from a sanitized UI-only context.
FROM node:22-alpine
WORKDIR /repo
COPY . .
RUN npm ci --workspaces --include-workspace-root
ENV VITE_AUTH_MODE=local VITE_CONTROL_API_URL=/api VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1
RUN npm run typecheck
RUN npx vitest run packages/ui/src/external-provider.test.tsx
RUN npm run build