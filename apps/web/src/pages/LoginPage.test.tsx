import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthProvider";
import { LoginPage } from "./LoginPage";

describe("LoginPage", () => {
  it("redirects away from the direct login route when local auth is disabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ authenticated: true, setup_required: false }), {
            headers: { "Content-Type": "application/json" },
          }),
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ csrf_token: "local-auth-disabled" }), {
            headers: { "Content-Type": "application/json" },
          }),
        ),
    );
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<p>控制台首页</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("控制台首页")).toBeInTheDocument());
    expect(screen.queryByLabelText("管理员密码")).not.toBeInTheDocument();
  });

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

  it("shows the six-character minimum for the setup password", async () => {
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

    await waitFor(() => expect(screen.getByText("初始化管理员密码")).toBeInTheDocument());
    expect(screen.getByLabelText("管理员密码")).toHaveAttribute("minlength", "6");
    expect(screen.getByText("管理员密码至少 6 位")).toBeInTheDocument();
  });

  it("shows the API error in Chinese and keeps form controls identifiable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ authenticated: false, setup_required: false }), {
            headers: { "Content-Type": "application/json" },
          }),
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ error: { code: "invalid_credentials", message: "请求被拒绝" } }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          }),
        ),
    );
    render(
      <MemoryRouter>
        <AuthProvider><LoginPage /></AuthProvider>
      </MemoryRouter>,
    );

    const password = await screen.findByLabelText("管理员密码");
    expect(password).toHaveAttribute("name", "password");
    fireEvent.change(password, { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("管理员密码不正确，请检查后重试。")).toBeInTheDocument();
  });
});
