import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthProvider";
import { LoginPage } from "./LoginPage";

describe("LoginPage", () => {
  it("uses Chinese labels for setup, expiry, and retry", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ authenticated: false, setup_required: true }), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    render(
      <MemoryRouter>
        <AuthProvider><LoginPage /></AuthProvider>
      </MemoryRouter>,
    );

    return waitFor(() => expect(screen.getByText("初始化管理员密码")).toBeInTheDocument()).then(() => {
      act(() => window.dispatchEvent(new Event("agentgate:session-expired")));
      expect(screen.getByText("初始化管理员密码")).toBeInTheDocument();
      expect(screen.getByText("会话已过期，请重新登录后重试。")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    });
  });
});
