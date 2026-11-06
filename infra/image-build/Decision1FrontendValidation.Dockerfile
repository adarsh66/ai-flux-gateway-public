FROM node:22-alpine
WORKDIR /repo
COPY . .
RUN npm ci --workspaces --include-workspace-root --no-audit --no-fund
# Validation-only constants: no live cloud configuration, credentials or .env files.
ENV VITE_AUTH_MODE=local VITE_CONTROL_API_URL=/api VITE_GATEWAY_URL=https://validation.invalid/v1
# Run every check even if a preceding check fails; propagate the combined failure.
RUN result=0; \
    npm run typecheck; code=$?; echo "D1_TYPECHECK_EXIT=$code"; [ "$code" -eq 0 ] || result=1; \
    npm test -- --reporter=verbose --maxWorkers=2; code=$?; echo "D1_TEST_EXIT=$code"; [ "$code" -eq 0 ] || result=1; \
    npm run build --workspace=@aiflux/admin-portal; code=$?; echo "D1_ADMIN_BUILD_EXIT=$code"; [ "$code" -eq 0 ] || result=1; \
    npm run build --workspace=@aiflux/customer-portal; code=$?; echo "D1_CUSTOMER_BUILD_EXIT=$code"; [ "$code" -eq 0 ] || result=1; \
    exit "$result"