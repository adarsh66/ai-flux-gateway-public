import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { localAuthErrorMessage } from "./auth-errors";

describe("local authentication errors", () => {
  it.each([500, 502, 503, 504])("does not label HTTP %s as invalid credentials", (status) => {
    const message = localAuthErrorMessage(status, "upstream implementation detail");
    expect(message).toContain("temporarily unavailable");
    expect(message).not.toContain("Invalid email or password");
    expect(message).not.toContain("upstream implementation detail");
  });
  it("reserves password rejection for 401", () => {
    expect(localAuthErrorMessage(401)).toBe("Invalid email or password.");
    expect(localAuthErrorMessage(429)).toContain("Too many");
    expect(localAuthErrorMessage(403, "Account disabled")).toBe("Account disabled");
  });
  it.each([null, [], { message: "not a string" }, ""])('handles malformed error detail %j', (detail) => {
    expect(localAuthErrorMessage(400, detail)).toContain("could not be completed");
  });
});

describe("portal upstream TLS policy", () => {
  it("keeps admin redirects relative behind App Service HTTPS termination", () => {
    const config = readFileSync(resolve(process.cwd(), "apps/admin-portal/nginx.conf.template"), "utf8");
    expect(config).toMatch(/absolute_redirect\s+off;/);
    expect(config).toMatch(/location\s+=\s+\/\s*\{\s*return\s+302\s+\/admin\/;/);
  });
  it.each(["admin", "customer"])("%s verifies the full upstream chain without disabling security", (portal) => {
    const config = readFileSync(resolve(process.cwd(), `apps/${portal}-portal/nginx.conf.template`), "utf8");
    expect(config).toMatch(/proxy_ssl_verify\s+on;/);
    expect(config).toMatch(/proxy_ssl_verify_depth\s+5;/);
    expect(config).toMatch(/proxy_ssl_server_name\s+on;/);
    expect(config).toMatch(/proxy_ssl_trusted_certificate\s+\/etc\/ssl\/certs\/ca-certificates.crt;/);
    expect(config).not.toMatch(/proxy_ssl_verify\s+off;/);
  });
});