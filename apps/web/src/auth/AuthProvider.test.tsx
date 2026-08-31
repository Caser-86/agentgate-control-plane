import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, RequireAuth } from "./AuthProvider";

describe("AuthProvider", () => {
  afterEach(() => vi.restoreAllMocks());

  it("redirects an unauthenticated browser to the Chinese setup flow", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ authenticated: false, setup_required: true }), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(
      <MemoryRouter initialEntries={["/runs"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<h1>初始化管理员密码</h1>} />
            <Route path="/runs" element={<RequireAuth><p>private route</p></RequireAuth>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByRole("heading", { name: "初始化管理员密码" })).toBeInTheDocument());
  });
});
