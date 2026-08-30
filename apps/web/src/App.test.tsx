import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("identifies the product as a local agent control plane", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "AgentGate" })).toBeInTheDocument();
    expect(screen.getByText("Local Demo")).toBeInTheDocument();
  });
});
