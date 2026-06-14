export const apiBaseUrl = process.env.NEXT_PUBLIC_SUPPORTLENS_API_URL ?? "http://localhost:8000";

export const demoHeaders = {
  "content-type": "application/json",
  "x-tenant-id": "demo-tenant",
  "x-user-id": "demo-user",
  "x-role": "tenant_admin,platform_operator,end_user",
};
