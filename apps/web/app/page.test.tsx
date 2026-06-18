import { render, screen } from "@testing-library/react";
import Home from "./page";

test("renders navigation tiles for the primary workspaces", () => {
  render(<Home />);

  expect(screen.getByRole("link", { name: /Ask with citations Chat/i })).toHaveAttribute("href", "/chat");
  expect(screen.getByRole("link", { name: /Configure knowledge Admin Sources/i })).toHaveAttribute("href", "/admin/sources");
  expect(screen.getByRole("link", { name: /Trace operations Operator Dashboard/i })).toHaveAttribute("href", "/operator");
});
