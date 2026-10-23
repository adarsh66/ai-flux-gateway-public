/** Infrastructure failures must never be presented as a password rejection. */
export function localAuthErrorMessage(status: number, detail?: unknown): string {
  if (status >= 500) {
    return "The sign-in service is temporarily unavailable. Please try again later. Your credentials could not be verified.";
  }
  if (status === 429) return "Too many sign-in attempts. Please wait before trying again.";
  if (status === 401) return "Invalid email or password.";
  if (typeof detail === "string" && detail.trim()) return detail;
  return "Sign-in could not be completed. Please check your details and try again.";
}